from fastapi import APIRouter, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from backend.api.deps import db_dependency, current_user_dependency
from backend.models.profile import CandidateProfile, Resume
from backend.schemas.profile import ResumeResponse
from backend.services.resume_ingest import ingest_resume
import logging
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

    # Background-subsection step 2: the whole store -> parse -> apply path
    # now lives in services/resume_ingest.py, shared with the candidate
    # entry step (POST /interviews/{id}/cv). Behaviour unchanged.
    return await ingest_resume(db, file, profile)

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
