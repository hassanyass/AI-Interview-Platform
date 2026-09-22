"""Build the InterviewRuntimeContext for a job from the backend's /load
payload -- fresh start or resume from checkpoint. Moved verbatim out of
main.entrypoint in H2-D so the lifecycle reads as bootstrap -> session ->
teardown and each part is testable on its own.

The helpers it uses (build_core_sections, build_criteria,
restore_background_questions) stay in agent.main because the existing
test suite imports them from there; they are imported lazily to avoid a
module cycle.
"""
from __future__ import annotations

import logging
from typing import Tuple

from agent.interview.models import (
    EvaluationSignal, InterviewPhase, InterviewRuntimeContext, Message, Question, QuestionRecord,
)
from agent.interview.persistence import InterviewPersistence

logger = logging.getLogger("agent")


async def build_context(
    session_data: dict, persistence: InterviewPersistence, session_id: str
) -> Tuple[InterviewRuntimeContext, bool]:
    """Returns (context, is_resuming). Moves the session to IN_PROGRESS and
    writes the SESSION_STARTED / SESSION_RECONNECTED event -- from this point
    on the caller owes the backend a terminal status (teardown.py)."""
    from agent.main import (
        attach_background_questions, build_core_sections, build_criteria, restore_background_questions,
    )

    # ─── Build InterviewRuntimeContext ─────────────────────────────────
    duration_minutes = session_data.get("duration_minutes", 15)
    checkpoint = session_data.get("latest_checkpoint") or {}
    recent_messages = session_data.get("recent_messages", [])

    # Phase 7D/7E: B2B ordered core-question sections (see build_core_sections
    # docstring). Only the mutable pointer (current_index/completed) is
    # restored from the checkpoint below, on the resume path.
    built_sections = build_core_sections(session_data)
    built_criteria = build_criteria(session_data)

    # Safely determine if the initial greeting was already generated and persisted.
    has_greeting = any(
        msg.get("metadata", {}) and msg.get("metadata", {}).get("is_greeting") is True
        for msg in recent_messages
    )

    # If resuming (has_greeting is True), restore state regardless of status
    is_resuming = has_greeting
    
    if is_resuming:
        logger.info("Restoring from checkpoint/messages (reconnect scenario)...")
        
        # Recover sequences from messages if checkpoint is missing
        max_msg_seq = max([m.get("sequence_number", 0) for m in recent_messages], default=0)
        
        checkpoint_technical = (checkpoint.get("section_progress") or {}).get("technical", {})
        context = InterviewRuntimeContext(
            session_id=session_id,
            candidate_id=str(session_data["candidate_profile_id"]),
            role=session_data["role"],
            confirmed_level=session_data["level"],
            language=session_data["language"],
            job_description=session_data.get("job_description"),
            candidate_profile=session_data.get("candidate_profile", {}),
            current_phase=InterviewPhase(checkpoint.get("current_phase", "CREATED")),
            question_index=checkpoint.get("question_index", 0),
            hints_used=checkpoint.get("hints_used", 0),
            followups_used=checkpoint.get("followups_used", 0),
            time_remaining_seconds=checkpoint.get("time_remaining_seconds", duration_minutes * 60),
            message_sequence=max(checkpoint.get("last_message_sequence", 0), max_msg_seq),
            event_sequence=checkpoint.get("last_event_sequence", 0),
            technical_question_ids_seen=checkpoint.get("technical_question_ids_seen", checkpoint_technical.get("technical_question_ids_seen", [])),
            technical_question_ids_skipped=checkpoint.get("technical_question_ids_skipped", checkpoint_technical.get("technical_question_ids_skipped", [])),
            technical_question_id_submitted=checkpoint.get("technical_question_id_submitted", checkpoint_technical.get("technical_question_id_submitted")),
            technical_submission=checkpoint.get("technical_submission", checkpoint_technical.get("technical_submission", {})),
            sections=built_sections,
            criteria=built_criteria,
        )

        # Restore the ordered core-question pointer (Phase 7D) — the question
        # list itself is always the fresh one built from /load above.
        verbal_checkpoint = (checkpoint.get("section_progress") or {}).get("verbal")
        if verbal_checkpoint and "VERBAL" in context.sections:
            # Background questions first (they sit at the front of the
            # list), THEN the pointer -- the pointer counts them.
            restored_bg = attach_background_questions(context.sections, restore_background_questions(checkpoint))
            if restored_bg:
                logger.info("[BG-GEN] Restored %d background question(s) from checkpoint", restored_bg)
            context.sections["VERBAL"].current_index = verbal_checkpoint.get("current_index", 0)
            # Background sub-clock: absolute deadline, so it simply resumes.
            context.background_deadline_epoch = verbal_checkpoint.get("background_deadline_epoch")
            context.sections["VERBAL"].completed = verbal_checkpoint.get("completed", False)

        # Restore conversation history from persisted messages
        for msg in recent_messages:
            context.conversation_history.append(
                Message(role="user" if msg["speaker"] == "candidate" else "assistant", content=msg["text"])
            )

        # Restore section progress from checkpoint
        sp = checkpoint.get("section_progress", {})
        if "background" in sp:
            bg = sp["background"]
            context.background_progress.questions_asked = bg.get("questions_asked", 0)
            context.background_progress.completed = bg.get("completed", False)
        if "technical" in sp:
            tech = sp["technical"]
            context.technical_progress.questions_completed = tech.get("questions_completed", 0)
            context.technical_progress.questions_skipped = tech.get("questions_skipped", 0)

        # Restore current question
        question_snapshot = checkpoint.get("current_question_snapshot")
        if question_snapshot:
            context.current_question = Question(**question_snapshot)
            logger.info(
                "[TECH-GEN] Resumed existing question id=%s title=%s source=%s",
                context.current_question.id,
                context.current_question.title,
                context.current_question.source,
            )
            
        # Restore question records
        records_snapshot = checkpoint.get("question_records", [])
        if records_snapshot:
            context.question_records = [QuestionRecord(**r) for r in records_snapshot]

        # Restore evaluation signals
        evals_snapshot = checkpoint.get("evaluation_signals", [])
        if evals_snapshot:
            context.evaluation_signals = [EvaluationSignal(**e) for e in evals_snapshot]

        # Log reconnect event
        await persistence.update_status(session_id, "IN_PROGRESS")
        await persistence.save_event(
            session_id=session_id,
            sequence=context.event_sequence + 1,
            event_type="SESSION_RECONNECTED",
            phase=context.current_phase.value,
        )
        context.event_sequence += 1

    else:
        # Fresh start
        context = InterviewRuntimeContext(
            session_id=session_id,
            candidate_id=str(session_data["candidate_profile_id"]),
            role=session_data["role"],
            confirmed_level=session_data["level"],
            language=session_data["language"],
            job_description=session_data.get("job_description"),
            candidate_profile=session_data.get("candidate_profile", {}),
            time_remaining_seconds=duration_minutes * 60,
            sections=built_sections,
            criteria=built_criteria,
        )

        # Transition to IN_PROGRESS
        await persistence.update_status(session_id, "IN_PROGRESS")
        await persistence.save_event(
            session_id=session_id,
            sequence=1,
            event_type="SESSION_STARTED",
            phase="CREATED",
        )
        context.event_sequence = 1

    return context, is_resuming
