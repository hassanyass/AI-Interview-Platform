"""
Public candidate-facing self-registration routes — Phase 6, Sub-phase 6C,
Flow B (public link, guest identity, no verification).

Deliberately a separate router/file from public_invitations.py (Flow A,
personalized/OTP-verified) — per docs/phase6-architecture.md: "Do not let
the agent merge these into one endpoint or one status enum. They have
different identity models (guest vs. Supabase-verified) and different
data (one has an InterviewInvitation row, one doesn't)."

Mounted at /api/v1/apply, fully public — no admin auth, and no candidate
JWT required either (that's the whole point: this endpoint MINTS the
guest JWT, it doesn't consume one).
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from backend.db.session import get_db
from backend.models.interview import InterviewDefinition, InterviewSession
from backend.schemas.public_apply import (
    PublicApplyContext,
    PublicRegisterRequest,
    PublicRegisterResponse,
)
from backend.schemas.public_invitations import RedeemedSessionInfo
from backend.services.candidate_profile_service import get_or_create_candidate_profile
from backend.services.job_application_service import get_or_create_job_application
from backend.services.guest_jwt_service import mint_guest_jwt
from backend.api.endpoints.livekit import generate_livekit_token, TokenRequest

logger = logging.getLogger(__name__)

router = APIRouter()


async def _get_public_definition_or_403(db: AsyncSession, token: str) -> InterviewDefinition:
    result = await db.execute(
        select(InterviewDefinition)
        .options(selectinload(InterviewDefinition.job))
        .where(InterviewDefinition.public_access_token == token)
    )
    definition = result.scalar_one_or_none()
    # Same rejection message/status as the legacy public_register endpoint,
    # for consistency — but with a stricter check: the legacy endpoint only
    # validates is_public, not job.status. Flow B's own spec requires both
    # (a public link should only actually work once the job is truly live).
    if not definition or not definition.is_public or definition.job.status != "PUBLISHED":
        raise HTTPException(status_code=403, detail="Invalid or inactive public access link")
    return definition


@router.get("/{token}", response_model=PublicApplyContext)
async def get_apply_context(token: str, db: AsyncSession = Depends(get_db)):
    definition = await _get_public_definition_or_403(db, token)
    job = definition.job
    return PublicApplyContext(
        job_title=job.title,
        job_description=job.description,
        seniority=job.seniority,
        candidate_instructions=job.instructions,
        duration_minutes=definition.duration_minutes,
    )


@router.post("/{token}/register", response_model=PublicRegisterResponse)
async def register_public_applicant(
    token: str,
    payload: PublicRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    definition = await _get_public_definition_or_403(db, token)
    job = definition.job
    email = payload.email.lower()

    # One transaction, one commit at the end — no intermediate durable
    # state needed here (unlike 6B's redeem, there's no OTP-verification
    # step to protect independently). Reading job.title/seniority/language
    # is safe throughout since nothing commits before the final commit
    # below.
    profile = await get_or_create_candidate_profile(db, email=email, full_name=payload.name)
    application = await get_or_create_job_application(
        db,
        job_id=job.id,
        candidate_profile_id=profile.id,
        resume_id=payload.resume_id,
    )

    access_token = mint_guest_jwt(str(profile.id), email)

    # Per 6C's own stop condition: repeat registrations by the same email
    # reuse the same CandidateProfile and JobApplication, but each call
    # creates its OWN new InterviewSession — deliberately not idempotent
    # the way 6B's redeem is (no invitation-status concept to key off of
    # here; the guest may genuinely want a fresh session on a return visit).
    session = InterviewSession(
        candidate_profile_id=profile.id,
        job_id=job.id,
        definition_id=definition.id,
        application_id=application.id,
        role=job.title,
        level=job.seniority or "mid",
        language=job.language,
        status="CREATED",
    )
    db.add(session)
    await db.flush()

    token_response = await generate_livekit_token(
        TokenRequest(session_id=str(session.id)), db, str(profile.id)
    )

    await db.commit()
    await db.refresh(session)

    return PublicRegisterResponse(
        access_token=access_token,
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
