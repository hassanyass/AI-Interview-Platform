"""
Internal persistence API for agent-to-backend communication.
Protected by AGENT_API_SECRET — never exposed to the frontend.
"""
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Header, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.api.deps import bind_session_id_from_path, db_dependency
from backend.core.config import settings
from backend.models.interview import (
    InterviewSession, InterviewDefinition, InterviewSection,
    InterviewMessage, InterviewEvent, InterviewCheckpoint,
)
from backend.models.profile import CandidateProfile
from backend.services.sessions.finalization import (
    ensure_evaluation_placeholder as _ensure_evaluation_placeholder,
    stop_recording_egress as _stop_recording_egress,
)
from backend.services.evaluations.upsert import (
    resolve_criteria_for_job as _resolve_criteria_for_job,
    upsert_evaluation as _upsert_evaluation,
)
from backend.schemas.persistence import (
    MessageCreate, MessageResponse,
    EventCreate, EventResponse,
    CheckpointCreate, CheckpointResponse,
    StatusUpdate, SessionLoadResponse,
    QuestionPayload, SectionPayload,
    CriterionPayload, EvaluationSubmit,
)

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(bind_session_id_from_path)])

VALID_STATUSES = {"CREATED", "IN_PROGRESS", "DISCONNECTED", "COMPLETED", "TERMINATED"}
VALID_TRANSITIONS = {
    "CREATED": {"IN_PROGRESS"},
    "IN_PROGRESS": {"DISCONNECTED", "COMPLETED", "TERMINATED"},
    "DISCONNECTED": {"IN_PROGRESS", "TERMINATED"},
    "COMPLETED": set(),
    "TERMINATED": set(),
}

# Agent lease duration — agent must renew within this window
# (settings.AGENT_LEASE_MINUTES; read at call time so tests can tune it).
def _agent_lease_duration() -> timedelta:
    return timedelta(minutes=settings.AGENT_LEASE_MINUTES)


# ─── Agent Auth Dependency ─────────────────────────────────────────────────────

async def verify_agent_secret(x_agent_secret: str = Header(...)):
    """Validates the internal AGENT_API_SECRET header."""
    if not settings.AGENT_API_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent API secret is not configured on the server.",
        )
    if x_agent_secret != settings.AGENT_API_SECRET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid agent API secret.",
        )


agent_auth = Depends(verify_agent_secret)


# ─── Helper ────────────────────────────────────────────────────────────────────

