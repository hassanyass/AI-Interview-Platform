"""Per-candidate result assembly for HR (Phase 8D): the legacy final_result
snapshot combined with the normalized Evaluation/Score rows, live-source
fallbacks, question enrichment, recording URL and integrity events. Moved
verbatim from api/endpoints/admin.py in H2-A2 so that both
GET /admin/interviews/{id}/result and the post-regeneration response come
from one function instead of one route calling another.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.config import settings
from backend.core.errors import Conflict, NotFound
from backend.models.interview import (
    Evaluation,
    InterviewCheckpoint,
    InterviewEvent,
    InterviewMessage,
    InterviewQuestion,
    InterviewSession,
    Job,
    Score,
)
from backend.providers.factory import get_recordings_storage
from backend.schemas.admin import (
    CriterionScoreResponse,
    EvaluationDetailResponse,
    IntegrityEventResponse,
    QuestionRecordDetail,
)

logger = logging.getLogger(__name__)


def presign_recording_url(storage_path: str | None) -> str | None:
    """PR-C/PR-F (docs/proctoring-architecture.md): the R2 object a
    session's recording lives at is private (the same R2 credentials used
    to upload it during Egress) -- there was no endpoint anywhere that
    could actually serve it back, which is why HR's result view had no way
    to play a recording at all, not just a missing player. A short-lived
    presigned GET URL (never stored, computed fresh per request) is the
    standard pattern for this: HR's browser gets a working <video> src
    without the raw R2 credentials, storage bucket, or a permanent public
    URL ever being exposed. Returns None (not an error) if there's no
    recording, or if R2 isn't configured -- both real, existing states
    this codebase already tolerates (see CURRENT_DECISIONS.md's
    camera-denial/R2-not-configured handling)."""
    if not storage_path:
        return None
    storage = get_recordings_storage()
    if not storage.configured:
        return None
    try:
        # Every step wrapped -- a storage-client failure must degrade to
        # "no recording available" on this one field, never 500 the entire
        # candidate result page. Same "a proctoring-feature failure must
        # never block the core flow" principle CURRENT_DECISIONS.md already
        # applies to camera denial.
        return storage.presign_get(storage_path, ttl_seconds=settings.RECORDING_URL_TTL_SECONDS)
    except Exception:  # noqa: BLE001 -- best-effort by contract: a recording problem must never 500 the result page
        logger.exception("Failed to presign recording URL for %s", storage_path)
        return None


# Explicit allowlist, not a blocklist -- a real query against interview_events
# today returns 15+ distinct event_type values (SESSION_STARTED,
# QUESTION_SKIPPED, PHASE_STARTED, HINT_REQUESTED, WAITING_ROOM_*, etc.),
# only a handful of which are genuine integrity signals; the rest are
# ordinary lifecycle bookkeeping that must never show up on an "integrity
# timeline". Matches process_ui_command's own explicit tuple in
# controller.py exactly -- same 6 strings, not derived from it (no shared
# import between the agent and backend packages) so keep these two lists
# in sync by hand if either changes.
INTEGRITY_EVENT_TYPES = (
    "FULLSCREEN_EXITED", "TAB_HIDDEN", "WINDOW_BLURRED",
    "NO_FACE_DETECTED", "MULTIPLE_FACES_DETECTED",
    "HEAD_DOWN_SUSPECTED",
)


async def get_integrity_events(db: AsyncSession, session: InterviewSession) -> list[IntegrityEventResponse]:
    """Session-finalization/proctoring aggregation (2026-09-02, see
    CURRENT_DECISIONS.md's "Proctoring PR-D scope decision" and the
    aggregation/dashboard plan that followed it, plus Part 2's head-pose
    signal): resolves the known integrity signal types (INTEGRITY_EVENT_
    TYPES) for one session, in order.

    video_offset_seconds is computed as event.created_at - session.started_at
    -- a real, named approximation, not a frame-exact seek: the Egress
    recording actually starts as soon as the candidate's browser connects to
    the room (livekit.py's _start_recording_egress), while started_at is set
    separately, later, when the agent finishes joining and calls
    update_status("IN_PROGRESS") (agent/main.py) -- two different processes
    writing two different clocks with real, variable latency between them.
    Close enough to jump a video player near the right moment; not exact
    enough to promise frame accuracy. None when started_at is missing
    entirely (a legacy/never-started session)."""
    result = await db.execute(
        select(InterviewEvent)
        .where(
            InterviewEvent.session_id == session.id,
            InterviewEvent.event_type.in_(INTEGRITY_EVENT_TYPES),
        )
        .order_by(InterviewEvent.sequence_number)
    )
    events = result.scalars().all()
    return [
        IntegrityEventResponse(
            event_type=e.event_type,
            phase=e.phase,
            metadata=e.metadata_ or {},
            video_offset_seconds=(
                # Clamped to >=0: the clock-skew this docstring describes can
                # occasionally put an early event fractionally before
                # started_at was written -- a negative seek target makes no
                # sense to a <video> player, so floor it at the start.
                max(0.0, (e.created_at - session.started_at).total_seconds())
                if session.started_at and e.created_at else None
            ),
        )
        for e in events
    ]


async def get_live_transcript(db: AsyncSession, session_id: UUID) -> list[dict]:
    """Amendment (2026-09-03, see CURRENT_DECISIONS.md's "Results display
    for non-naturally-completed sessions" entry): fallback source for a
    session's transcript when the legacy final_result JSONB snapshot was
    never written. final_result.transcript is ONLY ever populated by the
    agent's own natural end-of-interview path (persistence.py's
    build_final_result -> save_completion) -- a session that ends any
    other way (candidate/HR-terminated, the idle-disconnect sweep, an
    agent crash) never gets that snapshot, even though every individual
    turn is already durably persisted here in InterviewMessage as it
    happens. Real DB evidence at the time of this fix: 4 real TERMINATED
    sessions with 1-8 real messages each, every one showing an empty
    transcript on the results page despite the real conversation existing
    the whole time. "system" is a theoretically-allowed speaker value
    (see the model's own comment) but has never actually been written by
    the agent -- excluded here so this can never violate
    TranscriptMessage's agent|candidate-only contract even if that ever
    changes."""
    result = await db.execute(
        select(InterviewMessage)
        .where(
            InterviewMessage.session_id == session_id,
            InterviewMessage.speaker.in_(("candidate", "agent")),
        )
        .order_by(InterviewMessage.sequence_number)
    )
    return [{"speaker": m.speaker, "text": m.text} for m in result.scalars().all()]


async def get_live_question_records_and_submission(
    db: AsyncSession, session_id: UUID
) -> tuple[list[dict], dict]:
    """Same gap and reasoning as _get_live_transcript above, for
    question_records/technical_submission. InterviewCheckpoint is saved
    after essentially every turn (persistence.py's save_checkpoint, called
    throughout the interview, not just at natural completion), so the
    latest row is a near-real-time snapshot even for a session that never
    reached that natural path. Unlike the transcript, InterviewCheckpoint
    deliberately does NOT store the full transcript (see its own
    docstring) -- only this structured progress data, which it does
    carry, in the exact same QuestionRecord-model shape build_final_result
    itself serializes (both call `.model_dump(mode="json")` on the same
    context.question_records), so no reshaping is needed here."""
    result = await db.execute(
        select(InterviewCheckpoint)
        .where(InterviewCheckpoint.session_id == session_id)
        .order_by(InterviewCheckpoint.created_at.desc())
        .limit(1)
    )
    checkpoint = result.scalar_one_or_none()
    if checkpoint is None:
        return [], {}
    question_records = checkpoint.question_records or []
    technical_submission = (
        (checkpoint.section_progress or {}).get("technical", {}).get("technical_submission")
        or {}
    )
    return question_records, technical_submission


async def build_candidate_result(db: AsyncSession, session_id: UUID) -> EvaluationDetailResponse:
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
        raise NotFound("Interview session not found.")

    job_title = None
    if session.job_id:
        job_result = await db.execute(select(Job.title).where(Job.id == session.job_id))
        job_title = job_result.scalar_one_or_none()

    final_result = session.final_result or {}

    # Amendment (2026-09-03): final_result is only ever written by the
    # agent's own natural completion path -- fall back to the live sources
    # (already durably persisted independently of that path) rather than
    # silently showing "nothing was recorded" for a session that actually
    # has real data. See _get_live_transcript's docstring for the full
    # reasoning and real evidence.
    transcript = final_result.get("transcript") or []
    raw_question_records = final_result.get("question_records") or []
    technical_submission = final_result.get("technical_submission") or {}
    if not transcript:
        transcript = await get_live_transcript(db, session_id)
    if not raw_question_records or not technical_submission:
        live_records, live_submission = await get_live_question_records_and_submission(db, session_id)
        if not raw_question_records:
            raw_question_records = live_records
        if not technical_submission:
            technical_submission = live_submission

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
        raise Conflict("This session has not been evaluated yet (no Evaluation row exists).", code="not_evaluated")

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
            weight=s.criterion.weight if s.criterion else None,
        )
        for s in evaluation.scores
    ]

    # Enrich each raw question_record (question_id + outcome only -- useless
    # to an HR reviewer with no idea what was actually asked) with the real
    # question text, resolved from InterviewQuestion. A record whose
    # question_id doesn't resolve (legacy pre-Phase-7 session using
    # ephemeral, never-persisted questions) still comes through with
    # title/text/competency left None rather than being dropped.
    # (raw_question_records already resolved above, final_result or the
    # live-checkpoint fallback.)
    question_uuids = []
    for r in raw_question_records:
        try:
            question_uuids.append(UUID(r["question_id"]))
        except (KeyError, ValueError, TypeError):
            continue
    questions_by_id = {}
    if question_uuids:
        q_result = await db.execute(
            select(InterviewQuestion).where(InterviewQuestion.id.in_(question_uuids))
        )
        questions_by_id = {str(q.id): q for q in q_result.scalars().all()}

    question_records = []
    for r in raw_question_records:
        q = questions_by_id.get(r.get("question_id"))
        # Verbal Background subsection: a generated background question has
        # no InterviewQuestion row -- the record carries its own text
        # (question_title/question_text/competency/subsection, written by the
        # agent's _advance_core_question). Used as the fallback whenever the
        # id does not resolve, so a legacy record stays exactly as before.
        question_records.append(QuestionRecordDetail(
            question_id=r.get("question_id", ""),
            title=q.title if q else r.get("question_title"),
            text=q.text if q else r.get("question_text"),
            competency=q.competency if q else r.get("competency"),
            order_index=q.order_index if q else None,
            outcome=r.get("outcome", "UNKNOWN"),
            hints_used=r.get("hints_used", 0),
            followups_used=r.get("followups_used", 0),
            clarifications_used=r.get("clarifications_used", 0),
            subsection=r.get("subsection"),
        ))

    return EvaluationDetailResponse(
        session_id=session.id,
        status=session.status,
        completed_at=session.completed_at,
        candidate_name=session.profile.full_name if session.profile else None,
        candidate_email=session.profile.email if session.profile else None,
        job_title=job_title,
        transcript=transcript,
        question_records=question_records,
        technical_submission=technical_submission,
        overall_score=evaluation.overall_score,
        recommendation=evaluation.recommendation,
        evidence_sufficiency=evaluation.evidence_sufficiency,
        summary=evaluation.summary,
        detailed_overview=evaluation.detailed_overview,
        scores=scores,
        weighted_score=evaluation.weighted_score,
        is_placeholder=evaluation.is_placeholder,
        override_suggested=evaluation.override_suggested,
        override_reason=evaluation.override_reason,
        recording_url=presign_recording_url(session.recording_storage_path),
        is_mock_data=bool(final_result.get("is_mock")),
        integrity_events=await get_integrity_events(db, session),
    )
