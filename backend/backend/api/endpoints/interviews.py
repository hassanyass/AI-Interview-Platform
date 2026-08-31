from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from backend.api.deps import db_dependency, current_user_dependency, get_current_admin
from backend.models.profile import CandidateProfile
from backend.models.interview import InterviewSession, InterviewConfiguration, InterviewDefinition, Job
from backend.schemas.interview import (
    InterviewSessionResponse, 
    InterviewResultResponse
)
from backend.core.config import settings
from backend.services.guest_jwt_service import mint_guest_jwt
import logging
from uuid import UUID
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

router = APIRouter()



@router.get("/", response_model=list[InterviewSessionResponse])
async def list_interviews(
    db: AsyncSession = db_dependency,
    user_id: str = current_user_dependency
):
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid User ID format")
        
    result = await db.execute(
        select(InterviewSession)
        .options(selectinload(InterviewSession.configuration))
        .where(InterviewSession.candidate_profile_id == user_uuid)
    )
    sessions = result.scalars().all()
    return sessions

@router.get("/{session_id}", response_model=InterviewSessionResponse)
async def get_interview(
    session_id: UUID,
    db: AsyncSession = db_dependency,
    user_id: str = current_user_dependency
):
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid User ID format")
        
    result = await db.execute(
        select(InterviewSession)
        .options(selectinload(InterviewSession.configuration))
        .where(InterviewSession.id == session_id)
    )
    session = result.scalars().first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found")
        
    # Security Ownership Check
    if session.candidate_profile_id != user_uuid:
        raise HTTPException(status_code=403, detail="Not authorized to access this interview session")

    # WR-D follow-up: candidate_instructions + ordered section-type list for
    # the intro screen and the waiting room's "what's next" label. Plain
    # extra selects rather than new relationships on InterviewSession, to
    # keep this additive-only (no model/migration change) — see
    # docs/CURRENT_DECISIONS.md. None for legacy sessions with no
    # job_id/definition_id.
    candidate_instructions = None
    if session.job_id:
        job_result = await db.execute(select(Job).where(Job.id == session.job_id))
        job = job_result.scalar_one_or_none()
        if job:
            candidate_instructions = job.instructions

    sections: list[str] = []
    if session.definition_id:
        definition_result = await db.execute(
            select(InterviewDefinition)
            .options(selectinload(InterviewDefinition.sections))
            .where(InterviewDefinition.id == session.definition_id)
        )
        definition = definition_result.scalar_one_or_none()
        if definition:
            # InterviewDefinition.sections is already order_by=order_index
            # at the relationship level (models/interview.py).
            sections = [s.section_type for s in definition.sections]

    candidate_name = None
    profile_result = await db.execute(
        select(CandidateProfile).where(CandidateProfile.id == session.candidate_profile_id)
    )
    profile = profile_result.scalar_one_or_none()
    if profile:
        candidate_name = profile.full_name

    return InterviewSessionResponse.model_validate(session).model_copy(
        update={
            "candidate_instructions": candidate_instructions, 
            "sections": sections,
            "candidate_name": candidate_name
        }
    )


@router.post("/{session_id}/terminate", response_model=InterviewSessionResponse)
async def terminate_interview(
    session_id: UUID,
    db: AsyncSession = db_dependency,
    user_id: str = current_user_dependency,
):
    """Close an abandoned user-owned session so a fresh interview can start."""
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid User ID format")

    result = await db.execute(
        select(InterviewSession)
        .options(selectinload(InterviewSession.configuration))
        .where(InterviewSession.id == session_id, InterviewSession.candidate_profile_id == user_uuid)
    )
    session = result.scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found")
    if session.status in ("COMPLETED", "TERMINATED"):
        return session

    session.status = "TERMINATED"
    session.completed_at = datetime.now(timezone.utc)
    session.active_agent_id = None
    session.agent_lease_expires_at = None
    await db.commit()
    await db.refresh(session)
    return session


@router.get("/{session_id}/transcript")
async def get_transcript(
    session_id: UUID,
    db: AsyncSession = db_dependency,
    user_id: str = current_user_dependency
):
    """Returns the ordered transcript for a given interview session."""
    from backend.models.interview import InterviewMessage
    
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid User ID format")
    
    # Verify ownership
    result = await db.execute(
        select(InterviewSession).where(InterviewSession.id == session_id)
    )
    session = result.scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found")
    if session.candidate_profile_id != user_uuid:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    msg_result = await db.execute(
        select(InterviewMessage)
        .where(InterviewMessage.session_id == session_id)
        .order_by(InterviewMessage.sequence_number)
    )
    messages = msg_result.scalars().all()
    
    return [
        {
            "sequence_number": m.sequence_number,
            "speaker": m.speaker,
            "text": m.text,
            "phase": m.phase,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
    ]


@router.get("/{session_id}/events")
async def get_events(
    session_id: UUID,
    db: AsyncSession = db_dependency,
    user_id: str = current_user_dependency
):
    """Returns the ordered events for a given interview session."""
    from backend.models.interview import InterviewEvent
    
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid User ID format")
    
    result = await db.execute(
        select(InterviewSession).where(InterviewSession.id == session_id)
    )
    session = result.scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found")
    if session.candidate_profile_id != user_uuid:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    event_result = await db.execute(
        select(InterviewEvent)
        .where(InterviewEvent.session_id == session_id)
        .order_by(InterviewEvent.sequence_number)
    )
    events = event_result.scalars().all()
    
    return [
        {
            "event_type": e.event_type,
            "phase": e.phase,
            "sequence_number": e.sequence_number,
            "metadata": e.metadata_,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]


@router.get("/{session_id}/result", response_model=InterviewResultResponse)
async def get_interview_result(
    session_id: UUID,
    db: AsyncSession = db_dependency,
    admin_id: str = Depends(get_current_admin)
):
    result = await db.execute(
        select(InterviewSession).where(
            InterviewSession.id == session_id
        )
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found.")
        
    if session.status not in ("COMPLETED", "TERMINATED"):
        raise HTTPException(
            status_code=400, 
            detail=f"Result not available. Interview status is {session.status}."
        )

    if session.final_result is None:
        raise HTTPException(
            status_code=409,
            detail="Interview is complete, but the evaluation is still being persisted.",
        )

    return InterviewResultResponse(
        session_id=session.id,
        status=session.status,
        completed_at=session.completed_at,
        final_result=session.final_result
    )
