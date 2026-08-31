"""
Admin API endpoints — Phase 4.

All routes are behind Depends(get_current_admin) from Phase 3.
Mutation endpoints enforce DRAFT-only editing; PUBLISHED jobs are read-only.
DELETE /admin/jobs/{id} is restricted to DRAFT jobs (409 on PUBLISHED).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from uuid import UUID
import logging
import secrets

from backend.api.deps import get_current_admin
from backend.db.session import get_db
from backend.core.config import settings
from backend.models.interview import (
    Job,
    InterviewDefinition,
    InterviewSection,
    InterviewQuestion,
    InterviewSession,
    AssessmentCriterion,
    Evaluation,
    Score,
)
from backend.models.profile import CandidateProfile
from backend.services.candidate_profile_service import get_or_create_candidate_profile
from backend.services.guest_jwt_service import mint_guest_jwt
from backend.api.endpoints.livekit import generate_livekit_token, TokenRequest
from backend.schemas.public_apply import PublicRegisterResponse
from backend.schemas.public_invitations import RedeemedSessionInfo
from backend.schemas.admin import (
    JobCreate,
    JobUpdate,
    JobResponse,
    JobDetailResponse,
    InterviewDefinitionUpdate,
    SectionCreate,
    SectionUpdate,
    SectionResponse,
    SectionWithQuestionsResponse,
    QuestionCreate,
    QuestionUpdate,
    QuestionResponse,
    QuestionGenerateRequest,
    validate_question_config,
    validate_section_config,
    CriterionScoreResponse,
    EvaluationDetailResponse,
    JobCandidateRow,
    JobResultsResponse,
    SuggestedOverrideRequest,
    SuggestedOverrideResponse,
    AssessmentCriterionResponse,
    CriteriaToggleRequest,
    JobStatusUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────

async def _get_job_or_404(db: AsyncSession, job_id: UUID) -> Job:
    result = await db.execute(
        select(Job)
        .options(selectinload(Job.definition))
        .where(Job.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


async def _get_section_or_404(db: AsyncSession, section_id: UUID) -> InterviewSection:
    result = await db.execute(
        select(InterviewSection)
        .options(selectinload(InterviewSection.definition).selectinload(InterviewDefinition.job))
        .where(InterviewSection.id == section_id)
    )
    section = result.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    return section


async def _get_question_or_404(db: AsyncSession, question_id: UUID) -> InterviewQuestion:
    result = await db.execute(
        select(InterviewQuestion)
        .options(
            selectinload(InterviewQuestion.section)
            .selectinload(InterviewSection.definition)
            .selectinload(InterviewDefinition.job)
        )
        .where(InterviewQuestion.id == question_id)
    )
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    return question


async def _recompute_duration(db: AsyncSession, definition: InterviewDefinition) -> None:
    """WR-A: InterviewDefinition.duration_minutes is now DERIVED — the sum
    of each section's config.time_budget_minutes — not an admin-set input
    (see docs/section-pacing-architecture.md, CURRENT_DECISIONS.md's
    "Section pacing & waiting room"). Recompute-on-write, not live-read-time
    computation: safe because every section/question mutation is already
    _require_draft-gated (confirmed during WR-A's exploration — nothing can
    change a section after publish today), so a stored value recomputed
    here can never go stale relative to what's actually configured. Missing
    a budget on a section (not yet set) contributes 0, not an error — that
    gap is enforced separately, at publish time, not on every intermediate
    write.

    Queries sections fresh via `db` rather than relying on
    `definition.sections` being eagerly loaded (callers' own SELECTs don't
    all selectinload it) — this also means it correctly sees a change
    already `db.add()`/`db.delete()`d and `db.flush()`ed earlier in the
    SAME transaction, since flush (not commit) is enough for a subsequent
    SELECT in the same session to observe it. Caller must flush() any
    pending section change before calling this, and commit() after.
    """
    result = await db.execute(
        select(InterviewSection.config).where(InterviewSection.definition_id == definition.id)
    )
    definition.duration_minutes = sum(
        (config or {}).get("time_budget_minutes", 0) or 0
        for (config,) in result.all()
    )


def _require_draft(job: Job):
    """Raise 409 if the job is not in DRAFT status."""
    if job.status != "DRAFT":
        raise HTTPException(
            status_code=409,
            detail=f"Job is {job.status}; edits are only allowed while DRAFT",
        )


# ══════════════════════════════════════════════════════════════════════════
#  ADMIN STUB (keep existing ping)
# ══════════════════════════════════════════════════════════════════════════

@router.get("/ping")
async def admin_ping(admin_id: str = Depends(get_current_admin)):
    """Stub route to verify Admin RBAC logic."""
    return {"status": "ok", "admin_id": admin_id}


# ══════════════════════════════════════════════════════════════════════════
#  JOBS
# ══════════════════════════════════════════════════════════════════════════

@router.get("/jobs", response_model=list[JobResponse])
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    result = await db.execute(
        select(Job)
        .options(selectinload(Job.definition))
        .order_by(Job.created_at.desc())
    )
    return result.scalars().all()


@router.post("/jobs", response_model=JobResponse, status_code=201)
async def create_job(
    payload: JobCreate,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    """Create a Job and its 1:1 InterviewDefinition in a single transaction."""
    job = Job(
        title=payload.title,
        description=payload.description,
        seniority=payload.seniority,
        location=payload.location,
        instructions=payload.instructions,
        required_skills=payload.required_skills,
        preferred_skills=payload.preferred_skills,
        responsibilities=payload.responsibilities,
        status="DRAFT",
        language=payload.language.value if payload.language else "en",
    )
    db.add(job)
    await db.flush()  # generate job.id

    definition = InterviewDefinition(
        job_id=job.id,
        duration_minutes=15,
        is_public=False,
    )
    db.add(definition)

    await db.commit()
    await db.refresh(job)
    # Eager-load definition for response
    result = await db.execute(
        select(Job).options(selectinload(Job.definition)).where(Job.id == job.id)
    )
    return result.scalar_one()


@router.get("/jobs/{job_id}", response_model=JobDetailResponse)
async def get_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    result = await db.execute(
        select(Job)
        .options(
            selectinload(Job.definition)
            .selectinload(InterviewDefinition.sections)
            .selectinload(InterviewSection.questions)
        )
        .where(Job.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.patch("/jobs/{job_id}", response_model=JobResponse)
async def update_job(
    job_id: UUID,
    payload: JobUpdate,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    job = await _get_job_or_404(db, job_id)
    _require_draft(job)

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(job, field, value)

    await db.commit()
    await db.refresh(job)
    return job


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    """Delete a job. Will cascade delete definitions, criteria, sessions, and evaluations."""
    job = await _get_job_or_404(db, job_id)
    await db.delete(job)
    await db.commit()
    return None


@router.patch("/jobs/{job_id}/status", response_model=JobResponse)
async def update_job_status(
    job_id: UUID,
    payload: JobStatusUpdate,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    """Change job status (e.g. to PAUSED, DRAFT, PUBLISHED)."""
    job = await _get_job_or_404(db, job_id)
    
    if payload.status.value == job.status:
        return job
        
    if payload.status.value == "DRAFT":
        # Only allow unpublishing if no sessions exist to protect schema integrity
        from backend.models.session import InterviewSession
        stmt = select(func.count(InterviewSession.id)).where(InterviewSession.job_id == job_id)
        result = await db.execute(stmt)
        if result.scalar() > 0:
            raise HTTPException(
                status_code=409, 
                detail="Cannot unpublish a job that has active or completed candidates. Pause it instead."
            )
            
    if payload.status.value == "PUBLISHED":
        # Validate completeness before publishing (reusing publish_job rules)
        sections_result = await db.execute(
            select(InterviewSection)
            .options(selectinload(InterviewSection.questions))
            .where(InterviewSection.definition_id == job.definition.id)
        )
        sections = sections_result.scalars().all()
        empty_sections = [s.section_type for s in sections if not s.questions]
        if empty_sections:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot publish: section(s) with no questions: {', '.join(empty_sections)}",
            )
        unbudgeted_sections = [
            s.section_type for s in sections
            if not (s.config or {}).get("time_budget_minutes")
        ]
        if unbudgeted_sections:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot publish: section(s) with no time budget set: {', '.join(unbudgeted_sections)}",
            )

    job.status = payload.status.value
    await db.commit()
    await db.refresh(job)
    return job


@router.post("/jobs/{job_id}/publish", response_model=JobResponse)
async def publish_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    """Transition a Job from DRAFT to PUBLISHED."""
    job = await _get_job_or_404(db, job_id)
    if job.status != "DRAFT":
        raise HTTPException(status_code=409, detail=f"Job is already {job.status}")

    # Content-completeness check, not an editability rule (that's
    # _require_draft's job in the other direction). A section that exists
    # with zero questions would otherwise publish silently and reach a
    # candidate with nothing to answer. Deliberately narrow: does NOT
    # require at least one section to exist at all.
    sections_result = await db.execute(
        select(InterviewSection)
        .options(selectinload(InterviewSection.questions))
        .where(InterviewSection.definition_id == job.definition.id)
    )
    sections = sections_result.scalars().all()

    empty_sections = [s.section_type for s in sections if not s.questions]
    if empty_sections:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot publish: section(s) with no questions: {', '.join(empty_sections)}",
        )

    # WR-A: time_budget_minutes is optional while a section is being built
    # (mirrors questions being addable after section creation) but required
    # once it's actually going live — a published section with no time
    # budget would derive a 0-minute contribution to duration_minutes and
    # leave WR-C's waiting-room/clock logic with nothing to seed from.
    unbudgeted_sections = [
        s.section_type for s in sections
        if not (s.config or {}).get("time_budget_minutes")
    ]
    if unbudgeted_sections:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot publish: section(s) with no time budget set: {', '.join(unbudgeted_sections)}",
        )

    # STOPGAP LIFTED 2026-08-26, both types, per explicit user go-ahead --
    # see docs/CURRENT_DECISIONS.md and docs/phase9-architecture.md's 9H
    # section. This block existed because 9G's HR authoring UI, 9H's
    # candidate submission UI, and a runtime UI-state bridging bug
    # (build_core_sections()/generate_ui_state()) were all real gaps that
    # would have stranded a candidate mid-interview with no way to answer.
    # All three are now built and live-verified end-to-end for both CODING
    # and MCQ (real published test jobs, real candidate sessions, real
    # submissions, real grading, real dedicated no-avatar visual modes). If
    # a genuine regression in CODING/MCQ runtime or UI support is ever
    # found again, restore an equivalent per-type check here rather than
    # leaving candidates stranded -- do not treat this comment as
    # permission to skip that.

    job.status = "PUBLISHED"
    await db.commit()
    await db.refresh(job)
    return job


# ══════════════════════════════════════════════════════════════════════════
#  INTERVIEW DEFINITION (update only — created automatically with Job)
# ══════════════════════════════════════════════════════════════════════════

@router.patch("/definitions/{definition_id}", response_model=JobResponse)
async def update_definition(
    definition_id: UUID,
    payload: InterviewDefinitionUpdate,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    result = await db.execute(
        select(InterviewDefinition)
        .options(selectinload(InterviewDefinition.job))
        .where(InterviewDefinition.id == definition_id)
    )
    definition = result.scalar_one_or_none()
    if not definition:
        raise HTTPException(status_code=404, detail="InterviewDefinition not found")
    update_data = payload.model_dump(exclude_unset=True)
    
    # Allow toggling `is_public` even if PUBLISHED, but block structural changes like duration
    if definition.job.status != "DRAFT":
        if "duration_minutes" in update_data:
            _require_draft(definition.job)

    for field, value in update_data.items():
        setattr(definition, field, value)

    # Phase 6, Sub-phase 6A: lazily generate the public-link token the
    # moment is_public flips true, if one doesn't already exist. Not tied
    # to Job publish — is_public and PUBLISHED are independent (Flow B
    # requires both, but a job can be published without being public).
    if definition.is_public and not definition.public_access_token:
        definition.public_access_token = secrets.token_urlsafe(24)

    job_id = definition.job_id
    await db.commit()
    # Re-load with definition for response
    result = await db.execute(
        select(Job).options(selectinload(Job.definition)).where(Job.id == job_id)
    )
    return result.scalar_one()


@router.post("/definitions/{definition_id}/test-drive", response_model=PublicRegisterResponse)
async def test_drive_definition(
    definition_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    """
    Creates a dummy InterviewSession for the admin to test the interview flow,
    without creating a JobApplication (so it stays out of HR dashboards).
    """
    result = await db.execute(
        select(InterviewDefinition)
        .options(selectinload(InterviewDefinition.job))
        .where(InterviewDefinition.id == definition_id)
    )
    definition = result.scalar_one_or_none()
    if not definition:
        raise HTTPException(status_code=404, detail="InterviewDefinition not found")
        
    job = definition.job

    # Create or get the dummy admin test profile
    test_email = "admin_tester@path2hire.local"
    profile = await get_or_create_candidate_profile(db, email=test_email, full_name="Admin Tester")
    
    # We deliberately omit application_id to keep it out of candidate results
    session = InterviewSession(
        candidate_profile_id=profile.id,
        job_id=job.id,
        definition_id=definition.id,
        application_id=None,
        role=job.title,
        level=job.seniority or "mid",
        language=job.language,
        status="CREATED",
    )
    db.add(session)
    await db.flush()

    access_token = mint_guest_jwt(str(profile.id), test_email)

    token_response = await generate_livekit_token(
        TokenRequest(session_id=str(session.id)), db, str(profile.id)
    )

    await db.commit()
    await db.refresh(session)

    return PublicRegisterResponse(
        access_token=access_token,
        session=RedeemedSessionInfo(
            id=session.id,
            job_id=session.job_id,
            definition_id=session.definition_id,
            status=session.status,
            created_at=session.created_at,
        ),
        livekit_token=token_response.token,
        livekit_url=token_response.url,
    )



# ══════════════════════════════════════════════════════════════════════════
#  SECTIONS
# ══════════════════════════════════════════════════════════════════════════

@router.post("/sections", response_model=SectionResponse, status_code=201)
async def create_section(
    payload: SectionCreate,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    # Load definition and its parent Job
    result = await db.execute(
        select(InterviewDefinition)
        .options(selectinload(InterviewDefinition.job))
        .where(InterviewDefinition.id == payload.definition_id)
    )
    definition = result.scalar_one_or_none()
    if not definition:
        raise HTTPException(status_code=404, detail="InterviewDefinition not found")
    _require_draft(definition.job)

    try:
        validated_config = validate_section_config(payload.config)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    section = InterviewSection(
        definition_id=payload.definition_id,
        section_type=payload.section_type.value,
        order_index=payload.order_index,
        config=validated_config,
    )
    db.add(section)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Section type {payload.section_type.value} already exists on this definition",
        )
    await _recompute_duration(db, definition)
    await db.commit()
    await db.refresh(section)
    return section


@router.patch("/sections/{section_id}", response_model=SectionResponse)
async def update_section(
    section_id: UUID,
    payload: SectionUpdate,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    section = await _get_section_or_404(db, section_id)
    _require_draft(section.definition.job)

    update_data = payload.model_dump(exclude_unset=True)
    if "config" in update_data:
        try:
            update_data["config"] = validate_section_config(update_data["config"])
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    for field, value in update_data.items():
        setattr(section, field, value)

    if "config" in update_data:
        await db.flush()
        await _recompute_duration(db, section.definition)

    await db.commit()
    await db.refresh(section)
    return section


@router.delete("/sections/{section_id}", status_code=204)
async def delete_section(
    section_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    section = await _get_section_or_404(db, section_id)
    _require_draft(section.definition.job)
    definition = section.definition
    await db.delete(section)
    await db.flush()
    await _recompute_duration(db, definition)
    await db.commit()
    return None


# ══════════════════════════════════════════════════════════════════════════
#  QUESTIONS — manual CRUD
# ══════════════════════════════════════════════════════════════════════════

@router.post(
    "/sections/{section_id}/questions",
    response_model=QuestionResponse,
    status_code=201,
)
async def add_question(
    section_id: UUID,
    payload: QuestionCreate,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    section = await _get_section_or_404(db, section_id)
    _require_draft(section.definition.job)

    # Determine next order_index
    result = await db.execute(
        select(InterviewQuestion)
        .where(InterviewQuestion.section_id == section_id)
        .order_by(InterviewQuestion.order_index.desc())
    )
    last = result.scalars().first()
    next_idx = (last.order_index + 1) if last else 0

    question = InterviewQuestion(
        section_id=section_id,
        order_index=next_idx,
        title=payload.title,
        competency=payload.competency,
        text=payload.text,
        eval_criteria=payload.eval_criteria,
    )

    # Validate config against section type
    try:
        question.config = validate_question_config(section.section_type, payload.config)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    db.add(question)
    await db.commit()
    await db.refresh(question)
    return question


@router.patch("/questions/{question_id}", response_model=QuestionResponse)
async def update_question(
    question_id: UUID,
    payload: QuestionUpdate,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    question = await _get_question_or_404(db, question_id)
    _require_draft(question.section.definition.job)

    update_data = payload.model_dump(exclude_unset=True)

    # Validate config if it's being updated
    if "config" in update_data:
        try:
            update_data["config"] = validate_question_config(
                question.section.section_type, update_data["config"]
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    for field, value in update_data.items():
        setattr(question, field, value)
    await db.commit()
    await db.refresh(question)
    return question


@router.delete("/questions/{question_id}", status_code=204)
async def delete_question(
    question_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    question = await _get_question_or_404(db, question_id)
    _require_draft(question.section.definition.job)
    await db.delete(question)
    await db.commit()
    return None


# ══════════════════════════════════════════════════════════════════════════
#  QUESTIONS — AI generation
# ══════════════════════════════════════════════════════════════════════════

@router.post(
    "/sections/{section_id}/generate-questions",
    response_model=list[QuestionResponse],
    status_code=201,
)
async def generate_questions_for_section(
    section_id: UUID,
    payload: QuestionGenerateRequest,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    """AI-generate questions for a section using the job context."""
    section = await _get_section_or_404(db, section_id)
    _require_draft(section.definition.job)

    job = section.definition.job

    from backend.services.question_generator import generate_questions

    generated = await generate_questions(
        job_title=job.title,
        job_description=job.description,
        seniority=job.seniority,
        required_skills=job.required_skills,
        preferred_skills=job.preferred_skills,
        responsibilities=job.responsibilities,
        location=job.location,
        candidate_instructions=job.instructions,
        section_type=section.section_type,
        section_config=section.config,
        num_questions=payload.num_questions,
    )

    # Determine starting order_index
    result = await db.execute(
        select(InterviewQuestion)
        .where(InterviewQuestion.section_id == section_id)
        .order_by(InterviewQuestion.order_index.desc())
    )
    last = result.scalars().first()
    start_idx = (last.order_index + 1) if last else 0

    created_questions = []
    for i, q in enumerate(generated):
        # Validate config from AI output against section type
        try:
            validated_config = validate_question_config(section.section_type, q.get("config"))
        except ValueError as e:
            raise HTTPException(
                status_code=422,
                detail=f"AI-generated question {i+1} has invalid config: {str(e)}",
            )

        question = InterviewQuestion(
            section_id=section_id,
            order_index=start_idx + i,
            title=q["title"],
            competency=q.get("competency"),
            text=q["text"],
            eval_criteria=q.get("eval_criteria"),
            config=validated_config,
        )
        db.add(question)
        created_questions.append(question)

    await db.commit()
    for q in created_questions:
        await db.refresh(q)

    return created_questions


# ══════════════════════════════════════════════════════════════════════════
#  QUESTIONS — regenerate single question
# ══════════════════════════════════════════════════════════════════════════

@router.post("/questions/{question_id}/regenerate", response_model=QuestionResponse)
async def regenerate_question(
    question_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    """Replace a single question's content with a fresh AI-generated one."""
    question = await _get_question_or_404(db, question_id)
    job = question.section.definition.job
    _require_draft(job)

    from backend.services.question_generator import generate_questions

    generated = await generate_questions(
        job_title=job.title,
        job_description=job.description,
        seniority=job.seniority,
        required_skills=job.required_skills,
        preferred_skills=job.preferred_skills,
        responsibilities=job.responsibilities,
        location=job.location,
        candidate_instructions=job.instructions,
        section_type=question.section.section_type,
        section_config=question.section.config,
        num_questions=1,
    )

    if not generated:
        raise HTTPException(status_code=502, detail="AI generation returned no results")

    new_q = generated[0]
    question.title = new_q["title"]
    question.competency = new_q.get("competency")
    question.text = new_q["text"]
    question.eval_criteria = new_q.get("eval_criteria")

    # Validate config from AI output against section type
    try:
        question.config = validate_question_config(
            question.section.section_type, new_q.get("config")
        )
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=f"AI-regenerated question has invalid config: {str(e)}",
        )

    await db.commit()
    await db.refresh(question)
    return question


