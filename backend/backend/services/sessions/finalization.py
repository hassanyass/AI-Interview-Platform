"""Session finalization — the one place every end-of-session trigger funnels
through (moved verbatim from api/endpoints/internal.py in H2-A2; the
2026-09-01 investigation notes below are the original ones).

Callers: the agent's graceful teardown (internal.update_session_status),
POST /interviews/{id}/terminate (interviews.py) and the idle-disconnect
sweep (started from main.py). All best-effort side effects (egress stop,
room delete) never raise.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.models.interview import Evaluation, InterviewSession
from backend.providers.factory import get_realtime

logger = logging.getLogger(__name__)

# Stable bigint key for pg_try_advisory_xact_lock; any fixed value works,
# it just has to be the same on every replica.
SWEEP_LOCK_KEY = 0x48494D4D41  # 'HIMMA' as a bigint


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

async def ensure_evaluation_placeholder(db: AsyncSession, session_id: UUID) -> None:
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
    # Two finalizers on different replicas can both pass the check above;
    # uq_evaluation_session then rejects the second insert. That is the
    # "already exists" outcome, not an error -- flush inside a savepoint so
    # the caller's transaction survives (H2-B).
    nested = await db.begin_nested()
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
        # Evaluation regeneration (2026-09-03): explicit flag, not a
        # string-match on the summary above -- see Evaluation.is_placeholder's
        # own docstring in models/interview.py and CURRENT_DECISIONS.md's
        # "Evaluation regeneration for placeholder sessions" entry.
        is_placeholder=True,
    ))
    try:
        await db.flush()
        await nested.commit()
    except IntegrityError:
        await nested.rollback()
        logger.info("Evaluation placeholder for %s already written by another finalizer", session_id)


async def delete_livekit_room(session_id: UUID) -> None:
    """Best-effort -- never raises, same spirit as stop_recording_egress
    below. Forcibly ends the LiveKit room (disconnecting the agent and any
    remaining participant), which is what actually stops a live interview
    from continuing to run when a candidate ends it through a path (REST
    terminate, the idle-disconnect sweep) that doesn't go through the
    agent's own data-channel-driven END_INTERVIEW handling. A no-op if the
    room never existed or already ended -- both expected, not errors."""
    room_name = f"interview-{session_id}"
    try:
        await get_realtime().delete_room(room_name)
    except Exception:  # noqa: BLE001 -- best-effort by contract: a missing/ended room is the expected case
        logger.info("No live LiveKit room to delete for session %s (already ended or never started)", session_id)


async def finalize_live_session(db: AsyncSession, session: InterviewSession, target_status: str = "TERMINATED") -> bool:
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

    # Replica safety (H2-B): lock the row and re-check inside this
    # transaction. Two triggers (sweep on replica A, candidate terminate on
    # replica B) can both see a non-terminal status above; only the first
    # to lock proceeds, the second sees the terminal status and no-ops.
    locked = await db.execute(
        select(InterviewSession.status).where(InterviewSession.id == session.id).with_for_update()
    )
    if locked.scalar_one_or_none() in ("COMPLETED", "TERMINATED"):
        await db.rollback()
        return False

    session.status = target_status
    if not session.completed_at:
        session.completed_at = datetime.now(timezone.utc)
    session.active_agent_id = None
    session.agent_lease_expires_at = None
    session.disconnected_at = None
    # Bug fix (2026-09-02): captured before commit, deliberately. Reading
    # session.recording_egress_id AFTER db.commit() (as this used to do)
    # hits the exact same async-SQLAlchemy pitfall as admin.py's
    # update_job_criteria fix earlier today: commit() expires every
    # attribute on `session` by default, so that later read silently
    # became a lazy-load -- which async SQLAlchemy can't do outside an
    # active greenlet context, raising `MissingGreenlet:
    # greenlet_spawn has not been called` and aborting the whole
    # terminate/finalize call (candidate-initiated terminate, and the
    # idle-disconnect sweep both call this function).
    session_id = session.id
    recording_egress_id = session.recording_egress_id

    await ensure_evaluation_placeholder(db, session_id)
    await db.commit()

    if recording_egress_id:
        await stop_recording_egress(recording_egress_id)
    await delete_livekit_room(session_id)
    return True




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
                # One replica per interval (H2-B): a transaction-scoped
                # advisory lock; if another backend holds it, skip this
                # iteration -- the row-level lock in finalize_live_session
                # makes a race harmless anyway, this just avoids the work.
                got = await db.execute(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": SWEEP_LOCK_KEY})
                if not got.scalar():
                    logger.debug("[DISCONNECT_SWEEP] another replica is sweeping; skipping")
                    await db.rollback()
                    await asyncio.sleep(settings.DISCONNECT_SWEEP_INTERVAL_SECONDS)
                    continue
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
                    await finalize_live_session(db, session, target_status="TERMINATED")
        except Exception:  # noqa: BLE001 -- the sweep loop must survive any single iteration's failure
            logger.exception("[DISCONNECT_SWEEP] sweep iteration failed")

        await asyncio.sleep(settings.DISCONNECT_SWEEP_INTERVAL_SECONDS)


async def stop_recording_egress(egress_id: str) -> None:
    """Best-effort -- never raises. A failure here means the egress
    process keeps running until it hits LiveKit's own room-empty/timeout
    behavior; it does not affect the session's own COMPLETED/TERMINATED
    status, which has already been committed by the time this runs."""
    try:
        await get_realtime().stop_recording(egress_id)
    except Exception:  # noqa: BLE001 -- best-effort by contract: the session's terminal status is already committed
        logger.exception("Failed to stop recording egress %s", egress_id)
