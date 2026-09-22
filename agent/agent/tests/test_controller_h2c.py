"""H2-C (frozen controller.py, hunks C1–C7 signed off 2026-09-22):
- IM_READY in TECHNICAL_INTRO no longer raises NameError;
- fixed spoken lines come from SYSTEM_MESSAGES in the session language;
- irreversible spoken controls are confirmed on the next turn.
"""
import asyncio
import re
from unittest.mock import AsyncMock

import pytest

from agent.interview.controller import InterviewController
from agent.interview.models import (
    ActionEnum, CandidateControlAction, InterviewPhase, InterviewRuntimeContext, StructuredAction,
)
from agent.interview.persistence import MockPersistence
from agent.interview.questions import QUESTION_BANK
from agent.interview.voice_intents import CONFIRM_BEFORE_EXECUTING, is_affirmative
from agent.llm.prompts import SYSTEM_MESSAGES

LATIN = re.compile(r"[A-Za-z]")


def make_controller(phase: InterviewPhase, language: str = "en") -> InterviewController:
    context = InterviewRuntimeContext(
        session_id="h2c", candidate_id="candidate", role="Backend Engineer",
        confirmed_level="junior", language=language, current_phase=phase, time_remaining_seconds=1800,
    )
    llm = AsyncMock()
    llm.generate_structured = AsyncMock(return_value=StructuredAction(
        action=ActionEnum.ASK, response="Tell me more.", reason="llm", should_transition=False,
    ))
    return InterviewController(llm, MockPersistence(), context)


def run(coro):
    return asyncio.run(coro)


# ── C1 / C5 ────────────────────────────────────────────────────────────────

def test_im_ready_in_technical_intro_transitions_instead_of_raising():
    c = make_controller(InterviewPhase.TECHNICAL_INTRO)
    c.context.current_question = QUESTION_BANK[0]
    action = run(c.process_ui_command("IM_READY"))
    assert c.context.current_phase == InterviewPhase.TECHNICAL
    assert action.action == ActionEnum.ACKNOWLEDGE
    assert action.response == SYSTEM_MESSAGES["en"]["im_ready_ack"]


def test_im_ready_arabic_ack_is_arabic():
    c = make_controller(InterviewPhase.TECHNICAL_INTRO, language="ar")
    c.context.current_question = QUESTION_BANK[0]
    action = run(c.process_ui_command("IM_READY"))
    assert not LATIN.search(action.response)


# ── C2 / C3 / C4 / C6 ──────────────────────────────────────────────────────

def test_message_tables_have_identical_keys_in_both_languages():
    assert set(SYSTEM_MESSAGES["en"]) == set(SYSTEM_MESSAGES["ar"])
    for key in ("already_completed", "time_up_wrap", "llm_fallback", "im_ready_ack", "forced_wrap_up",
                "forced_next_question", "forced_to_technical", "forced_wrap_question", "forced_next_part",
                "confirm_end_interview", "confirm_skip_question", "confirm_change_question",
                "confirm_move_to_technical", "confirm_skip_section"):
        assert SYSTEM_MESSAGES["en"][key] and not LATIN.search(SYSTEM_MESSAGES["ar"][key]), key


def test_completed_and_llm_failure_fallbacks_follow_the_session_language():
    ar = make_controller(InterviewPhase.COMPLETED, language="ar")
    action = run(ar.process_candidate_input("hello"))
    assert action.action == ActionEnum.END and not LATIN.search(action.response)

    ar = make_controller(InterviewPhase.TECHNICAL, language="ar")
    ar.context.current_question = QUESTION_BANK[0]
    ar.llm.generate_structured = AsyncMock(side_effect=RuntimeError("llm down"))
    action = run(ar.process_candidate_input("some answer"))
    assert action.response == SYSTEM_MESSAGES["ar"]["llm_fallback"]


def test_forced_transition_messages_follow_the_session_language():
    for lang in ("en", "ar"):
        c = make_controller(InterviewPhase.TECHNICAL, language=lang)
        msg = c._get_forced_transition_message()
        assert msg == SYSTEM_MESSAGES[lang]["forced_wrap_question"]
        c.context.current_phase = InterviewPhase.WELCOME
        assert c._get_forced_transition_message() == SYSTEM_MESSAGES[lang]["forced_next_part"]


