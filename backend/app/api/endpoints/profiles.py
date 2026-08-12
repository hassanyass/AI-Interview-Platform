from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.api.deps import db_dependency, current_user_dependency
from app.models.profile import CandidateProfile
from app.schemas.profile import CandidateProfileResponse, CandidateProfileCreate, CandidateProfileUpdate
import logging
from uuid import UUID

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/me", response_model=CandidateProfileResponse)
async def get_my_profile(
    db: AsyncSession = db_dependency,
    user_id: str = current_user_dependency
):
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid User ID format")

    result = await db.execute(select(CandidateProfile).where(CandidateProfile.id == user_uuid))
    profile = result.scalars().first()
    
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
        
    return profile

@router.post("/", response_model=CandidateProfileResponse)
async def create_profile(
    profile_in: CandidateProfileCreate,
    db: AsyncSession = db_dependency,
    user_id: str = current_user_dependency
):
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid User ID format")

    result = await db.execute(select(CandidateProfile).where(CandidateProfile.id == user_uuid))
    existing_profile = result.scalars().first()
    
    if existing_profile:
        raise HTTPException(status_code=400, detail="Profile already exists")
        
    db_profile = CandidateProfile(
        id=user_uuid,
        **profile_in.model_dump(exclude_unset=True)
    )
    db.add(db_profile)
    await db.commit()
    await db.refresh(db_profile)
    return db_profile

@router.patch("/me", response_model=CandidateProfileResponse)
async def update_my_profile(
    profile_in: CandidateProfileUpdate,
    db: AsyncSession = db_dependency,
    user_id: str = current_user_dependency
):
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid User ID format")

    result = await db.execute(select(CandidateProfile).where(CandidateProfile.id == user_uuid))
    profile = result.scalars().first()
    
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
        
    update_data = profile_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(profile, field, value)
        
    await db.commit()
    await db.refresh(profile)
    return profile
