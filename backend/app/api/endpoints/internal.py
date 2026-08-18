"""
Internal persistence API for agent-to-backend communication.
Protected by AGENT_API_SECRET — never exposed to the frontend.
"""
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Header, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.api.deps import db_dependency
from app.core.config import settings
from app.models.interview import (
    InterviewSession, InterviewConfiguration,
    InterviewMessage, InterviewEvent, InterviewCheckpoint,
)
from app.models.profile import CandidateProfile
from app.schemas.persistence import (
    MessageCreate, MessageResponse,
    EventCreate, EventResponse,
    CheckpointCreate, CheckpointResponse,
    StatusUpdate, SessionLoadResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

VALID_STATUSES = {"CREATED", "IN_PROGRESS", "DISCONNECTED", "COMPLETED", "TERMINATED"}
VALID_TRANSITIONS = {
    "CREATED": {"IN_PROGRESS"},
    "IN_PROGRESS": {"DISCONNECTED", "COMPLETED", "TERMINATED"},
    "DISCONNECTED": {"IN_PROGRESS", "TERMINATED"},
    "COMPLETED": set(),
    "TERMINATED": set(),
}

# Agent lease duration — agent must renew within this window
AGENT_LEASE_DURATION = timedelta(minutes=10)


# ─── Agent Auth Dependency ─────────────────────────────────────────────────────

async def verify_agent_secret(x_agent_secret: str = Header(...)):
    """Validates the internal AGENT_API_SECRET header."""
    if not settings.AGENT_API_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent API secret is not configured on the server.",
        )
    if x_agent_secret != settings.AGENT_API_SECRET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid agent API secret.",
        )


agent_auth = Depends(verify_agent_secret)


# ─── Helper ────────────────────────────────────────────────────────────────────

