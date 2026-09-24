"""
Admin API endpoints — Phase 4.

All routes are behind Depends(get_current_admin) from Phase 3.
Mutation endpoints enforce DRAFT-only editing; PUBLISHED jobs are read-only.
DELETE /admin/jobs/{id} is restricted to DRAFT jobs (409 on PUBLISHED).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from uuid import UUID
import logging
import secrets

from backend.api.deps import get_current_admin
from backend.db.session import get_db
from backend.core.config import settings
from backend.providers.factory import get_recordings_storage, get_task_queue
from backend.models.interview import (
    Job,
    InterviewDefinition,
    InterviewSection,
    InterviewQuestion,
    InterviewSession,
    InterviewEvent,
    AssessmentCriterion,
    Evaluation,
)
from backend.models.profile import CandidateProfile
from backend.services.candidate_profile_service import get_or_create_candidate_profile
from backend.services.guest_jwt_service import mint_guest_jwt
from backend.services.sessions.room_token import issue_candidate_room_token
from backend.models import audit as audit_actions
from backend.services.audit import record_admin_action
from backend.services.data_deletion import delete_candidate, delete_session_artifacts
from backend.services.publish_rules import assert_definition_publishable
# H2-F: the four AI endpoints queue a Task; the generator calls themselves
# live in services/tasks/handlers.py, which the worker runs.
from backend.services.tasks import handlers
from backend.services.results.candidate_result import (
    INTEGRITY_EVENT_TYPES,
    build_candidate_result,
)
from backend.schemas.public_apply import PublicRegisterResponse
from backend.schemas.public_invitations import RedeemedSessionInfo
from backend.schemas.admin import (
    AdminPingResponse,
    TaskAcceptedResponse,
    TaskResponse,
    JobCreate,
    JobUpdate,
    JobResponse,
    JobDetailResponse,
    InterviewDefinitionUpdate,
    SectionCreate,
    SectionUpdate,
    SectionResponse,
    QuestionCreate,
    QuestionUpdate,
    QuestionResponse,
    QuestionGenerateRequest,
    validate_question_config,
    validate_section_config,
    default_verbal_section_config,
    SectionType,
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


async def _delete_recording_object(storage_path: str | None) -> bool:
    """Delete a session's recording object from R2 (2026-09-14, added for
    candidate deletion). Returns True if the object was deleted or there
    was nothing to delete, False if a delete was attempted and failed.

    Deliberately mirrors _presign_recording_url's construction of the
    client (same credentials, same path addressing style) rather than
    introducing a second, subtly-different R2 client.

    Never raises: a failed R2 delete must not roll back or block the
    database delete the caller has already decided to perform -- the
    alternative (500 the request and leave the row in place) is strictly
    worse for the admin, who then can't remove the candidate at all. The
    caller logs/surfaces the discrepancy instead; same "a
    recording-subsystem failure must never block the core flow" principle
    the rest of this module already applies.
    """
    if not storage_path:
        return True
    storage = get_recordings_storage()
    if not storage.configured:
        # Recording storage not configured in this environment -- there is
        # no object to delete here, which is a real, tolerated state (same
        # as presign's).
        return True
    try:
        await storage.delete(storage_path)
        return True
    except Exception:  # noqa: BLE001 -- best-effort by contract: a failed object delete must not block the DB delete
        logger.exception("Failed to delete recording object %s", storage_path)
        return False


# ══════════════════════════════════════════════════════════════════════════
#  ADMIN STUB (keep existing ping)
# ══════════════════════════════════════════════════════════════════════════

@router.get("/ping", response_model=AdminPingResponse)
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
    limit: int | None = Query(default=None, ge=1, le=500, description="Page size; omitted = all (today's behaviour)."),
    offset: int = Query(default=0, ge=0),
):
    stmt = (
        select(Job)
        .options(selectinload(Job.definition))
        .order_by(Job.created_at.desc())
        .offset(offset)
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    result = await db.execute(stmt)
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
    record_admin_action(
        db, actor_id=admin_id, action=audit_actions.JOB_DELETED, target_type="job", target_id=str(job_id),
        details={"title": job.title, "status": job.status},
    )
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
        # Only allow unpublishing if no sessions exist to protect schema integrity.
        # (H2-A1: this imported a non-existent `backend.models.session` and an
        # unimported `func`, so every unpublish attempt 500'd.)
        stmt = select(func.count(InterviewSession.id)).where(InterviewSession.job_id == job_id)
        result = await db.execute(stmt)
        if result.scalar() > 0:
            raise HTTPException(
                status_code=409,
                detail="Cannot unpublish a job that has active or completed candidates. Pause it instead."
            )

    if payload.status.value == "PUBLISHED":
        # Same completeness rules as publish_job (services/publish_rules.py).
        await assert_definition_publishable(db, job.definition.id)

    previous_status = job.status
    job.status = payload.status.value
    record_admin_action(
        db, actor_id=admin_id, action=audit_actions.JOB_STATUS_CHANGED, target_type="job",
        target_id=str(job_id), details={"from": previous_status, "to": job.status},
    )
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

    # Content-completeness rules live in services/publish_rules.py (H2-A2)
    # -- one implementation for this route and update_job_status.
    await assert_definition_publishable(db, job.definition.id)

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
    record_admin_action(
        db, actor_id=admin_id, action=audit_actions.JOB_PUBLISHED, target_type="job",
        target_id=str(job_id), details={"title": job.title},
    )
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


@router.post("/definitions/{definition_id}/generate-invitation-message",
             response_model=TaskAcceptedResponse, status_code=202)
async def generate_invitation_message_for_definition(
    definition_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    """Queue an AI-drafted invitation subject/body for CandidateAccess.tsx's
    composer -- the "Regenerate" action (H2-F: 202 + poll).

    Purely generative: nothing here is persisted as a domain object and
    this never sends anything (CURRENT_DECISIONS.md's P1, email provider
    still unresolved). The draft is the task's `result` -- which is also
    the fix: inline, a browser timeout lost the generated draft outright.
    """
    definition = (
        await db.execute(
            select(InterviewDefinition).where(InterviewDefinition.id == definition_id)
        )
    ).scalar_one_or_none()
    if not definition:
        raise HTTPException(status_code=404, detail="InterviewDefinition not found")

    task = await get_task_queue().enqueue(
        handlers.GENERATE_INVITATION_MESSAGE,
        {"definition_id": str(definition_id)},
        requested_by=admin_id,
    )
    return TaskAcceptedResponse(task_id=task.id, kind=task.kind, status=task.status)


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
    profile = await get_or_create_candidate_profile(
        db, email=settings.ADMIN_TEST_CANDIDATE_EMAIL, full_name=settings.ADMIN_TEST_CANDIDATE_NAME
    )

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

    access_token = mint_guest_jwt(str(profile.id), settings.ADMIN_TEST_CANDIDATE_EMAIL)

    issued = await issue_candidate_room_token(session, str(profile.id))

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
        livekit_token=issued.token,
        livekit_url=issued.url,
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

    # Background subsection (docs/verbal-background-subsection-plan.md §2):
    # a new VERBAL section starts with the CV-grounded background ON, with
    # the plan's defaults. Only when the caller sent no config at all -- an
    # explicit config (even one without these keys) is respected as-is.
    if validated_config is None and payload.section_type == SectionType.VERBAL:
        validated_config = default_verbal_section_config()

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
    response_model=TaskAcceptedResponse,
    status_code=202,
)
async def generate_questions_for_section(
    section_id: UUID,
    payload: QuestionGenerateRequest,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    """Queue AI question generation for a section (H2-F).

    Answers 202 with a task id; the work runs in the backend's task worker
    and the caller polls GET /admin/tasks/{task_id}. Before H2-F this ran
    inline: a Groq call can take longer than the browser's 30s timeout, so
    the admin saw a failure while the questions were in fact written.
    The 404/409 checks stay here so a bad request still fails immediately.
    """
    section = await _get_section_or_404(db, section_id)
    _require_draft(section.definition.job)

    task = await get_task_queue().enqueue(
        handlers.GENERATE_QUESTIONS,
        {"section_id": str(section_id), "num_questions": payload.num_questions},
        requested_by=admin_id,
    )
    return TaskAcceptedResponse(task_id=task.id, kind=task.kind, status=task.status)


# ══════════════════════════════════════════════════════════════════════════
#  QUESTIONS — regenerate single question
# ══════════════════════════════════════════════════════════════════════════

@router.post("/questions/{question_id}/regenerate", response_model=TaskAcceptedResponse, status_code=202)
async def regenerate_question(
    question_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    """Queue a fresh AI-generated replacement for one question (H2-F: 202 +
    poll, see generate_questions_for_section)."""
    question = await _get_question_or_404(db, question_id)
    _require_draft(question.section.definition.job)

    task = await get_task_queue().enqueue(
        handlers.REGENERATE_QUESTION,
        {"question_id": str(question_id)},
        requested_by=admin_id,
    )
    return TaskAcceptedResponse(task_id=task.id, kind=task.kind, status=task.status)


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
    return await build_candidate_result(db, session_id)


@router.delete("/interviews/{session_id}", status_code=204)
async def delete_interview_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    """Delete one candidate's interview session from a job's results
    (2026-09-14). Hard delete, matching delete_job's existing precedent in
    this module -- the ORM relationships on InterviewSession are already
    declared cascade="all, delete-orphan", so this removes the session's
    messages, events, checkpoints, consent, configuration, and its
    Evaluation (and that Evaluation's Scores) along with it. There is no
    undo.

    Deliberately scoped to the SESSION, not the person: the
    CandidateProfile and any JobApplication/InterviewInvitation rows are
    left intact, because those are shared with (and meaningful to) other
    jobs the same candidate may have applied to -- deleting a result from
    one job's dashboard must not silently erase that candidate everywhere.

    The R2 recording object is deleted too, so this is a real deletion of
    the candidate's interview rather than one that leaves their video
    sitting in storage unreferenced. A failed R2 delete does NOT fail the
    request (see _delete_recording_object's docstring): the row still goes,
    and the orphaned object is logged for manual cleanup -- refusing to
    delete the row because storage misbehaved would leave the admin unable
    to remove the candidate at all.
    """
    result = await db.execute(
        select(InterviewSession).where(InterviewSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found.")

    # Captured BEFORE the delete/commit -- reading an ORM attribute after
    # commit expires it and forces a lazy-load outside an async-safe
    # context (the MissingGreenlet bug class this module has hit before).
    storage_path = session.recording_storage_path
    candidate_profile_id = str(session.candidate_profile_id)

    # H5-C: the recording goes through the shared deletion service, which
    # the candidate-wide delete and the purge job also use, so there is one
    # implementation of "remove the objects that belong to this".
    report = await delete_session_artifacts(session)

    record_admin_action(
        db, actor_id=admin_id, action=audit_actions.SESSION_DELETED, target_type="session",
        target_id=str(session_id),
        details={"candidate_profile_id": candidate_profile_id, "status": session.status, **report.as_details()},
    )
    await db.delete(session)
    await db.commit()

    if not report.complete:
        logger.error(
            "Session %s deleted, but its recording object %s could not be removed from R2 "
            "and is now orphaned -- manual cleanup required.",
            session_id, storage_path,
        )
    return None


@router.delete("/candidates/{profile_id}", status_code=204)
async def delete_candidate_completely(
    profile_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    """Erase a person: every interview they sat, every recording, every CV,
    and the profile row itself (H5-C).

    This is the counterpart to DELETE /admin/interviews/{id}, which removes
    one interview and deliberately leaves the person intact because a
    profile is shared across every job they applied to. Until this
    endpoint existed there was no way to honour "delete my data" at all --
    `ResumeService.delete_object` had no caller, so a CV uploaded to
    Supabase Storage was never removed by anything.

    Object storage is best effort and the database is not: a failed object
    delete is reported in the audit entry as an orphan needing manual
    cleanup, rather than aborting the deletion and leaving the admin
    unable to remove the person. There is no undo.
    """
    profile, report = await delete_candidate(db, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Candidate profile not found.")

    record_admin_action(
        db, actor_id=admin_id, action=audit_actions.CANDIDATE_DELETED, target_type="candidate",
        target_id=str(profile_id), details={"email": profile.email, **report.as_details()},
    )
    await db.commit()

    if not report.complete:
        logger.error(
            "Candidate %s deleted, but %d object(s) could not be removed from storage and are "
            "now orphaned -- manual cleanup required: %s",
            profile_id, len(report.orphaned), report.orphaned,
        )
    return None


@router.post("/interviews/{session_id}/regenerate-evaluation",
             response_model=TaskAcceptedResponse, status_code=202)
async def regenerate_evaluation(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(get_current_admin),
):
    """Queue evaluation regeneration (2026-09-03, see CURRENT_DECISIONS.md's
    "Evaluation regeneration for placeholder sessions" entry): HR-triggered,
    on-demand -- generates a real evaluation for a session stuck on the
    generic placeholder row, using whatever real evidence exists.
    Deliberately NOT restricted to COMPLETED sessions -- a TERMINATED
    (early-ended) session is explicitly eligible, evaluated honestly from
    partial evidence (evidence_sufficiency exists precisely to flag this).

    H2-F: 202 + poll. The trigger is unchanged (one session, HR's click);
    only the waiting moved off the HTTP connection. When the task
    succeeds the page re-reads GET /admin/interviews/{id}/result.
    """
    result = await db.execute(
        select(InterviewSession).where(InterviewSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found.")

    if session.status not in ("COMPLETED", "TERMINATED"):
        raise HTTPException(
            status_code=409,
            detail="Cannot generate an evaluation for a session that hasn't ended yet.",
        )

    task = await get_task_queue().enqueue(
        handlers.REGENERATE_EVALUATION,
        {"session_id": str(session_id)},
        requested_by=admin_id,
    )
    return TaskAcceptedResponse(task_id=task.id, kind=task.kind, status=task.status)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: UUID,
    admin_id: str = Depends(get_current_admin),
):
    """Poll a queued task (H2-F). SUCCEEDED carries the handler's `result`;
    FAILED carries `error` + `error_code` -- the same message the inline
    version used to return as a 4xx/5xx body."""
    task = await get_task_queue().get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse(
        id=task.id, kind=task.kind, status=task.status, result=task.result,
        error=task.error, error_code=task.error_code, attempts=task.attempts,
        created_at=task.created_at, started_at=task.started_at, finished_at=task.finished_at,
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

    # One extra query for the whole job, not one per candidate: which of
    # these sessions have at least one integrity event at all (option A --
    # any event flags the candidate, no severity/count threshold, per the
    # confirmed decision). Avoids an N+1 -- this list endpoint can list
    # dozens of candidates and should stay cheap column reads plus this one
    # aggregate, not a per-row query.
    session_ids = [session.id for session, _, _ in rows]
    flagged_session_ids: set = set()
    if session_ids:
        flagged_result = await db.execute(
            select(InterviewEvent.session_id)
            .where(
                InterviewEvent.session_id.in_(session_ids),
                InterviewEvent.event_type.in_(INTEGRITY_EVENT_TYPES),
            )
            .distinct()
        )
        flagged_session_ids = set(flagged_result.scalars().all())

    floor = settings.SUGGESTED_EVIDENCE_SUFFICIENCY_FLOOR
    completed_count = 0
    in_progress_count = 0
    suggested_count = 0
    flagged_count = 0
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

        is_flagged = session.id in flagged_session_ids
        if is_flagged:
            flagged_count += 1

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
            flagged_for_review=is_flagged,
        ))

    return JobResultsResponse(
        job_id=job.id,
        job_title=job.title,
        total_candidates=len(candidates),
        completed_count=completed_count,
        in_progress_count=in_progress_count,
        suggested_count=suggested_count,
        flagged_count=flagged_count,
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
    record_admin_action(
        db, actor_id=admin_id, action=audit_actions.EVALUATION_OVERRIDDEN, target_type="evaluation",
        target_id=str(session_id),
        details={"override_suggested": payload.override_suggested, "reason": payload.reason},
    )
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
    await _get_job_or_404(db, job_id)          # 404 guard; the row itself is not needed here

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
                source=c.source, weight=c.weight,
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
            source="TEMPLATE", weight=t.weight,
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

    # Clone from templates, respecting each entry's enabled/weight setting.
    # A template key not present in payload.criteria at all stays disabled
    # at the default weight (5) -- matches the old enabled_keys behavior's
    # "not in the list = disabled" convention.
    #
    # Bug fix (2026-09-02): the response used to be built AFTER
    # `db.commit()` by reading attributes back off the just-added ORM
    # objects (`r.key`, `r.label`, ...). Committing expires every attribute
    # on those objects by default (SQLAlchemy's expire_on_commit), so that
    # later read silently becomes a lazy-load -- which async SQLAlchemy
    # can't do outside an active greenlet context, and raised
    # `MissingGreenlet: greenlet_spawn has not been called` on every save.
    # Fix: build the response payload from the values already in hand
    # (`t`/`setting`) during the same loop that builds the rows, before
    # commit -- never re-reading attributes off a committed object.
    settings_by_key = {c.key: c for c in payload.criteria}
    response_rows = []
    for t in templates:
        setting = settings_by_key.get(t.key)
        enabled = setting.enabled if setting else False
        weight = setting.weight if setting else 5
        db.add(AssessmentCriterion(
            job_id=job_id,
            section_id=None,
            key=t.key,
            label=t.label,
            kind=t.kind,
            enabled=enabled,
            guidance_text=t.guidance_text,
            source="TEMPLATE",
            weight=weight,
        ))
        response_rows.append(AssessmentCriterionResponse(
            key=t.key, label=t.label, kind=t.kind,
            enabled=enabled, guidance_text=t.guidance_text,
            source="TEMPLATE", weight=weight,
        ))

    await db.commit()

    return response_rows
