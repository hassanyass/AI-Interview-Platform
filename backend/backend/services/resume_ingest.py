"""One CV ingestion path, shared by POST /resumes (the profile-level upload)
and POST /interviews/{id}/cv (the candidate entry step).

docs/verbal-background-subsection-plan.md §2 "Candidate (entry)", step 2.
Extracted verbatim in behaviour from resumes.py's upload_resume so the
entry step cannot drift from it: validate -> store in Supabase Storage ->
Resume row (PROCESSING) -> PyMuPDF text -> Groq structured profile ->
CandidateProfile fields -> COMPLETED (or FAILED, with the row kept so the
failure is visible and retryable).
"""
import logging
import uuid

from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.profile import CandidateProfile, Resume
from backend.services.resume_service import ResumeService

logger = logging.getLogger(__name__)


async def ingest_resume(db: AsyncSession, file: UploadFile, profile: CandidateProfile) -> Resume:
    """Store, parse and apply a PDF CV for `profile`. Commits. Returns the
    Resume row (extraction_status COMPLETED). Raises HTTPException on a
    bad file (400/413), storage failure (5xx) or extraction failure (500)."""
    ResumeService.validate_pdf(file)

    resume_id = uuid.uuid4()
    file_bytes = await file.read()
    await file.seek(0)  # ResumeService.upload reads the stream itself

    storage_path = await ResumeService.upload(file, str(profile.id), resume_id)

    db_resume = Resume(
        id=resume_id,
        profile_id=profile.id,
        original_filename=file.filename,
        storage_path=storage_path,
        mime_type=file.content_type,
        file_size=len(file_bytes),
        extraction_status="PROCESSING",
    )
    db.add(db_resume)
    await db.commit()
    await db.refresh(db_resume)

    try:
        extracted_text = ResumeService.extract_text(file_bytes)
        db_resume.extracted_text = extracted_text

        extracted_profile = await ResumeService.build_candidate_profile(extracted_text)
        db_resume.extraction_status = "COMPLETED"

        profile.education = extracted_profile.education
        profile.years_of_experience = extracted_profile.years_of_experience
        profile.skills = extracted_profile.skills
        profile.programming_languages = extracted_profile.programming_languages
        profile.frameworks = extracted_profile.frameworks
        profile.projects = extracted_profile.projects
        profile.professional_title = extracted_profile.professional_title
        profile.recommended_level = extracted_profile.recommended_level

        await db.commit()
        await db.refresh(db_resume)
    except Exception as e:  # noqa: BLE001 -- mark the row FAILED whatever went wrong
        logger.error("Error processing resume %s: %s", resume_id, e)
        db_resume.extraction_status = "FAILED"
        await db.commit()
        raise HTTPException(status_code=500, detail="Failed to process resume text extraction.")

    return db_resume


def profile_cv_summary(profile: CandidateProfile) -> dict:
    """The short "what we read" the candidate is shown before Start, so a
    bad parse is visible rather than silent (ruling Q1)."""
    return {
        "professional_title": profile.professional_title,
        "years_of_experience": profile.years_of_experience,
        "skills": list(profile.skills or [])[:8],
        "projects_count": len(profile.projects or []),
    }
