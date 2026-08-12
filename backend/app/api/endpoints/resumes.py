from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.api.deps import db_dependency, current_user_dependency
from app.models.profile import CandidateProfile, Resume
from app.schemas.profile import ResumeResponse
from app.services.resume_service import ResumeService
import logging
import uuid
from uuid import UUID

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/", response_model=ResumeResponse)
async def upload_resume(
    file: UploadFile = File(...),
    db: AsyncSession = db_dependency,
    user_id: str = current_user_dependency
):
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid User ID format")
        
    # Check if profile exists
    result = await db.execute(select(CandidateProfile).where(CandidateProfile.id == user_uuid))
    profile = result.scalars().first()
    if not profile:
        raise HTTPException(status_code=404, detail="Candidate profile not found. Create a profile first.")
    
    # 1. Validate File
    ResumeService.validate_pdf(file)
    
    resume_id = uuid.uuid4()
    
    # Read bytes for extraction
    file_bytes = await file.read()
    await file.seek(0) # reset pointer for upload if needed (though upload might take bytes, our upload takes file but we can modify to take file object)
    
    # 2. Upload to Supabase Storage
    storage_path = await ResumeService.upload(file, user_id, resume_id)
    
    # 3. Create initial Resume record (PROCESSING)
    db_resume = Resume(
        id=resume_id,
        profile_id=user_uuid,
        original_filename=file.filename,
        storage_path=storage_path,
        mime_type=file.content_type,
        extraction_status="PROCESSING"
    )
    db.add(db_resume)
    await db.commit()
    await db.refresh(db_resume)
    
    try:
        # 4. Extract Text
        extracted_text = ResumeService.extract_text(file_bytes)
        db_resume.extracted_text = extracted_text
        
        # 5. Extract Structured Profile via LLM
        extracted_profile = await ResumeService.build_candidate_profile(extracted_text)
        
        # Update Resume Status
        db_resume.extraction_status = "COMPLETED"
        
        # Update Profile
        profile.education = extracted_profile.education
        profile.years_of_experience = extracted_profile.years_of_experience
        profile.skills = extracted_profile.skills
        profile.programming_languages = extracted_profile.programming_languages
        profile.frameworks = extracted_profile.frameworks
        profile.projects = extracted_profile.projects
        profile.recommended_level = extracted_profile.recommended_level
        
        await db.commit()
        await db.refresh(db_resume)
        
    except Exception as e:
        logger.error(f"Error processing resume: {e}")
        db_resume.extraction_status = "FAILED"
        await db.commit()
        raise HTTPException(status_code=500, detail="Failed to process resume text extraction.")
        
    return db_resume

@router.get("/", response_model=list[ResumeResponse])
async def list_resumes(
    db: AsyncSession = db_dependency,
    user_id: str = current_user_dependency
):
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid User ID format")
        
    result = await db.execute(select(Resume).where(Resume.profile_id == user_uuid))
    resumes = result.scalars().all()
    return resumes
