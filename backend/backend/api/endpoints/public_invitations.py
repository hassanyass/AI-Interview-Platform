"""
Public candidate-facing invitation routes — Phase 6, Sub-phase 6B.

Deliberately a separate router/file from invitations.py (admin CRUD, mounted
under /api/v1/admin with admin auth). These routes are mounted at
/api/v1/invitations with no admin dependency — GET is fully public, POST
requires a candidate JWT (Supabase, not admin), validated via the existing
get_current_user_token_data / get_current_candidate_profile_id dependencies
(reused, not reimplemented).
"""
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from backend.api.deps import get_current_user_token_data, get_current_candidate_profile_id
from backend.db.session import get_db
from backend.models.interview import (
    InterviewDefinition,
    InterviewInvitation,
    InterviewSession,
    JobApplication,
)
from backend.schemas.public_invitations import (
    InvitationPublicContext,
    RedeemedSessionInfo,
    RedeemResponse,
)
from backend.services.job_application_service import get_or_create_job_application
from backend.api.endpoints.livekit import generate_livekit_token, TokenRequest

logger = logging.getLogger(__name__)

router = APIRouter()


async def _get_invitation_or_404(db: AsyncSession, token: str) -> InterviewInvitation:
    result = await db.execute(
        select(InterviewInvitation)
        .options(
            selectinload(InterviewInvitation.application).selectinload(JobApplication.job)
        )
        .where(InterviewInvitation.token == token)
    )
    invitation = result.scalar_one_or_none()
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")
    return invitation


@router.get("/{token}", response_model=InvitationPublicContext)
async def get_invitation(token: str, db: AsyncSession = Depends(get_db)):
    invitation = await _get_invitation_or_404(db, token)

    # Expiration check kept in place even though 6A always writes
    # expires_at=NULL (policy unresolved) — so it activates automatically
    # once that policy is set, without needing this endpoint touched again.
    if invitation.expires_at is not None and invitation.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="This invitation has expired")

    # Capture everything needed from the relationship chain BEFORE any
    # commit below. expire_on_commit=True marks already-loaded relationships
    # (even eagerly selectinload'd ones) as expired at commit time, and a
    # post-commit lazy-load doesn't work in this async context
    # (MissingGreenlet) — same lesson as 6A's invitations.py fix.
    job = invitation.application.job
    job_title = job.title
    job_description = job.description
    job_seniority = job.seniority
    job_instructions = job.instructions
    job_id = job.id

    if invitation.status == "INVITED":
        invitation.status = "OPENED"
        await db.commit()
        await db.refresh(invitation)

    definition_result = await db.execute(
        select(InterviewDefinition).where(InterviewDefinition.job_id == job_id)
    )
    definition = definition_result.scalar_one_or_none()

    return InvitationPublicContext(
        job_title=job_title,
        job_description=job_description,
        seniority=job_seniority,
        candidate_instructions=job_instructions,
        duration_minutes=definition.duration_minutes if definition else 15,
        invitation_status=invitation.status,
        candidate_email=invitation.candidate_email,
    )