async def _get_session(db: AsyncSession, session_id: UUID) -> InterviewSession:
    result = await db.execute(
        select(InterviewSession).where(InterviewSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found.")
    return session


# ─── Load Session (for agent bootstrap / recovery) ────────────────────────────

@router.get(
    "/{session_id}/load",
    response_model=SessionLoadResponse,
    dependencies=[agent_auth],
)
async def load_session_for_agent(
    session_id: UUID,
    agent_id: str = Query(...),
    db: AsyncSession = db_dependency,
):
    """
    Load interview session data for agent bootstrap.
    Acquires agent lease if the session is eligible.
    """
    result = await db.execute(
        select(InterviewSession)
        .options(selectinload(InterviewSession.configuration))
        .where(InterviewSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found.")

    # Check if session is in a resumable state
    if session.status in ("COMPLETED", "TERMINATED"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session is already {session.status} and cannot be resumed.",
        )

    # Check agent lease — prevent two agents from controlling the same session
    now = datetime.now(timezone.utc)
    if (
        session.active_agent_id
        and session.active_agent_id != agent_id
        and session.agent_lease_expires_at
        and session.agent_lease_expires_at > now
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another agent is currently controlling this session.",
        )

    # Acquire lease
    session.active_agent_id = agent_id
    session.agent_lease_expires_at = now + AGENT_LEASE_DURATION

    # Load candidate profile
    profile_result = await db.execute(
        select(CandidateProfile).where(
            CandidateProfile.id == session.candidate_profile_id
        )
    )
    profile = profile_result.scalar_one_or_none()
    candidate_profile = {}
    if profile:
        candidate_profile = {
            "full_name": profile.full_name,
            "email": profile.email,
            "education": profile.education,
            "years_of_experience": profile.years_of_experience,
            "skills": profile.skills,
            "programming_languages": profile.programming_languages,
            "frameworks": profile.frameworks,
            "projects": profile.projects,
            "professional_title": profile.professional_title,
            "recommended_level": profile.recommended_level,
            "confirmed_level": profile.confirmed_level,
        }

    # Load latest checkpoint
    cp_result = await db.execute(
        select(InterviewCheckpoint)
        .where(InterviewCheckpoint.session_id == session_id)
        .order_by(InterviewCheckpoint.created_at.desc())
        .limit(1)
    )
    latest_checkpoint = cp_result.scalar_one_or_none()

    # Load recent messages for conversation context restoration
    msg_result = await db.execute(
        select(InterviewMessage)
        .where(InterviewMessage.session_id == session_id)
        .order_by(InterviewMessage.sequence_number.desc())
        .limit(20)
    )
    recent_messages = [
        {
            "id": m.id,
            "session_id": m.session_id,
            "sequence_number": m.sequence_number,
            "speaker": m.speaker,
            "text": m.text,
            "phase": m.phase,
            "metadata": m.metadata_,
            "created_at": m.created_at,
        }
        for m in reversed(msg_result.scalars().all())
    ]

    config = session.configuration

    response = SessionLoadResponse(
        session_id=session.id,
        candidate_profile_id=session.candidate_profile_id,
        role=session.role,
        level=session.level,
        language=session.language,
        status=session.status,
        started_at=session.started_at,
        job_description=config.job_description if config else None,
        duration_minutes=config.duration if config else 15,
        thinking_time=config.thinking_time if config else 60,
        candidate_profile=candidate_profile,
        latest_checkpoint=latest_checkpoint,
        recent_messages=recent_messages,
        active_agent_id=session.active_agent_id,
        agent_lease_expires_at=session.agent_lease_expires_at,
    )
    
    await db.commit()
    
    return response


# ─── Renew Agent Lease ────────────────────────────────────────────────────────

@router.post(
    "/{session_id}/renew-lease",
    dependencies=[agent_auth],
)
async def renew_agent_lease(
    session_id: UUID,
    agent_id: str = Query(...),
    db: AsyncSession = db_dependency,
):
    session = await _get_session(db, session_id)
    if session.active_agent_id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You do not hold the lease for this session.",
        )
    now = datetime.now(timezone.utc)
    session.agent_lease_expires_at = now + AGENT_LEASE_DURATION
    await db.commit()
    return {"status": "renewed", "expires_at": session.agent_lease_expires_at.isoformat()}


# ─── Status Update ─────────────────────────────────────────────────────────────

@router.patch(
    "/{session_id}/status",
    dependencies=[agent_auth],
)
async def update_session_status(
    session_id: UUID,
    body: StatusUpdate,
    db: AsyncSession = db_dependency,
):
    session = await _get_session(db, session_id)

    current = session.status
    target = body.status

    if target not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {target}")

    allowed = VALID_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from {current} to {target}.",
        )

    session.status = target

    if target == "IN_PROGRESS" and not session.started_at:
        session.started_at = datetime.now(timezone.utc)
    elif target in ("COMPLETED", "TERMINATED"):
        if not session.completed_at:
            session.completed_at = datetime.now(timezone.utc)
        if target == "COMPLETED" and body.final_result is not None:
            session.final_result = body.final_result
        # Release agent lease
        session.active_agent_id = None
        session.agent_lease_expires_at = None

    await db.commit()
    return {"session_id": str(session_id), "status": target}


# ─── Messages ──────────────────────────────────────────────────────────────────

@router.post(
    "/{session_id}/messages",
    response_model=MessageResponse,
    dependencies=[agent_auth],
    status_code=status.HTTP_201_CREATED,
)
async def create_message(
    session_id: UUID,
    body: MessageCreate,
    db: AsyncSession = db_dependency,
):
    await _get_session(db, session_id)

    msg = InterviewMessage(
        session_id=session_id,
        sequence_number=body.sequence_number,
        speaker=body.speaker,
        text=body.text,
        phase=body.phase,
        metadata_=body.metadata,
    )
    db.add(msg)
    try:
        await db.commit()
        await db.refresh(msg)
    except Exception:
        await db.rollback()
        # Idempotency: if unique constraint violated, return existing
        result = await db.execute(
            select(InterviewMessage).where(
                InterviewMessage.session_id == session_id,
                InterviewMessage.sequence_number == body.sequence_number,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing
        raise

    return {
        "id": msg.id,
        "session_id": msg.session_id,
        "sequence_number": msg.sequence_number,
        "speaker": msg.speaker,
        "text": msg.text,
        "phase": msg.phase,
        "metadata": msg.metadata_,
        "created_at": msg.created_at
    }


# ─── Events ────────────────────────────────────────────────────────────────────

@router.post(
    "/{session_id}/events",
    response_model=EventResponse,
    dependencies=[agent_auth],
    status_code=status.HTTP_201_CREATED,
)
async def create_event(
    session_id: UUID,
    body: EventCreate,
    db: AsyncSession = db_dependency,
):
    await _get_session(db, session_id)

    event = InterviewEvent(
        session_id=session_id,
        event_type=body.event_type,
        phase=body.phase,
        sequence_number=body.sequence_number,
        metadata_=body.metadata,
    )
    db.add(event)
    try:
        await db.commit()
        await db.refresh(event)
    except Exception:
        await db.rollback()
        result = await db.execute(
            select(InterviewEvent).where(
                InterviewEvent.session_id == session_id,
                InterviewEvent.sequence_number == body.sequence_number,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing
        raise

    return {
        "id": event.id,
        "session_id": event.session_id,
        "event_type": event.event_type,
        "phase": event.phase,
        "sequence_number": event.sequence_number,
        "metadata": event.metadata_,
        "created_at": event.created_at
    }


# ─── Checkpoints ───────────────────────────────────────────────────────────────

@router.post(
    "/{session_id}/checkpoints",
    response_model=CheckpointResponse,
    dependencies=[agent_auth],
    status_code=status.HTTP_201_CREATED,
)
async def create_checkpoint(
    session_id: UUID,
    body: CheckpointCreate,
    db: AsyncSession = db_dependency,
):
    await _get_session(db, session_id)

    checkpoint = InterviewCheckpoint(
        session_id=session_id,
        schema_version=body.schema_version,
        current_phase=body.current_phase,
        current_question_id=body.current_question_id,
        question_index=body.question_index,
        section=body.section,
        hints_used=body.hints_used,
        followups_used=body.followups_used,
        background_questions_asked=body.background_questions_asked,
        competencies_evaluated=body.competencies_evaluated,
        time_remaining_seconds=body.time_remaining_seconds,
        last_message_sequence=body.last_message_sequence,
        last_event_sequence=body.last_event_sequence,
        current_question_snapshot=body.current_question_snapshot,
        section_progress=body.section_progress,
        question_records=body.question_records,
    )
    db.add(checkpoint)
    await db.commit()
    await db.refresh(checkpoint)

    return checkpoint
