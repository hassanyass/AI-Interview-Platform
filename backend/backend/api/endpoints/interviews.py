from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from backend.api.deps import db_dependency, current_user_dependency, get_current_admin
from backend.models.profile import CandidateProfile
from backend.models.interview import InterviewSession, InterviewDefinition, Job, InterviewConsent, JobApplication
from backend.models.profile import Resume
from backend.services.resume_ingest import ingest_resume, profile_cv_summary
from backend.schemas.interview import (
    TranscriptEntryResponse,
    SessionEventResponse,
    InterviewSessionResponse,
    InterviewResultResponse,
    ConsentCreate,
    ConsentResponse,
    SessionCvStatus,
    CvSummary,
)
import logging
from uuid import UUID
from backend.services.sessions.finalization import finalize_live_session

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


# ─── Candidate CV gate (Background subsection step 2) ────────────────────────
# Register/redeem -> mandatory CV -> Start (ruling Q2). The room token is
# only minted once the session's JobApplication has a resume_id; see
# livekit.py's generate_livekit_token. These two endpoints are the entry
# pages' (and the intro screen's) view of, and way through, that gate.

async def _load_owned_session_with_application(db: AsyncSession, session_id: UUID, user_id: str):
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid User ID format")
    result = await db.execute(select(InterviewSession).where(InterviewSession.id == session_id))
    session = result.scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found")
    if session.candidate_profile_id != user_uuid:
        raise HTTPException(status_code=403, detail="Not authorized to access this interview session")
    application = None
    if session.application_id:
        app_result = await db.execute(select(JobApplication).where(JobApplication.id == session.application_id))
        application = app_result.scalars().first()
    profile_result = await db.execute(select(CandidateProfile).where(CandidateProfile.id == user_uuid))
    profile = profile_result.scalars().first()
    if not profile:
        raise HTTPException(status_code=404, detail="Candidate profile not found.")
    return session, application, profile


async def _cv_status(db: AsyncSession, session: InterviewSession, application, profile: CandidateProfile) -> SessionCvStatus:
    resume = None
    if application is not None and application.resume_id:
        res = await db.execute(select(Resume).where(Resume.id == application.resume_id))
        resume = res.scalars().first()
    return SessionCvStatus(
        session_id=session.id,
        required=application is not None,
        has_resume=resume is not None,
        resume_id=resume.id if resume else None,
        original_filename=resume.original_filename if resume else None,
        extraction_status=resume.extraction_status if resume else None,
        summary=CvSummary(**profile_cv_summary(profile)) if resume else None,
    )


@router.get("/{session_id}/cv", response_model=SessionCvStatus)
async def get_session_cv(
    session_id: UUID,
    db: AsyncSession = db_dependency,
    user_id: str = current_user_dependency,
):
    """Whether this session still needs a CV, and what we read from the one
    it has (an invited candidate whose application already carries a CV is
    offered "use the CV we have" -- ruling Q1)."""
    session, application, profile = await _load_owned_session_with_application(db, session_id, user_id)
    return await _cv_status(db, session, application, profile)


@router.post("/{session_id}/cv", response_model=SessionCvStatus)
async def upload_session_cv(
    session_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = db_dependency,
    user_id: str = current_user_dependency,
):
    """Upload (or replace) the CV for this session's application: same
    ingestion as POST /resumes, then links JobApplication.resume_id. Allowed
    only before the interview starts."""
    session, application, profile = await _load_owned_session_with_application(db, session_id, user_id)
    if application is None:
        raise HTTPException(status_code=409, detail="This session has no job application to attach a CV to.")
    if session.status != "CREATED":
        raise HTTPException(status_code=409, detail="The CV can only be changed before the interview starts.")
    resume = await ingest_resume(db, file, profile)
    # ingest_resume commits (expire_on_commit) -- reload the rows loaded
    # before it, or the next attribute access lazy-loads outside greenlet
    # context (MissingGreenlet), the same lesson as public_invitations.py.
    await db.refresh(application)
    await db.refresh(session)
    await db.refresh(profile)
    application.resume_id = resume.id
    await db.commit()
    await db.refresh(application)
    await db.refresh(session)
    await db.refresh(profile)
    return await _cv_status(db, session, application, profile)


@router.post("/{session_id}/terminate", response_model=InterviewSessionResponse)
async def terminate_interview(
    session_id: UUID,
    db: AsyncSession = db_dependency,
    user_id: str = current_user_dependency,
):
    """Close a candidate-owned session, whether abandoned before it ever
    connected (the original, still-supported case: the intro screen's
    "end" button, per docs/CURRENT_DECISIONS.md's "Intro screen's end
    control") or ended by the candidate while LIVE (session-finalization-
    contract fix, 2026-09-01: this endpoint used to only flip DB state for
    the pre-connect case and silently do nothing useful for a live
    session -- it now goes through the same _finalize_live_session used by
    the idle-disconnect sweep, which also force-disconnects the LiveKit
    room so a live candidate's audio/video actually stops instead of the
    room and its recording continuing to run with no one home)."""
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

    await finalize_live_session(db, session, target_status="TERMINATED")
    await db.refresh(session)
    return session


@router.post("/{session_id}/consent", response_model=ConsentResponse, status_code=status.HTTP_201_CREATED)
async def record_consent(
    session_id: UUID,
    body: ConsentCreate,
    db: AsyncSession = db_dependency,
    user_id: str = current_user_dependency,
):
    """PR-A: record the candidate's recording/monitoring consent, tied to
    their session. Same ownership-check pattern as terminate_interview.
    Idempotent: a session that already has a consent row returns that
    existing row (200-equivalent data, still 201 the first time) rather
    than erroring or creating a duplicate -- mirrors internal.py's
    create_event/create_message unique-constraint-catch pattern.
    """
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
        raise HTTPException(status_code=403, detail="Not authorized to access this interview session")

    consent = InterviewConsent(
        session_id=session_id,
        disclosure_language=body.disclosure_language,
        disclosure_text=body.disclosure_text,
    )
    db.add(consent)
    try:
        await db.commit()
        await db.refresh(consent)
    except IntegrityError:
        # Idempotent: a second consent for the same session hits the unique
        # constraint -- return the existing row. Any other DB failure
        # propagates (H2-A1: this used to swallow everything).
        await db.rollback()
        existing_result = await db.execute(
            select(InterviewConsent).where(InterviewConsent.session_id == session_id)
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            return existing
        raise

    return consent


@router.get("/{session_id}/transcript", response_model=list[TranscriptEntryResponse])
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


@router.get("/{session_id}/events", response_model=list[SessionEventResponse])
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