@router.post("/{token}/redeem", response_model=RedeemResponse)
async def redeem_invitation(
    token: str,
    db: AsyncSession = Depends(get_db),
    token_data: dict = Depends(get_current_user_token_data),
    candidate_profile_id: str = Depends(get_current_candidate_profile_id),
):
    invitation = await _get_invitation_or_404(db, token)

    # Capture job identity BEFORE any commit below — expire_on_commit=True
    # would otherwise expire this eagerly-loaded relationship at the first
    # commit, and a post-commit lazy-load doesn't work in this async
    # context (MissingGreenlet) — same lesson as 6A's invitations.py fix
    # and this file's own get_invitation handler above.
    job_id = invitation.application.job.id
    job_title = invitation.application.job.title
    job_seniority = invitation.application.job.seniority
    job_language = invitation.application.job.language

    # Hard security boundary — runs on EVERY call, regardless of the
    # invitation's current status. Two independent rejections, both 403:
    #  1. The JWT must be a real Supabase-verified token, not a guest
    #     token (guest identity is self-asserted at public registration,
    #     with no OTP verification — accepting one here would let a
    #     public-flow candidate bypass OTP entirely for the personalized
    #     flow).
    #  2. The JWT's own email claim must exactly match
    #     invitation.candidate_email (not the resolved CandidateProfile's
    #     stored email, which could in principle drift from the JWT over
    #     time — comparing the raw claim is the more precise check).
    if token_data.get("type") != "supabase":
        raise HTTPException(status_code=403, detail="A verified Supabase session is required to redeem this invitation")
    jwt_email = (token_data.get("email") or "").lower()
    if jwt_email != invitation.candidate_email:
        raise HTTPException(status_code=403, detail="This invitation was issued to a different email address")

    # Transaction #1: durable proof OTP verification succeeded, independent
    # of whether session creation below succeeds. Skipped if a prior call
    # already advanced past this point — this endpoint is safely
    # re-callable; it does not re-verify OTP each time (the check above
    # still runs every call, but this WRITE only happens once).
    if invitation.status not in ("VERIFIED", "STARTED"):
        invitation.status = "VERIFIED"
        await db.commit()
        await db.refresh(invitation)

    if invitation.status == "STARTED":
        # Already fully redeemed by a prior call. Don't create a second
        # session — find the existing one (keyed by application_id, since
        # InterviewSession has no direct FK back to InterviewInvitation;
        # see docs/phase6-architecture.md's Flow A note) and re-mint a
        # fresh LiveKit token for it rather than erroring.
        existing_result = await db.execute(
            select(InterviewSession)
            .where(InterviewSession.application_id == invitation.application_id)
            .order_by(InterviewSession.created_at.desc())
        )
        existing_session = existing_result.scalars().first()
        if existing_session:
            token_response = await generate_livekit_token(
                TokenRequest(session_id=str(existing_session.id)), db, candidate_profile_id
            )
            return RedeemResponse(
                session=RedeemedSessionInfo(
                    id=existing_session.id,
                    job_id=existing_session.job_id,
                    definition_id=existing_session.definition_id,
                    status=existing_session.status,
                    created_at=existing_session.created_at,
                ),
                livekit_token=token_response.token,
                livekit_url=token_response.url,
            )
        # Defensive fallback: STARTED but no session found (shouldn't
        # normally happen) — self-heal by falling through to create one
        # below rather than erroring.

    # Transaction #2: JobApplication resolve-or-create, InterviewSession
    # creation, and invitation.status = "STARTED" all commit together.
    definition_result = await db.execute(
        select(InterviewDefinition).where(InterviewDefinition.job_id == job_id)
    )
    definition = definition_result.scalar_one_or_none()
    if not definition:
        raise HTTPException(status_code=500, detail="Job has no InterviewDefinition")

    application = await get_or_create_job_application(
        db, job_id=job_id, candidate_profile_id=UUID(candidate_profile_id)
    )

    # role/level are legacy InterviewConfiguration-era columns, NOT NULL
    # with no default, and still have no B2B equivalent for level beyond
    # Job.seniority — level falls back to a hardcoded "mid" when
    # Job.seniority is unset (flagged separately in
    # docs/CURRENT_DECISIONS.md, lower severity, not yet resolved).
    # language now comes from job_language (Job.language) — the "Interview
    # language" decision in docs/CURRENT_DECISIONS.md resolved this to a
    # real Job-level property, no longer a hardcoded placeholder.
    session = InterviewSession(
        candidate_profile_id=UUID(candidate_profile_id),
        job_id=job_id,
        definition_id=definition.id,
        application_id=application.id,
        role=job_title,
        level=job_seniority or "mid",
        language=job_language,
        status="CREATED",
    )
    db.add(session)
    await db.flush()

    token_response = await generate_livekit_token(
        TokenRequest(session_id=str(session.id)), db, candidate_profile_id
    )

    invitation.status = "STARTED"
    await db.commit()
    await db.refresh(session)

    return RedeemResponse(
        session=RedeemedSessionInfo(
            id=session.id,
            job_id=session.job_id,
            definition_id=session.definition_id,
            status=session.status,
            created_at=session.created_at,
        ),
        livekit_token=token_response.token,
        livekit_url=token_response.url,
    )
