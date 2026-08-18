from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.api.deps import db_dependency, current_user_dependency
from app.models.profile import CandidateProfile
from app.models.interview import InterviewSession, InterviewConfiguration
from app.schemas.interview import InterviewSessionCreate, InterviewSessionResponse, InterviewResultResponse
import logging
from uuid import UUID
import uuid

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/", response_model=InterviewSessionResponse)
async def create_interview(
    session_in: InterviewSessionCreate,
    db: AsyncSession = db_dependency,
    user_id: str = current_user_dependency
):
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid User ID format")

    # Ensure profile exists
    result = await db.execute(select(CandidateProfile).where(CandidateProfile.id == user_uuid))
    profile = result.scalars().first()
    if not profile:
        raise HTTPException(status_code=404, detail="Candidate profile not found. Create a profile first.")
        
    session_id = uuid.uuid4()
    
    # 1. Create Interview Session
    db_session = InterviewSession(
        id=session_id,
        candidate_profile_id=user_uuid,
        role=session_in.configuration.role,
        level=session_in.configuration.level,
        language=session_in.configuration.language,
        status="CREATED"
    )
    db.add(db_session)
    
    # 2. Create Interview Configuration
    db_config = InterviewConfiguration(
        session_id=session_id,
        **session_in.configuration.model_dump()
    )
    db.add(db_config)
    
    await db.commit()
    
    # Reload with configuration
    result = await db.execute(
        select(InterviewSession)
        .options(selectinload(InterviewSession.configuration))
        .where(InterviewSession.id == session_id)
    )
    loaded_session = result.scalars().first()
    return loaded_session

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
        
    return session


@router.get("/{session_id}/transcript")
async def get_transcript(
    session_id: UUID,
    db: AsyncSession = db_dependency,
    user_id: str = current_user_dependency
):
    """Returns the ordered transcript for a given interview session."""
    from app.models.interview import InterviewMessage
    
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
    from app.models.interview import InterviewEvent
    
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
    user_id: str = current_user_dependency
):
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid User ID format")

    result = await db.execute(
        select(InterviewSession).where(
            InterviewSession.id == session_id,
            InterviewSession.candidate_profile_id == user_uuid
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

    return InterviewResultResponse(
        session_id=session.id,
        status=session.status,
        completed_at=session.completed_at,
        final_result=session.final_result
    )