async def _get_session(db: AsyncSession, session_id: UUID) -> InterviewSession:
    result = await db.execute(
        select(InterviewSession).where(InterviewSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found.")
    return session


# ─── Load Session (for agent bootstrap / recovery) ────────────────────────────

@router.get(
    "/{session_id}/load",
    response_model=SessionLoadResponse,
    dependencies=[agent_auth],
)
async def load_session_for_agent(
    session_id: UUID,
    agent_id: str = Query(...),
    db: AsyncSession = db_dependency,
):
    """
    Load interview session data for agent bootstrap.
    Acquires agent lease if the session is eligible.
    """
    result = await db.execute(
        select(InterviewSession)
        .options(selectinload(InterviewSession.configuration))
        .where(InterviewSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found.")

    # Check if session is in a resumable state
    if session.status in ("COMPLETED", "TERMINATED"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session is already {session.status} and cannot be resumed.",
        )

    # Check agent lease — prevent two agents from controlling the same session
    now = datetime.now(timezone.utc)
    if (
        session.active_agent_id
        and session.active_agent_id != agent_id
        and session.agent_lease_expires_at
        and session.agent_lease_expires_at > now
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another agent is currently controlling this session.",
        )

    # Acquire lease
    session.active_agent_id = agent_id
    session.agent_lease_expires_at = now + _agent_lease_duration()

    # Load candidate profile
    profile_result = await db.execute(
        select(CandidateProfile).where(
            CandidateProfile.id == session.candidate_profile_id
        )
    )
    profile = profile_result.scalar_one_or_none()
    candidate_profile = {}
    if profile:
        candidate_profile = {
            "full_name": profile.full_name,
            "email": profile.email,
            "education": profile.education,
            "years_of_experience": profile.years_of_experience,
            "skills": profile.skills,
            "programming_languages": profile.programming_languages,
            "frameworks": profile.frameworks,
            "projects": profile.projects,
            "professional_title": profile.professional_title,
            "recommended_level": profile.recommended_level,
            "confirmed_level": profile.confirmed_level,
        }

    # Load latest checkpoint
    cp_result = await db.execute(
        select(InterviewCheckpoint)
        .where(InterviewCheckpoint.session_id == session_id)
        .order_by(InterviewCheckpoint.created_at.desc())
        .limit(1)
    )
    latest_checkpoint = cp_result.scalar_one_or_none()

    # Load recent messages for conversation context restoration
    msg_result = await db.execute(
        select(InterviewMessage)
        .where(InterviewMessage.session_id == session_id)
        .order_by(InterviewMessage.sequence_number.desc())
        .limit(20)
    )
    recent_messages = [
        {
            "id": m.id,
            "session_id": m.session_id,
            "sequence_number": m.sequence_number,
            "speaker": m.speaker,
            "text": m.text,
            "phase": m.phase,
            "metadata": m.metadata_,
            "created_at": m.created_at,
        }
        for m in reversed(msg_result.scalars().all())
    ]

    config = session.configuration

    # ─── B2B ordered core-question sections (Phase 7D) ──────────────────────
    # Additive: only populated when the session was created through the
    # Job -> InterviewDefinition -> Invitation/public-apply path. Legacy
    # (InterviewConfiguration-sourced) sessions get an empty `sections` list
    # and keep sourcing job_description/duration_minutes exactly as before.
    sections: list[SectionPayload] = []
    job_description = config.job_description if config else None
    duration_minutes = config.duration if config else 15

    if session.definition_id:
        definition_result = await db.execute(
            select(InterviewDefinition)
            .options(
                selectinload(InterviewDefinition.sections).selectinload(InterviewSection.questions),
                selectinload(InterviewDefinition.job),
            )
            .where(InterviewDefinition.id == session.definition_id)
        )
        definition = definition_result.scalar_one_or_none()
        if definition:
            # B2B sessions never have an InterviewConfiguration row (see
            # public_apply.py / public_invitations.py) — source these from
            # the Job/InterviewDefinition instead of falling back to the
            # legacy 15-minute/no-JD defaults above.
            job_description = definition.job.description if definition.job else None
            duration_minutes = definition.duration_minutes
            for db_section in definition.sections:
                sections.append(SectionPayload(
                    section_type=db_section.section_type,
                    # WR-A: defensive .get, not direct indexing — a
                    # section's config can legitimately be None (JSONB
                    # null, not just SQL NULL — see docs/section-pacing-
                    # architecture.md item 1's flag) for a session created
                    # before WR-A shipped, or a legacy definition.
                    time_budget_minutes=(db_section.config or {}).get("time_budget_minutes"),
                    include_background=bool((db_section.config or {}).get("include_background", False)),
                    background_question_count=(db_section.config or {}).get("background_question_count"),
                    background_time_budget_minutes=(db_section.config or {}).get("background_time_budget_minutes"),
                    questions=[
                        QuestionPayload(
                            id=str(q.id),
                            order_index=q.order_index,
                            title=q.title,
                            competency=q.competency,
                            text=q.text,
                            eval_criteria=q.eval_criteria,
                            config=q.config,
                        )
                        for q in db_section.questions
                    ],
                ))

    # Phase 8C: resolved assessment criteria for this session's job.
    resolved_criteria = await _resolve_criteria_for_job(db, session.job_id)
    criteria = [
        CriterionPayload(
            key=c.key,
            label=c.label,
            kind=c.kind,
            guidance_text=c.guidance_text,
            section_id=str(c.section_id) if c.section_id else None,
        )
        for c in resolved_criteria
    ]

    response = SessionLoadResponse(
        session_id=session.id,
        candidate_profile_id=session.candidate_profile_id,
        role=session.role,
        level=session.level,
        language=session.language,
        status=session.status,
        started_at=session.started_at,
        job_description=job_description,
        duration_minutes=duration_minutes,
        thinking_time=config.thinking_time if config else 60,
        candidate_profile=candidate_profile,
        sections=sections,
        criteria=criteria,
        latest_checkpoint=latest_checkpoint,
        recent_messages=recent_messages,
        active_agent_id=session.active_agent_id,
        agent_lease_expires_at=session.agent_lease_expires_at,
    )

    await db.commit()

    return response


# ─── Renew Agent Lease ────────────────────────────────────────────────────────

@router.post(
    "/{session_id}/renew-lease",
    dependencies=[agent_auth],
)
async def renew_agent_lease(
    session_id: UUID,
    agent_id: str = Query(...),
    db: AsyncSession = db_dependency,
):
    session = await _get_session(db, session_id)
    if session.active_agent_id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You do not hold the lease for this session.",
        )
    now = datetime.now(timezone.utc)
    new_expiry = now + _agent_lease_duration()
    session.agent_lease_expires_at = new_expiry
    await db.commit()
    # Audit fix (2026-08-27): db.commit() expires the ORM instance's
    # attributes by default, so reading session.agent_lease_expires_at
    # after commit forces a lazy-refresh from the DB outside an
    # async-safe context -> sqlalchemy.exc.MissingGreenlet, every call.
    # Same bug class as Phase 3/6A/6B's commit-then-read-ORM-attribute
    # mistake — fixed the same way: capture the value into a local
    # BEFORE commit and return that, never the (now-expired) ORM attribute.
    return {"status": "renewed", "expires_at": new_expiry.isoformat()}


# ─── Status Update ─────────────────────────────────────────────────────────────

@router.patch(
    "/{session_id}/status",
    dependencies=[agent_auth],
)
async def update_session_status(
    session_id: UUID,
    body: StatusUpdate,
    db: AsyncSession = db_dependency,
):
    session = await _get_session(db, session_id)

    current = session.status
    target = body.status

    if target not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {target}")

    allowed = VALID_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from {current} to {target}.",
        )

    session.status = target

    if target == "IN_PROGRESS" and not session.started_at:
        session.started_at = datetime.now(timezone.utc)
    if target == "IN_PROGRESS" and current == "DISCONNECTED":
        # Session-finalization-contract fix (2026-09-01): a genuine resume
        # clears the disconnect clock so the idle-auto-finalize sweep
        # doesn't later act on a stale timestamp from a disconnect the
        # candidate already recovered from.
        session.disconnected_at = None
    elif target == "DISCONNECTED":
        session.disconnected_at = datetime.now(timezone.utc)
    elif target in ("COMPLETED", "TERMINATED"):
        if not session.completed_at:
            session.completed_at = datetime.now(timezone.utc)
        if target == "COMPLETED" and body.final_result is not None:
            session.final_result = body.final_result
        # Release agent lease
        session.active_agent_id = None
        session.agent_lease_expires_at = None
        session.disconnected_at = None
        # Session-finalization-contract fix (2026-09-01): guarantee an
        # Evaluation row exists for every session reaching a terminal
        # status through the agent's own graceful path too -- backstops
        # the case this endpoint's own existing comment already named
        # ("Completion must not be lost because room teardown raced a
        # final persistence request... the next recovery path can retry")
        # but that no actual recovery path implemented, until now.
        await _ensure_evaluation_placeholder(db, session.id)

    await db.commit()

    # PR-C (docs/proctoring-architecture.md): stop the recording on real
    # completion/termination -- this is the one narrow, explicitly
    # signed-off touch to this frozen endpoint. Only these two targets
    # (not DISCONNECTED, which may still resume) stop the recording, same
    # gating as the rest of this branch above.
    if target in ("COMPLETED", "TERMINATED") and session.recording_egress_id:
        await _stop_recording_egress(session.recording_egress_id)

    return {"session_id": str(session_id), "status": target}


# ─── Messages ──────────────────────────────────────────────────────────────────

@router.post(
    "/{session_id}/messages",
    response_model=MessageResponse,
    dependencies=[agent_auth],
    status_code=status.HTTP_201_CREATED,
)
async def create_message(
    session_id: UUID,
    body: MessageCreate,
    db: AsyncSession = db_dependency,
):
    await _get_session(db, session_id)

    msg = InterviewMessage(
        session_id=session_id,
        sequence_number=body.sequence_number,
        speaker=body.speaker,
        text=body.text,
        phase=body.phase,
        metadata_=body.metadata,
    )
    db.add(msg)
    try:
        await db.commit()
        await db.refresh(msg)
    except IntegrityError:
        await db.rollback()
        # Idempotency: unique (session_id, sequence_number) violated -> return
        # the existing row. Other DB failures propagate (H2-A1).
        result = await db.execute(
            select(InterviewMessage).where(
                InterviewMessage.session_id == session_id,
                InterviewMessage.sequence_number == body.sequence_number,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing
        raise

    return {
        "id": msg.id,
        "session_id": msg.session_id,
        "sequence_number": msg.sequence_number,
        "speaker": msg.speaker,
        "text": msg.text,
        "phase": msg.phase,
        "metadata": msg.metadata_,
        "created_at": msg.created_at
    }


# ─── Events ────────────────────────────────────────────────────────────────────

@router.post(
    "/{session_id}/events",
    response_model=EventResponse,
    dependencies=[agent_auth],
    status_code=status.HTTP_201_CREATED,
)
async def create_event(
    session_id: UUID,
    body: EventCreate,
    db: AsyncSession = db_dependency,
):
    await _get_session(db, session_id)

    event = InterviewEvent(
        session_id=session_id,
        event_type=body.event_type,
        phase=body.phase,
        sequence_number=body.sequence_number,
        metadata_=body.metadata,
    )
    db.add(event)
    try:
        await db.commit()
        await db.refresh(event)
    except IntegrityError:
        # Same idempotency contract as create_message above.
        await db.rollback()
        result = await db.execute(
            select(InterviewEvent).where(
                InterviewEvent.session_id == session_id,
                InterviewEvent.sequence_number == body.sequence_number,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing
        raise

    return {
        "id": event.id,
        "session_id": event.session_id,
        "event_type": event.event_type,
        "phase": event.phase,
        "sequence_number": event.sequence_number,
        "metadata": event.metadata_,
        "created_at": event.created_at
    }


# ─── Checkpoints ───────────────────────────────────────────────────────────────

@router.post(
    "/{session_id}/checkpoints",
    response_model=CheckpointResponse,
    dependencies=[agent_auth],
    status_code=status.HTTP_201_CREATED,
)
async def create_checkpoint(
    session_id: UUID,
    body: CheckpointCreate,
    db: AsyncSession = db_dependency,
):
    await _get_session(db, session_id)

    checkpoint = InterviewCheckpoint(
        session_id=session_id,
        schema_version=body.schema_version,
        current_phase=body.current_phase,
        current_question_id=body.current_question_id,
        question_index=body.question_index,
        section=body.section,
        hints_used=body.hints_used,
        followups_used=body.followups_used,
        background_questions_asked=body.background_questions_asked,
        competencies_evaluated=body.competencies_evaluated,
        time_remaining_seconds=body.time_remaining_seconds,
        last_message_sequence=body.last_message_sequence,
        last_event_sequence=body.last_event_sequence,
        current_question_snapshot=body.current_question_snapshot,
        section_progress=body.section_progress,
        question_records=body.question_records,
    )
    db.add(checkpoint)
    await db.commit()
    await db.refresh(checkpoint)

    return checkpoint


@router.post(
    "/{session_id}/evaluation",
    dependencies=[agent_auth],
)
async def submit_evaluation(
    session_id: UUID,
    body: EvaluationSubmit,
    db: AsyncSession = db_dependency,
):
    """Upserts the normalized Evaluation + Score rows for this session.
    Idempotent on session_id -- the agent's own mid-session attempt and its
    teardown-time retry (both call this) can both succeed without creating
    duplicate rows. A resubmission replaces (not accumulates) prior scores,
    matching build_final_result()'s existing single-envelope-per-session
    semantics for the legacy final_result JSONB."""
    session = await _get_session(db, session_id)
    evaluation_id = await _upsert_evaluation(
        db, session,
        overall_score=body.overall_score,
        recommendation=body.recommendation,
        evidence_sufficiency=body.evidence_sufficiency,
        summary=body.summary,
        detailed_overview=body.detailed_overview,
        criterion_scores=body.criterion_scores,
    )
    await db.commit()
    return {"session_id": str(session_id), "evaluation_id": str(evaluation_id)}
