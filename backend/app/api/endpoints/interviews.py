from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.api.deps import db_dependency, current_user_dependency
from app.models.profile import CandidateProfile
from app.models.interview import InterviewSession, InterviewConfiguration
from app.schemas.interview import InterviewSessionCreate, InterviewSessionResponse
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
