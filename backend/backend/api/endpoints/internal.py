"""
Internal persistence API for agent-to-backend communication.
Protected by AGENT_API_SECRET — never exposed to the frontend.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Header, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.api.deps import db_dependency
from backend.core.config import settings
from backend.models.interview import (
    InterviewSession, InterviewConfiguration, InterviewDefinition, InterviewSection,
    InterviewMessage, InterviewEvent, InterviewCheckpoint,
    AssessmentCriterion, Evaluation, Score,
)
from backend.models.profile import CandidateProfile
from backend.schemas.persistence import (
    MessageCreate, MessageResponse,
    EventCreate, EventResponse,
    CheckpointCreate, CheckpointResponse,
    StatusUpdate, SessionLoadResponse,
    QuestionPayload, SectionPayload,
    CriterionPayload, EvaluationSubmit,
)

logger = logging.getLogger(__name__)

router = APIRouter()

VALID_STATUSES = {"CREATED", "IN_PROGRESS", "DISCONNECTED", "COMPLETED", "TERMINATED"}
VALID_TRANSITIONS = {
    "CREATED": {"IN_PROGRESS"},
    "IN_PROGRESS": {"DISCONNECTED", "COMPLETED", "TERMINATED"},
    "DISCONNECTED": {"IN_PROGRESS", "TERMINATED"},
    "COMPLETED": set(),
    "TERMINATED": set(),
}

# Agent lease duration — agent must renew within this window
AGENT_LEASE_DURATION = timedelta(minutes=10)


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


# ─── Session-finalization contract (2026-09-01 real-issue investigation) ───────
# Root cause (see the session that diagnosed this, and docs/CURRENT_DECISIONS.md):
# "end this interview" was three independently-triggered side effects (stop
# Egress, disconnect the LiveKit room, write the Evaluation row) with no
# shared guarantee -- any one of them could fire without the others,
# leaving a session stuck with no Evaluation row (HR dashboard's "not
# evaluated yet") and/or a recording that never stops. These two helpers
# are the single place all three end-of-session triggers (the agent's own
# graceful teardown via update_session_status below, POST /interviews/
# {id}/terminate for a candidate-initiated live end, and the idle-
# disconnect sweep) now funnel through.

async def _ensure_evaluation_placeholder(db: AsyncSession, session_id: UUID) -> None:
    """Guarantee an Evaluation row exists once a session reaches a terminal
    status, even if the agent process never got to run
    generate_final_evaluation()/submit_evaluation() itself (crashed, lost
    its lease, or the session ended via a path that never talks to the
    agent at all). Never overwrites a real evaluation already submitted --
    only fills the gap. Mirrors the exact fallback DetailedEvaluation shape
    controller.py's own generate_final_evaluation() already produces on LLM
    failure ([controller.py] "Session ended early or evaluation generation
    failed..."), so a placeholder looks the same regardless of which of the
    two code paths produced it."""
    existing = await db.execute(
        select(Evaluation.id).where(Evaluation.session_id == session_id)
    )
    if existing.scalar_one_or_none() is not None:
        return
    db.add(Evaluation(
        session_id=session_id,
        overall_score=None,
        recommendation="Consider / Mixed",
        evidence_sufficiency=0,
        summary="Session ended before a full evaluation could be generated.",
        detailed_overview=(
            "This interview was disconnected or ended before the AI "
            "evaluation could run. Review the transcript and recording "
            "directly to assess this candidate."
        ),
    ))


async def _delete_livekit_room(session_id: UUID) -> None:
    """Best-effort -- never raises, same spirit as _stop_recording_egress
    below. Forcibly ends the LiveKit room (disconnecting the agent and any
    remaining participant), which is what actually stops a live interview
    from continuing to run when a candidate ends it through a path (REST
    terminate, the idle-disconnect sweep) that doesn't go through the
    agent's own data-channel-driven END_INTERVIEW handling. A no-op if the
    room never existed or already ended -- both expected, not errors."""
    from livekit import api as lk_api
    room_name = f"interview-{session_id}"
    lkapi = lk_api.LiveKitAPI(url=settings.LIVEKIT_URL, api_key=settings.LIVEKIT_API_KEY, api_secret=settings.LIVEKIT_API_SECRET)
    try:
        await lkapi.room.delete_room(lk_api.DeleteRoomRequest(room=room_name))
    except Exception:
        logger.info("No live LiveKit room to delete for session %s (already ended or never started)", session_id)
    finally:
        await lkapi.aclose()


async def _finalize_live_session(db: AsyncSession, session: InterviewSession, target_status: str = "TERMINATED") -> bool:
    """Idempotent terminal-state finalizer for a session ended from OUTSIDE
    the agent's own graceful teardown -- POST /interviews/{id}/terminate
    (candidate-initiated, now covers a LIVE session too, not just the
    pre-connect abandon case) and the idle-disconnect sweep. Deliberately
    does NOT route through update_session_status's VALID_TRANSITIONS table
    below -- that table only models the agent-driven state machine, and a
    candidate-abandoned CREATED session ending in TERMINATED (this
    endpoint's original, still-supported case) was never a modeled agent
    transition either. No-op (returns False) if the session already
    reached a terminal status -- safe to call from multiple triggers
    without double-finalizing."""
    if session.status in ("COMPLETED", "TERMINATED"):
        return False

    session.status = target_status
    if not session.completed_at:
        session.completed_at = datetime.now(timezone.utc)
    session.active_agent_id = None
    session.agent_lease_expires_at = None
    session.disconnected_at = None

    await _ensure_evaluation_placeholder(db, session.id)
    await db.commit()

    if session.recording_egress_id:
        await _stop_recording_egress(session.recording_egress_id)
    await _delete_livekit_room(session.id)
    return True


_DISCONNECT_SWEEP_INTERVAL_SECONDS = 120


async def disconnect_auto_finalize_sweep_loop() -> None:
    """Backend-owned safety net: a candidate who disconnects (tab closed,
    network drop) and never resumes would otherwise leave the session
    (and its LiveKit Egress recording) running indefinitely -- nothing
    else in this codebase ever revisits a DISCONNECTED session once the
    agent process that was handling it exits. Runs for the lifetime of the
    backend process (started from main.py's startup event, same lifecycle
    as the app itself), same polling-loop shape as the agent's own
    renew_lease_loop in agent/agent/main.py. Confirmed default duration
    with the user (2026-09-01): 10 minutes idle in DISCONNECTED."""
    from backend.db.session import AsyncSessionLocal

    if not AsyncSessionLocal:
        return

    while True:
        try:
            threshold = datetime.now(timezone.utc) - timedelta(
                minutes=settings.DISCONNECT_AUTO_FINALIZE_MINUTES
            )
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(InterviewSession).where(
                        InterviewSession.status == "DISCONNECTED",
                        InterviewSession.disconnected_at.is_not(None),
                        InterviewSession.disconnected_at < threshold,
                    )
                )
                stale_sessions = list(result.scalars().all())
                for session in stale_sessions:
                    logger.info(
                        "[DISCONNECT_SWEEP] auto-finalizing session %s idle since %s",
                        session.id, session.disconnected_at,
                    )
                    await _finalize_live_session(db, session, target_status="TERMINATED")
        except Exception:
            logger.exception("[DISCONNECT_SWEEP] sweep iteration failed")

        await asyncio.sleep(_DISCONNECT_SWEEP_INTERVAL_SECONDS)


async def _resolve_criteria_for_job(db: AsyncSession, job_id) -> list[AssessmentCriterion]:
    """Phase 8C. job_id-scoped enabled rows if any exist for this job;
    otherwise falls back to the enabled TEMPLATE tier (job_id/section_id both
    NULL) as this job's default set. That fallback is a deliberate, flagged
    interim behavior (no 8E authoring UI exists yet to create job-scoped
    rows) — see AssessmentCriterion's docstring in models/interview.py.
    Returns [] entirely for job_id=None (a legacy, non-B2B session)."""
    if job_id is None:
        return []
    result = await db.execute(
        select(AssessmentCriterion).where(
            AssessmentCriterion.job_id == job_id,
            AssessmentCriterion.enabled.is_(True),
        )
    )
    job_criteria = list(result.scalars().all())
    if job_criteria:
        return job_criteria

    template_result = await db.execute(
        select(AssessmentCriterion).where(
            AssessmentCriterion.job_id.is_(None),
            AssessmentCriterion.section_id.is_(None),
            AssessmentCriterion.enabled.is_(True),
        )
    )
    return list(template_result.scalars().all())


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
    session.agent_lease_expires_at = now + AGENT_LEASE_DURATION

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
    new_expiry = now + AGENT_LEASE_DURATION
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


async def _stop_recording_egress(egress_id: str) -> None:
    """Best-effort -- never raises. A failure here means the egress
    process keeps running until it hits LiveKit's own room-empty/timeout
    behavior; it does not affect the session's own COMPLETED/TERMINATED
    status, which has already been committed by the time this runs."""
    from livekit import api as lk_api
    lkapi = lk_api.LiveKitAPI(url=settings.LIVEKIT_URL, api_key=settings.LIVEKIT_API_KEY, api_secret=settings.LIVEKIT_API_SECRET)
    try:
        await lkapi.egress.stop_egress(lk_api.StopEgressRequest(egress_id=egress_id))
    except Exception:
        logger.exception("Failed to stop recording egress %s", egress_id)
    finally:
        await lkapi.aclose()


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
    except Exception:
        await db.rollback()
        # Idempotency: if unique constraint violated, return existing
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
    except Exception:
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


# ─── Evaluation Submission (Phase 8C) ───────────────────────────────────────────

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

    result = await db.execute(
        select(Evaluation).where(Evaluation.session_id == session_id)
    )
    evaluation = result.scalar_one_or_none()

    if evaluation is None:
        evaluation = Evaluation(session_id=session_id)
        db.add(evaluation)
        await db.flush()  # assigns evaluation.id before Score rows reference it
    else:
        await db.execute(delete(Score).where(Score.evaluation_id == evaluation.id))

    evaluation.overall_score = body.overall_score
    evaluation.recommendation = body.recommendation
    evaluation.evidence_sufficiency = body.evidence_sufficiency
    evaluation.summary = body.summary
    evaluation.detailed_overview = body.detailed_overview

    # Scoring-mechanism upgrade (2026-09-01, signed-off frozen-file touch,
    # see CURRENT_DECISIONS.md's "Scoring mechanism upgrade" entry): a
    # real, code-computed weighted aggregate of criterion_scores, using
    # each enabled criterion's AssessmentCriterion.weight. Deliberately
    # separate from overall_score (the LLM's own independent holistic
    # judgment, untouched by this change) -- computed once here, using the
    # weights in effect at submission time, then frozen on the Evaluation
    # row, same "recorded fact about this evaluation event" precedent as
    # overall_score/evidence_sufficiency.
    #
    # Formula (plan item 3): S = criteria that are both enabled for this
    # job AND have a non-null score in this submission. weighted_score =
    # sum(weight_i * score_i for i in S) / sum(weight_i for i in S).
    # Dividing by the sum of INCLUDED weights (not a fixed total) IS the
    # renormalization -- a disabled or null-scored criterion's weight is
    # simply absent from that denominator, so the remaining criteria's
    # shares grow proportionally on their own. None (not 0) when S is
    # empty -- nothing to average is "insufficient evidence", not "scored
    # zero", matching overall_score's own null convention.
    weighted_sum = 0.0
    total_weight = 0
    if body.criterion_scores:
        # Best-effort criterion_id resolution, scoped to this exact job's
        # resolved criteria set (not a bare global key lookup — a key is
        # only unique within one job/template scope, not across all of them).
        # _resolve_criteria_for_job already filters to enabled.is_(True), so
        # a criterion disabled since the question was asked (or any key not
        # in this job's resolved set) is naturally excluded from both the
        # criterion_id lookup and the weighted-score computation below.
        resolved = await _resolve_criteria_for_job(db, session.job_id)
        key_to_id = {c.key: c.id for c in resolved}
        key_to_weight = {c.key: c.weight for c in resolved}
        for cs in body.criterion_scores:
            db.add(Score(
                evaluation_id=evaluation.id,
                criterion_id=key_to_id.get(cs.criterion_key),
                criterion_key=cs.criterion_key,
                score=cs.score,
                overview=cs.overview,
                strengths=cs.strengths,
                improvements=cs.improvements,
                evidence_reference=cs.evidence_reference,
            ))
            weight = key_to_weight.get(cs.criterion_key)
            if weight is not None and cs.score is not None:
                weighted_sum += weight * cs.score
                total_weight += weight

    evaluation.weighted_score = (weighted_sum / total_weight) if total_weight > 0 else None

    # Audit fix (2026-08-27) pattern, same bug class: db.commit() expires the
    # ORM instance's attributes by default, so reading evaluation.id after
    # commit forces a lazy-refresh outside an async-safe context ->
    # sqlalchemy.exc.MissingGreenlet. Capture the value BEFORE commit, return
    # that local, never the (now-expired) ORM attribute.
    evaluation_id = evaluation.id
    await db.commit()
    return {"session_id": str(session_id), "evaluation_id": str(evaluation_id)}