# ══════════════════════════════════════════════════════════════════════════
# HR Results Dashboard (Phase 8D)
# ══════════════════════════════════════════════════════════════════════════

@router.get("/interviews/{session_id}/result", response_model=EvaluationDetailResponse)
async def get_candidate_result(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    """Per-candidate detailed result: the legacy final_result JSONB's
    transcript/question_records/technical_submission (read-only, unchanged)
    combined with the normalized Evaluation/Score rows (Phase 8C) in one
    response. Distinct from GET /api/v1/interviews/{id}/result (Plan 11B's
    candidate-access lockdown) -- that endpoint and its access-control logic
    are untouched by this one."""
    result = await db.execute(
        select(InterviewSession)
        .options(selectinload(InterviewSession.profile))
        .where(InterviewSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found.")

    job_title = None
    if session.job_id:
        job_result = await db.execute(select(Job.title).where(Job.id == session.job_id))
        job_title = job_result.scalar_one_or_none()

    final_result = session.final_result or {}

    eval_result = await db.execute(
        select(Evaluation)
        .options(selectinload(Evaluation.scores).selectinload(Score.criterion))
        .where(Evaluation.session_id == session_id)
    )
    evaluation = eval_result.scalar_one_or_none()

    if evaluation is None:
        # Distinct from the 404 above -- the session is real, this is a
        # genuine, non-hypothetical state (8A/8C found real examples): a
        # COMPLETED session whose evaluation write hasn't landed yet, or
        # failed independently of save_completion()'s own final_result write.
        raise HTTPException(
            status_code=409,
            detail="This session has not been evaluated yet (no Evaluation row exists).",
        )

    scores = [
        CriterionScoreResponse(
            criterion_key=s.criterion_key,
            criterion_label=s.criterion.label if s.criterion else None,
            kind=s.criterion.kind if s.criterion else None,
            score=s.score,
            overview=s.overview,
            strengths=s.strengths or [],
            improvements=s.improvements or [],
            evidence_reference=s.evidence_reference,
        )
        for s in evaluation.scores
    ]

    return EvaluationDetailResponse(
        session_id=session.id,
        status=session.status,
        completed_at=session.completed_at,
        candidate_name=session.profile.full_name if session.profile else None,
        candidate_email=session.profile.email if session.profile else None,
        job_title=job_title,
        transcript=final_result.get("transcript") or [],
        question_records=final_result.get("question_records") or [],
        technical_submission=final_result.get("technical_submission") or {},
        overall_score=evaluation.overall_score,
        recommendation=evaluation.recommendation,
        evidence_sufficiency=evaluation.evidence_sufficiency,
        summary=evaluation.summary,
        detailed_overview=evaluation.detailed_overview,
        scores=scores,
        override_suggested=evaluation.override_suggested,
        override_reason=evaluation.override_reason,
    )


@router.get("/jobs/{job_id}/results", response_model=JobResultsResponse)
async def get_job_results(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    """Per-job aggregate stats + candidate list. `suggested` is computed
    per-request from evidence_sufficiency + recommendation (8B mechanism B),
    unless override_suggested is set (Phase 8F — manual override takes
    precedence over computed)."""
    job = await _get_job_or_404(db, job_id)

    result = await db.execute(
        select(InterviewSession, CandidateProfile, Evaluation)
        .outerjoin(CandidateProfile, InterviewSession.candidate_profile_id == CandidateProfile.id)
        .outerjoin(Evaluation, Evaluation.session_id == InterviewSession.id)
        .where(InterviewSession.job_id == job_id)
        .order_by(InterviewSession.created_at.desc())
    )
    rows = result.all()

    floor = settings.SUGGESTED_EVIDENCE_SUFFICIENCY_FLOOR
    completed_count = 0
    in_progress_count = 0
    suggested_count = 0
    candidates: list[JobCandidateRow] = []

    for session, profile, evaluation in rows:
        if session.status == "COMPLETED":
            completed_count += 1
        elif session.status != "TERMINATED":
            in_progress_count += 1

        computed_suggested = bool(
            evaluation
            and evaluation.recommendation == "Hire"
            and evaluation.evidence_sufficiency is not None
            and evaluation.evidence_sufficiency >= floor
        )
        # Phase 8F: manual override takes precedence when set.
        override_val = evaluation.override_suggested if evaluation else None
        suggested = override_val if override_val is not None else computed_suggested
        if suggested:
            suggested_count += 1

        candidates.append(JobCandidateRow(
            session_id=session.id,
            candidate_name=profile.full_name if profile else None,
            candidate_email=profile.email if profile else None,
            status=session.status,
            completed_at=session.completed_at,
            overall_score=evaluation.overall_score if evaluation else None,
            recommendation=evaluation.recommendation if evaluation else None,
            evidence_sufficiency=evaluation.evidence_sufficiency if evaluation else None,
            suggested=suggested,
            override_suggested=override_val,
        ))

    return JobResultsResponse(
        job_id=job.id,
        job_title=job.title,
        total_candidates=len(candidates),
        completed_count=completed_count,
        in_progress_count=in_progress_count,
        suggested_count=suggested_count,
        candidates=candidates,
    )


# ══════════════════════════════════════════════════════════════════════════
# Manual Override (Phase 8F — Part 1)
# ══════════════════════════════════════════════════════════════════════════

@router.patch("/interviews/{session_id}/suggested-override", response_model=SuggestedOverrideResponse)
async def set_suggested_override(
    session_id: UUID,
    payload: SuggestedOverrideRequest,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    """Manually override a candidate's computed 'suggested' status.
    override_suggested=True/False sets an explicit override;
    override_suggested=None clears it back to 'use computed value'.
    Both the computed and overridden values remain visible/auditable."""
    eval_result = await db.execute(
        select(Evaluation).where(Evaluation.session_id == session_id)
    )
    evaluation = eval_result.scalar_one_or_none()
    if evaluation is None:
        # Check whether the session itself exists.
        sess_result = await db.execute(
            select(InterviewSession.id).where(InterviewSession.id == session_id)
        )
        if sess_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Interview session not found.")
        raise HTTPException(
            status_code=409,
            detail="This session has not been evaluated yet (no Evaluation row exists).",
        )

    evaluation.override_suggested = payload.override_suggested
    evaluation.override_reason = payload.reason
    await db.commit()
    await db.refresh(evaluation)

    # Compute the "would-be suggested" value so the UI can show both.
    floor = settings.SUGGESTED_EVIDENCE_SUFFICIENCY_FLOOR
    computed_suggested = bool(
        evaluation.recommendation == "Hire"
        and evaluation.evidence_sufficiency is not None
        and evaluation.evidence_sufficiency >= floor
    )

    return SuggestedOverrideResponse(
        session_id=session_id,
        override_suggested=evaluation.override_suggested,
        override_reason=evaluation.override_reason,
        computed_suggested=computed_suggested,
    )


# ══════════════════════════════════════════════════════════════════════════
# Assessment Criteria Authoring (Phase 8E)
# ══════════════════════════════════════════════════════════════════════════

@router.get("/jobs/{job_id}/criteria", response_model=list[AssessmentCriterionResponse])
async def get_job_criteria(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    """Returns the behavioral assessment criteria for this job.
    If job-scoped rows exist, returns those. Otherwise derives the state
    from the template tier (all templates enabled by default for display
    purposes — this mirrors _resolve_criteria_for_job's fallback)."""
    job = await _get_job_or_404(db, job_id)

    # Check for job-scoped rows first.
    result = await db.execute(
        select(AssessmentCriterion).where(
            AssessmentCriterion.job_id == job_id,
            AssessmentCriterion.section_id.is_(None),
        )
    )
    job_criteria = list(result.scalars().all())

    if job_criteria:
        return [
            AssessmentCriterionResponse(
                key=c.key, label=c.label, kind=c.kind,
                enabled=c.enabled, guidance_text=c.guidance_text,
                source=c.source,
            )
            for c in job_criteria
        ]

    # No job-scoped rows yet — return templates with enabled=True (the
    # default state before any explicit configuration).
    template_result = await db.execute(
        select(AssessmentCriterion).where(
            AssessmentCriterion.job_id.is_(None),
            AssessmentCriterion.section_id.is_(None),
        )
    )
    templates = list(template_result.scalars().all())
    return [
        AssessmentCriterionResponse(
            key=t.key, label=t.label, kind=t.kind,
            enabled=True, guidance_text=t.guidance_text,
            source="TEMPLATE",
        )
        for t in templates
    ]


@router.put("/jobs/{job_id}/criteria", response_model=list[AssessmentCriterionResponse])
async def update_job_criteria(
    job_id: UUID,
    payload: CriteriaToggleRequest,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    """Set which behavioral criteria are enabled for this job.
    Upserts job-scoped AssessmentCriterion rows cloned from templates.
    DRAFT-only — 409 on a published job, matching every other mutation
    endpoint's existing _require_draft() pattern."""
    job = await _get_job_or_404(db, job_id)
    if job.status != "DRAFT":
        raise HTTPException(
            status_code=409,
            detail="Cannot modify assessment criteria on a published job.",
        )

    # Load all behavioral templates.
    template_result = await db.execute(
        select(AssessmentCriterion).where(
            AssessmentCriterion.job_id.is_(None),
            AssessmentCriterion.section_id.is_(None),
            AssessmentCriterion.kind == "behavioral",
        )
    )
    templates = list(template_result.scalars().all())

    # Delete existing job-scoped behavioral criteria and re-insert.
    # (Simpler and safer than per-row upserts for a small, bounded set.)
    from sqlalchemy import delete
    await db.execute(
        delete(AssessmentCriterion).where(
            AssessmentCriterion.job_id == job_id,
            AssessmentCriterion.section_id.is_(None),
            AssessmentCriterion.kind == "behavioral",
        )
    )

    # Clone from templates, respecting the enabled_keys list.
    new_rows = []
    for t in templates:
        row = AssessmentCriterion(
            job_id=job_id,
            section_id=None,
            key=t.key,
            label=t.label,
            kind=t.kind,
            enabled=(t.key in payload.enabled_keys),
            guidance_text=t.guidance_text,
            source="TEMPLATE",
        )
        db.add(row)
        new_rows.append(row)

    await db.commit()

    return [
        AssessmentCriterionResponse(
            key=r.key, label=r.label, kind=r.kind,
            enabled=r.enabled, guidance_text=r.guidance_text,
            source=r.source,
        )
        for r in new_rows
    ]
