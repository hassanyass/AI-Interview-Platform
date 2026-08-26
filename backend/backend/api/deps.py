from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.session import get_db
from backend.core.security import get_current_user_token_data
from backend.models.profile import CandidateProfile, UserRole
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
import uuid

# Re-export for convenience
db_dependency = Depends(get_db)

async def get_current_candidate_profile_id(
    token_data: dict = Depends(get_current_user_token_data),
    db: AsyncSession = Depends(get_db)
) -> str:
    sub = token_data["sub"]
    token_type = token_data["type"]
    email = token_data.get("email")

    if token_type == "guest":
        return sub
    
    # Supabase token
    try:
        supabase_id = uuid.UUID(sub)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid Supabase subject UUID")

    # 1. Lookup by supabase_user_id
    stmt = select(CandidateProfile).where(CandidateProfile.supabase_user_id == supabase_id)
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()
    if profile:
        return str(profile.id)

    # 2. Fallback to email if present
    if email:
        stmt = select(CandidateProfile).where(CandidateProfile.email == email)
        result = await db.execute(stmt)
        profile = result.scalar_one_or_none()
        if profile:
            profile_id = str(profile.id)
            profile.supabase_user_id = supabase_id
            await db.commit()
            return profile_id
    
    # 3. Create (Handling check-then-act race)
    if not email:
        raise HTTPException(status_code=401, detail="Supabase token lacks email for profile resolution")
        
    try:
        new_profile = CandidateProfile(
            supabase_user_id=supabase_id,
            email=email,
            full_name="Candidate"
        )
        db.add(new_profile)
        await db.commit()
        await db.refresh(new_profile)
        return str(new_profile.id)
    except IntegrityError:
        await db.rollback()
        # Fallback to re-lookup
        stmt = select(CandidateProfile).where(CandidateProfile.email == email)
        result = await db.execute(stmt)
        profile = result.scalar_one_or_none()
        if profile:
            profile_id = str(profile.id)
            profile.supabase_user_id = supabase_id
            await db.commit()
            return profile_id
        raise HTTPException(status_code=500, detail="Failed to resolve profile identity")

current_user_dependency = Depends(get_current_candidate_profile_id)

async def get_current_admin(
    token_data: dict = Depends(get_current_user_token_data),
    db: AsyncSession = Depends(get_db)
) -> str:
    sub = token_data["sub"]
    try:
        user_uuid = uuid.UUID(sub)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid admin subject UUID")
        
    stmt = select(UserRole).where(UserRole.user_id == user_uuid)
    result = await db.execute(stmt)
    user_role = result.scalar_one_or_none()
    if not user_role or user_role.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return sub
