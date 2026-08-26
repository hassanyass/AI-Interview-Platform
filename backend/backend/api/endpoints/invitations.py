"""
Admin-side Invitation CRUD — Phase 6, Sub-phase 6A.

Kept as its own file/router rather than growing the already-large admin.py
(519 lines before this). Included under the same /api/v1/admin prefix in
main.py and reuses get_current_admin, so it behaves like part of the same
admin API from the frontend's perspective.

Candidate-facing public routes (GET /invitations/{token},
POST /invitations/{token}/redeem — Sub-phase 6B) belong in a separate,
no-auth router and are not part of this file.
"""
import logging
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from backend.api.deps import get_current_admin
from backend.db.session import get_db
from backend.models.interview import InterviewDefinition, InterviewInvitation, JobApplication
from backend.schemas.admin import InvitationCreate, InvitationResponse
from backend.services.candidate_profile_service import get_or_create_candidate_profile
from backend.services.job_application_service import get_or_create_job_application
from backend.services.notifications import notification_service

logger = logging.getLogger(__name__)

router = APIRouter()


async def _get_definition_or_404(db: AsyncSession, definition_id: UUID) -> InterviewDefinition:
    result = await db.execute(
        select(InterviewDefinition)
        .options(selectinload(InterviewDefinition.job))
        .where(InterviewDefinition.id == definition_id)
    )
    definition = result.scalar_one_or_none()
    if not definition:
        raise HTTPException(status_code=404, detail="InterviewDefinition not found")
    return definition


@router.post(
    "/definitions/{definition_id}/invitations",
    response_model=InvitationResponse,
    status_code=201,
)
async def create_invitation(
    definition_id: UUID,
    payload: InvitationCreate,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    definition = await _get_definition_or_404(db, definition_id)
    email = payload.candidate_email.lower()

    # Atomicity: everything below — CandidateProfile resolve-or-create,
    # JobApplication resolve-or-create, and the InterviewInvitation insert
    # — runs on this one `db` session with NO commit until the very end.
    # get_or_create_candidate_profile and get_or_create_job_application
    # each only open a SAVEPOINT (db.begin_nested()) around their own
    # insert attempt, so a unique-constraint race in either one rolls back
    # just that savepoint, not this whole in-progress transaction. If
    # anything below raises (including the final db.add for the
    # invitation itself, before commit), FastAPI's dependency teardown
    # closes this session without committing, and SQLAlchemy rolls back
    # the entire implicit transaction — so a profile or application can
    # never be left committed on its own without the invitation that was
    # being created for it, and vice versa.
    profile = await get_or_create_candidate_profile(db, email=email)
    application = await get_or_create_job_application(
        db, job_id=definition.job_id, candidate_profile_id=profile.id
    )

    token = secrets.token_urlsafe(32)
    invitation = InterviewInvitation(
        application_id=application.id,
        candidate_email=email,
        status="INVITED",
        token=token,
        expires_at=None,  # Invitation expiration policy is unresolved per
        # docs/CURRENT_DECISIONS.md (P1-adjacent item) — left NULL (no
        # enforced expiry) rather than inventing a duration.
    )
    db.add(invitation)

    # Capture the job title before commit: the session's default
    # expire_on_commit=True marks every already-loaded attribute
    # (including definition.job, even though it was eagerly selectinload'd
    # in _get_definition_or_404) as expired once we commit, and a
    # post-commit lazy-load of a relationship doesn't work in this async
    # context (raises MissingGreenlet). Same pattern update_definition
    # already uses in admin.py (capturing job_id before its own commit).
    job_title = definition.job.title

    await db.commit()
    await db.refresh(invitation)

    invite_link = f"/invite/{token}"
    await notification_service.send_invitation_email(
        to=email,
        link=invite_link,
        context={"job_title": job_title},
    )

    return invitation


@router.get(
    "/definitions/{definition_id}/invitations",
    response_model=list[InvitationResponse],
)
async def list_invitations(
    definition_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    definition = await _get_definition_or_404(db, definition_id)

    result = await db.execute(
        select(InterviewInvitation)
        .join(JobApplication, InterviewInvitation.application_id == JobApplication.id)
        .where(JobApplication.job_id == definition.job_id)
        .order_by(InterviewInvitation.created_at.desc())
    )
    return result.scalars().all()