# ── C7: confirmation ───────────────────────────────────────────────────────

def test_spoken_end_interview_asks_for_confirmation_then_ends_on_yes():
    c = make_controller(InterviewPhase.TECHNICAL)
    c.context.current_question = QUESTION_BANK[0]
    first = run(c.process_candidate_input("ok i'm done"))
    assert first.action == ActionEnum.ASK
    assert first.response == SYSTEM_MESSAGES["en"]["confirm_end_interview"]
    assert first.detected_candidate_control == CandidateControlAction.END_INTERVIEW
    assert c.context.current_phase == InterviewPhase.TECHNICAL          # nothing changed yet
    c.llm.generate_structured.assert_not_awaited()

    second = run(c.process_candidate_input("yes"))
    assert second.detected_candidate_control == CandidateControlAction.END_INTERVIEW
    assert c.context.current_phase in (InterviewPhase.CLOSING, InterviewPhase.COMPLETED)


def test_anything_but_an_affirmative_cancels_the_pending_control():
    c = make_controller(InterviewPhase.TECHNICAL)
    c.context.current_question = QUESTION_BANK[0]
    run(c.process_candidate_input("i'm done"))
    reply = run(c.process_candidate_input("no wait, let me continue with the hash map idea"))
    assert c.context.current_phase == InterviewPhase.TECHNICAL
    assert c._pending_voice_control is None
    c.llm.generate_structured.assert_awaited()                       # processed as ordinary speech
    assert reply.response == "Tell me more."
    # and a later plain "yes" is just speech, not a stale confirmation
    run(c.process_candidate_input("yes"))
    assert c.context.current_phase == InterviewPhase.TECHNICAL


def test_arabic_end_request_is_confirmed_in_arabic():
    c = make_controller(InterviewPhase.TECHNICAL, language="ar")
    c.context.current_question = QUESTION_BANK[0]
    first = run(c.process_candidate_input("خلاص end the interview"))
    assert first.response == SYSTEM_MESSAGES["ar"]["confirm_end_interview"]
    run(c.process_candidate_input("نعم"))
    assert c.context.current_phase in (InterviewPhase.CLOSING, InterviewPhase.COMPLETED)


def test_skip_question_is_confirmed_and_confirmation_stays_out_of_llm_history():
    c = make_controller(InterviewPhase.TECHNICAL)
    c.context.current_question = QUESTION_BANK[0]
    first = run(c.process_candidate_input("skip this question"))
    assert first.action == ActionEnum.ASK and first.detected_candidate_control == CandidateControlAction.SKIP_QUESTION
    assert not any(m.role == "assistant" and "skip" in m.content.lower() for m in c.context.conversation_history)
    second = run(c.process_candidate_input("yeah"))
    assert second.detected_candidate_control == CandidateControlAction.SKIP_QUESTION


def test_hint_and_repeat_stay_immediate():
    c = make_controller(InterviewPhase.TECHNICAL)
    c.context.current_question = QUESTION_BANK[0]
    action = run(c.process_candidate_input("can you repeat the question"))
    assert action.detected_candidate_control == CandidateControlAction.REPEAT_QUESTION
    assert c._pending_voice_control is None
    assert CandidateControlAction.REQUEST_HINT not in CONFIRM_BEFORE_EXECUTING


@pytest.mark.parametrize("text,lang,expected", [
    ("yes", "en", True), ("Yeah, end it.", "en", True), ("sure go ahead", "en", True),
    ("no", "en", False), ("yes but not yet", "en", False), ("I don't think so", "en", False),
    ("yes I would use a hash map to keep track of the complements", "en", False),   # too long: an answer
    ("نعم", "ar", True), ("أكيد خلاص", "ar", True), ("لا كمّل", "ar", False), ("", "ar", False), (None, "en", False),
])
def test_is_affirmative(text, lang, expected):
    assert is_affirmative(text, lang) is expected
