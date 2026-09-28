"""End-of-session persistence for the agent worker (H2-D).

`finalize_session` is the teardown that used to sit at the end of
main.entrypoint, moved verbatim: a completed interview persists its
completion + evaluation; anything else is checkpointed and marked
DISCONNECTED so the backend's idle-disconnect sweep can finalize it.
`mark_disconnected_after_failure` is the new path for a crash anywhere
after the session was moved to IN_PROGRESS: the same DISCONNECTED write,
best effort, so no session is ever left IN_PROGRESS with nobody driving it.
"""
from __future__ import annotations

import logging

from agent.interview.models import InterviewPhase, InterviewRuntimeContext
from agent.interview.persistence import InterviewPersistence

logger = logging.getLogger("agent")


async def finalize_session(persistence: InterviewPersistence, controller, context: InterviewRuntimeContext, session_id: str) -> str:
    """Returns "completed" or "disconnected"."""
    # If the interview isn't completed yet, mark as DISCONNECTED and save checkpoint
    if context.current_phase not in (InterviewPhase.COMPLETED,):
        logger.info("Interview not completed — saving disconnect checkpoint.")
        await persistence.save_event(
            session_id=session_id,
            sequence=context.event_sequence + 1,
            event_type="SESSION_DISCONNECTED",
            phase=context.current_phase.value,
        )
        context.event_sequence += 1
        await persistence.save_checkpoint(context)
        await persistence.update_status(session_id, "DISCONNECTED")
        
        try:
            logger.info("Generating partial evaluation for disconnected session...")
            await controller.generate_final_evaluation()
            await persistence.submit_evaluation(context)
        except Exception:
            logger.exception("Failed to generate partial evaluation during shutdown")
    else:
        logger.info("Interview completed.")
        try:
            await controller.generate_final_evaluation()
            await persistence.save_completion(context)
        except Exception:
            # Completion must not be lost because room teardown raced a
            # final persistence request. The next recovery path can retry.
            logger.exception("Failed to persist completed interview during shutdown")

        # Phase 8C: same last-resort retry for the normalized Evaluation/
        # Score submission, independent of the block above -- the backend
        # endpoint upserts on session_id, so retrying here even when the
        # mid-session attempt already succeeded is safe, not just tolerated.
        try:
            await persistence.submit_evaluation(context)
        except Exception:
            logger.exception("[EVALUATION_SUBMIT] failed_to_persist_completed_interview_during_shutdown")

    return "completed" if context.current_phase == InterviewPhase.COMPLETED else "disconnected"


async def mark_disconnected_after_failure(persistence: InterviewPersistence, context: InterviewRuntimeContext | None, session_id: str) -> None:
    """The session was moved to IN_PROGRESS and the worker is dying. Leave it
    DISCONNECTED (with a checkpoint when there is one) instead of stranded;
    the backend auto-finalizes DISCONNECTED sessions after its idle window.
    Best effort: every step is guarded, this must never raise."""
    try:
        if context is not None:
            try:
                await persistence.save_event(
                    session_id=session_id,
                    sequence=context.event_sequence + 1,
                    event_type="SESSION_DISCONNECTED",
                    phase=context.current_phase.value,
                    metadata={"reason": "agent_failure"},
                )
                context.event_sequence += 1
                await persistence.save_checkpoint(context)
            except Exception:  # noqa: BLE001 -- the status write below is what matters
                logger.exception("Failed to checkpoint before marking %s DISCONNECTED", session_id)
        ok = await persistence.update_status(session_id, "DISCONNECTED")
        logger.error("Session %s marked DISCONNECTED after agent failure (persisted=%s)", session_id, ok)
    except Exception:  # noqa: BLE001 -- last resort; logged, never raised
        logger.exception("Could not mark session %s DISCONNECTED after failure", session_id)
