"""Verbal Background subsection, step 3 -- live-flow edges in the controller.

docs/verbal-background-subsection-plan.md §2 "Live flow", §10, §11.
Background questions are ordinary VERBAL core questions tagged
source="BACKGROUND" at the front of the list (steps 1-2); these tests pin
the edge behaviour added around them: the 1-follow-up cap, no +2:00
grant, the spoken bridge at the Background -> Discussion boundary on
every path that can cross it, SKIP_BACKGROUND, the sub-clock, the
UI-state fields, the enriched records, and the CV in the evaluation
evidence.

Review mode: set CONTROLLER_UNDER_TEST to a path to run these against a
patched COPY of controller.py before the frozen file is touched.
"""
import asyncio
import importlib.util
import os
import sys
import time
from unittest.mock import AsyncMock

import pytest

_override = os.environ.get("CONTROLLER_UNDER_TEST")
if _override:
    _spec = importlib.util.spec_from_file_location("agent.interview.controller", _override)
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules["agent.interview.controller"] = _mod
    _spec.loader.exec_module(_mod)

from agent.interview.controller import InterviewController, VERBAL_FOLLOWUP_TIME_BONUS_SECONDS as BONUS  # noqa: E402
from agent.interview.models import (  # noqa: E402
    InterviewRuntimeContext, InterviewPhase, ActionEnum, StructuredAction,
    CandidateControlAction, QuestionOutcome, Question, OrderedSectionProgress,
)
from agent.interview.persistence import MockPersistence  # noqa: E402
from agent.llm.prompts import SYSTEM_MESSAGES  # noqa: E402

EN = SYSTEM_MESSAGES["en"]


def _q(qid, text, source, competency="communication"):
    return Question(
        id=qid, title=qid, problem_statement=text, difficulty="mid", competency=competency,
        expected_concepts=[], hints=[], follow_up_topics=[], time_budget_minutes=0,
        coding_required=False, source=source,
    )


def _controller(n_bg=2, n_hr=2, phase=InterviewPhase.BACKGROUND, bg_budget_min=5, extra_sections=False):
    ctx = InterviewRuntimeContext(
        session_id="bg-step3", candidate_id="cand", role="Backend Engineer", confirmed_level="mid",
        language="en", current_phase=phase, time_remaining_seconds=1200,
        candidate_profile={"professional_title": "Senior ML Engineer", "skills": ["Python"]},
    )
    questions = [_q(f"bg-{i}", f"Background question {i}?", "BACKGROUND", f"background:topic{i}") for i in range(1, n_bg + 1)]
    questions += [_q(f"hr-{i}", f"HR question {i}?", "HR_APPROVED") for i in range(1, n_hr + 1)]
    ctx.sections["VERBAL"] = OrderedSectionProgress(
        section_type="VERBAL", questions=questions, time_budget_minutes=20,
        include_background=True, background_question_count=n_bg, background_time_budget_minutes=bg_budget_min,
    )
    if extra_sections:
        ctx.sections["MCQ"] = OrderedSectionProgress(section_type="MCQ", questions=[_q("mcq-1", "Pick one.", "HR_APPROVED", "knowledge")])
    c = InterviewController(object(), MockPersistence(), ctx)
    if phase != InterviewPhase.CREATED:
        c.resume_timer()
    return c


def _script(controller, *actions):
    controller._generate_next_action = AsyncMock(side_effect=[
        StructuredAction(action=a, response=f"llm said ({a.value})", reason="scripted",
                         should_transition=(a == ActionEnum.TRANSITION))
        for a in actions
    ])


async def _drive(controller, *inputs):
    last = None
    for text in inputs:
        last = await controller.process_candidate_input(text)
    return last


def run(coro):
    return asyncio.run(coro)


# ── cap / grant ──────────────────────────────────────────────────────────────

def test_background_cap_is_one_followup_and_forced_advance_stays_in_background():
    async def scenario():
        c = _controller(n_bg=2, n_hr=1)
        section = c.context.sections["VERBAL"]
        assert c._current_max_followups() == 1
        _script(c, ActionEnum.ASK, ActionEnum.FOLLOW_UP, ActionEnum.FOLLOW_UP)
        await _drive(c, None, "answer 1")
        assert c.context.followups_used == 1 and section.current_index == 0
        forced = await c.process_candidate_input("answer 2")  # would be follow-up 2
        assert forced.action == ActionEnum.TRANSITION
        # mid-background: the ordinary "next question" bridge, next BACKGROUND question verbatim
        assert forced.response == f"{EN['core_followups_exhausted_next']} Background question 2?"
        assert section.current_index == 1 and section.current_question_asked is True
        assert c.context.question_records[-1].question_id == "bg-1"
        assert c.context.question_records[-1].followups_used == 1
        # discussion questions keep the normal cap
        section.current_index = 2
        assert c._current_max_followups() == 2
    run(scenario())


def test_no_time_grant_during_background_but_grant_resumes_in_discussion():
    async def scenario():
        c = _controller(n_bg=1, n_hr=1)
        _script(c, ActionEnum.ASK, ActionEnum.FOLLOW_UP)
        await _drive(c, None, "answer")
        assert c.context.followups_used == 1
        assert c.context.followup_time_bonus_seconds_total == 0
        assert c.generate_ui_state()["time_bonus_granted_seconds"] is None
        # move to the discussion question and probe once
        c.context.sections["VERBAL"].current_index = 1
        c.context.sections["VERBAL"].current_question_asked = True
        c.context.followups_used = 0
        _script(c, ActionEnum.FOLLOW_UP)
        await c.process_candidate_input("discussion answer")
        assert c.context.followup_time_bonus_seconds_total == BONUS
    run(scenario())


# ── the bridge, on every path across the boundary ────────────────────────────

def test_forced_advance_on_last_background_question_speaks_bridge_plus_hr1():
    async def scenario():
        c = _controller(n_bg=1, n_hr=2)
        section = c.context.sections["VERBAL"]
        _script(c, ActionEnum.ASK, ActionEnum.FOLLOW_UP, ActionEnum.FOLLOW_UP)
        await _drive(c, None, "a1")
        forced = await c.process_candidate_input("a2")
        assert forced.response == f"{EN['background_to_discussion']} HR question 1?"
        assert section.current_question.id == "hr-1" and section.current_question_asked is True
        assert c._pending_background_bridge is False
        assert c.generate_ui_state()["verbal_subsection"] == "DISCUSSION"
    run(scenario())


def test_voluntary_transition_on_last_background_question_appends_bridge_plus_hr1():
    async def scenario():
        c = _controller(n_bg=1, n_hr=2)
        section = c.context.sections["VERBAL"]
        _script(c, ActionEnum.ASK, ActionEnum.TRANSITION)
        await _drive(c, None)
        done = await c.process_candidate_input("a full answer")
        assert done.action == ActionEnum.TRANSITION
        assert done.response.startswith("llm said (TRANSITION)")
        assert done.response.endswith(f"{EN['background_to_discussion']} HR question 1?")
        assert section.current_question.id == "hr-1" and section.current_question_asked is True
        assert c._pending_background_bridge is False
    run(scenario())


def test_voluntary_transition_between_hr_questions_has_no_bridge():
    """Regression guard: the bridge only exists at the boundary."""
    async def scenario():
        c = _controller(n_bg=0, n_hr=2)
        _script(c, ActionEnum.ASK, ActionEnum.TRANSITION)
        await _drive(c, None)
        done = await c.process_candidate_input("answer")
        assert done.response == "llm said (TRANSITION)"
        assert EN["background_to_discussion"] not in done.response
    run(scenario())


def test_skip_question_on_last_background_question_bridges_on_the_chained_turn():
    async def scenario():
        c = _controller(n_bg=1, n_hr=2)
        section = c.context.sections["VERBAL"]
        _script(c, ActionEnum.ASK, ActionEnum.ASK)
        await _drive(c, None)
        skipped = await c.process_ui_command("SKIP_QUESTION")
        assert skipped.response == EN["skip_question"]
        assert c.context.question_records[-1].outcome == QuestionOutcome.SKIPPED
        assert c._pending_background_bridge is True
        # the voice adapter chains a turn; the LLM's first-turn ASK gets the bridge
        chained = await c.process_candidate_input("")
        assert chained.response == f"{EN['background_to_discussion']} HR question 1?"
        assert section.current_question_asked is True and c._pending_background_bridge is False
    run(scenario())


def test_skip_background_skips_rest_and_speaks_bridge_plus_hr1():
    async def scenario():
        c = _controller(n_bg=3, n_hr=2)
        section = c.context.sections["VERBAL"]
        _script(c, ActionEnum.ASK)
        await _drive(c, None)
        assert "SKIP_BACKGROUND" in c.generate_ui_state()["allowed_controls"]
        handled = await c.process_ui_command("SKIP_BACKGROUND")
        assert handled.action == ActionEnum.TRANSITION and handled.should_transition is False
        assert handled.response == f"{EN['background_skipped']} HR question 1?"
        assert [(r.question_id, r.outcome) for r in c.context.question_records] == [
            ("bg-1", QuestionOutcome.SKIPPED), ("bg-2", QuestionOutcome.SKIPPED), ("bg-3", QuestionOutcome.SKIPPED),
        ]
        assert section.current_question.id == "hr-1" and section.current_question_asked is True
        assert c.context.current_phase == InterviewPhase.BACKGROUND
        ui = c.generate_ui_state()
        assert ui["verbal_subsection"] == "DISCUSSION" and "SKIP_BACKGROUND" not in ui["allowed_controls"]
        # the spoken bridge is in the history so the LLM knows HR-1 was asked
        assert c.context.conversation_history[-1].content == handled.response
    run(scenario())


def test_skip_background_outside_background_is_a_rejected_noop():
    async def scenario():
        c = _controller(n_bg=1, n_hr=2)
        c.context.sections["VERBAL"].current_index = 1
        handled = await c.process_ui_command("SKIP_BACKGROUND")
        assert handled.action == ActionEnum.ACKNOWLEDGE
        assert c.context.question_records == []
        assert "SKIP_BACKGROUND" not in c.generate_ui_state()["allowed_controls"]
    run(scenario())


# ── the sub-clock ────────────────────────────────────────────────────────────

def test_subclock_starts_when_first_background_question_is_asked():
    async def scenario():
        c = _controller(n_bg=2, n_hr=1, bg_budget_min=5)
        assert c.context.background_deadline_epoch is None
        assert c.generate_ui_state()["background_time_remaining_seconds"] is None
        _script(c, ActionEnum.ASK)
        before = time.time()
        await _drive(c, None)
        assert c.context.background_deadline_epoch is not None
        assert 290 <= c.context.background_deadline_epoch - before <= 301
        ui = c.generate_ui_state()
        assert 290 <= ui["background_time_remaining_seconds"] <= 300
        # section clock untouched
        assert 1190 <= ui["time_remaining_seconds"] <= 1200
        # checkpoint carries the absolute deadline
        cp = c.persistence.storage["bg-step3"]["section_progress"]["verbal"]
        assert cp["background_deadline_epoch"] == c.context.background_deadline_epoch
    run(scenario())


def test_subclock_expiry_bridges_at_the_next_turn_without_an_llm_call():
    async def scenario():
        c = _controller(n_bg=3, n_hr=2, bg_budget_min=1)
        section = c.context.sections["VERBAL"]
        _script(c, ActionEnum.ASK)
        await _drive(c, None)
        c.context.background_deadline_epoch = time.time() - 1  # expired
        c._generate_next_action = AsyncMock(side_effect=AssertionError("LLM must not be called"))
        out = await c.process_candidate_input("my last background answer")
        assert out.action == ActionEnum.TRANSITION
        assert out.response == f"{EN['background_time_up']} HR question 1?"
        # answered one -> COMPLETED; never-asked ones -> TIME_EXPIRED
        assert [(r.question_id, r.outcome) for r in c.context.question_records] == [
            ("bg-1", QuestionOutcome.COMPLETED), ("bg-2", QuestionOutcome.TIME_EXPIRED), ("bg-3", QuestionOutcome.TIME_EXPIRED),
        ]
        assert section.current_question.id == "hr-1" and section.current_question_asked is True
        assert c.context.conversation_history[-2].content == "my last background answer"
        assert c.generate_ui_state()["background_time_remaining_seconds"] is None
    run(scenario())


def test_no_budget_means_no_subclock():
    async def scenario():
        c = _controller(n_bg=1, n_hr=1, bg_budget_min=None)
        _script(c, ActionEnum.ASK)
        await _drive(c, None)
        assert c.context.background_deadline_epoch is None
        assert c._background_time_expired() is False
    run(scenario())


# ── UI state / records / evidence ────────────────────────────────────────────

def test_ui_state_fields_and_plain_verbal_has_no_subsection():
    c = _controller(n_bg=2, n_hr=1)
    ui = c.generate_ui_state()
    assert (ui["verbal_subsection"], ui["background_total"], ui["background_index"]) == ("BACKGROUND", 2, 1)
    c.context.sections["VERBAL"].current_index = 1
    assert c.generate_ui_state()["background_index"] == 2
    c.context.sections["VERBAL"].current_index = 2
    ui = c.generate_ui_state()
    assert (ui["verbal_subsection"], ui["background_index"]) == ("DISCUSSION", None)

    plain = _controller(n_bg=0, n_hr=2)
    ui = plain.generate_ui_state()
    assert (ui["verbal_subsection"], ui["background_total"], ui["background_index"]) == (None, 0, None)
    assert "SKIP_BACKGROUND" not in ui["allowed_controls"]


def test_background_records_carry_their_text_and_hr_records_do_not():
    async def scenario():
        c = _controller(n_bg=1, n_hr=2)
        _script(c, ActionEnum.ASK, ActionEnum.TRANSITION, ActionEnum.TRANSITION)
        await _drive(c, None, "bg answer", "hr answer")
        bg, hr = c.context.question_records
        assert (bg.question_id, bg.subsection, bg.question_text, bg.competency) == ("bg-1", "BACKGROUND", "Background question 1?", "background:topic1")
        assert (hr.question_id, hr.subsection, hr.question_text) == ("hr-1", None, None)
        snap = c.persistence.storage["bg-step3"]["question_records"]
        assert snap[0]["subsection"] == "BACKGROUND" and snap[0]["question_text"] == "Background question 1?"
    run(scenario())


def test_evaluation_evidence_includes_candidate_profile():
    async def scenario():
        c = _controller(n_bg=1, n_hr=1)
        captured = {}

        async def fake_structured(system_prompt, messages, response_model):
            captured["messages"] = messages
            raise RuntimeError("stop here")

        c.llm = type("L", (), {"generate_structured": staticmethod(fake_structured)})()
        await c.generate_final_evaluation()
        import json
        evidence = json.loads(captured["messages"][0]["content"])
        assert evidence["candidate_profile"] == {"professional_title": "Senior ML Engineer", "skills": ["Python"]}
    run(scenario())


def test_kickoff_hop_starts_subclock_and_asks_first_background_question():
    """Through the real kick-off (BRIEFING -> WELCOME -> BACKGROUND hop)."""
    async def scenario():
        c = _controller(n_bg=2, n_hr=1, phase=InterviewPhase.CREATED)

        def generate(*_a, **_k):
            phase = c.context.current_phase
            if phase == InterviewPhase.BRIEFING:
                return StructuredAction(action=ActionEnum.ASK, response="Hi, ready?", reason="")
            if phase == InterviewPhase.WELCOME:
                return StructuredAction(action=ActionEnum.TRANSITION, response="Great, let's begin.", reason="", should_transition=True)
            return StructuredAction(action=ActionEnum.ASK, response="(core)", reason="")
        c._generate_next_action = AsyncMock(side_effect=generate)
        c.start_interview()
        await c.process_candidate_input(None)
        reply = await c.process_candidate_input("Hi, yes.")
        assert reply.response.endswith("Background question 1?")
        assert c.context.background_deadline_epoch is not None
        assert c.generate_ui_state()["verbal_subsection"] == "BACKGROUND"
    run(scenario())


# ── skip, from the greeting to the end ───────────────────────────────────────

def _first_turn_llm(c):
    """Model that ASKs (paraphrasing) on any core first turn, greets in BRIEFING."""
    def generate(*_a, **_k):
        if c.context.current_phase == InterviewPhase.BRIEFING:
            return StructuredAction(action=ActionEnum.ASK, response="Hi, ready?", reason="")
        if c.context.current_phase == InterviewPhase.CLOSING:
            return StructuredAction(action=ActionEnum.END, response="Thanks, goodbye.", reason="")
        return StructuredAction(action=ActionEnum.ASK, response="(paraphrase)", reason="")
    c._generate_next_action = AsyncMock(side_effect=generate)


def test_skip_on_the_greeting_hops_into_the_first_background_question():
    async def scenario():
        c = _controller(n_bg=2, n_hr=1, phase=InterviewPhase.CREATED)
        _first_turn_llm(c)
        c.start_interview()
        await c.process_candidate_input(None)  # greeting
        assert c.context.current_phase == InterviewPhase.BRIEFING

        skipped = await c.process_ui_command("SKIP_QUESTION")
        assert skipped.action == ActionEnum.TRANSITION
        assert skipped.response == EN["skip_intro"]
        assert c.context.current_phase == InterviewPhase.BACKGROUND
        assert c.context.question_records == []  # nothing was skipped, only the intro

        # the voice adapter chains a turn after a successful skip
        chained = await c.process_candidate_input("")
        assert chained.response.endswith("Background question 1?")
        assert c.context.sections["VERBAL"].current_question_asked is True
        assert c.context.background_deadline_epoch is not None
        assert c.generate_ui_state()["verbal_subsection"] == "BACKGROUND"
    run(scenario())


def test_skip_all_the_way_from_greeting_to_completed():
    """Skip on the greeting, skip every background question (bridge on the
    boundary), skip the only discussion question -> CLOSING -> COMPLETED.
    No waiting room with a single section."""
    async def scenario():
        c = _controller(n_bg=2, n_hr=1, phase=InterviewPhase.CREATED)
        _first_turn_llm(c)
        c.start_interview()
        await c.process_candidate_input(None)
        await c.process_ui_command("SKIP_QUESTION")           # intro
        await c.process_candidate_input("")                    # chained: bg-1 asked

        s1 = await c.process_ui_command("SKIP_QUESTION")       # bg-1 skipped
        assert s1.response == EN["skip_question"]
        t2 = await c.process_candidate_input("")               # chained: bg-2 asked
        assert t2.response.endswith("Background question 2?")

        await c.process_ui_command("SKIP_QUESTION")            # bg-2 skipped -> boundary
        t3 = await c.process_candidate_input("")               # chained: bridge + HR-1
        assert t3.response == f"{EN['background_to_discussion']} HR question 1?"
        assert c.generate_ui_state()["verbal_subsection"] == "DISCUSSION"

        last = await c.process_ui_command("SKIP_QUESTION")     # HR-1 skipped -> section done
        assert last.action == ActionEnum.TRANSITION
        assert c.context.current_phase == InterviewPhase.CLOSING
        end = await c.process_candidate_input("")              # chained: closing turn
        assert end.action == ActionEnum.END
        assert c.context.current_phase == InterviewPhase.COMPLETED
        assert [(r.question_id, r.outcome) for r in c.context.question_records] == [
            ("bg-1", QuestionOutcome.SKIPPED), ("bg-2", QuestionOutcome.SKIPPED), ("hr-1", QuestionOutcome.SKIPPED)]
    run(scenario())


def test_skip_on_the_greeting_of_a_legacy_session_is_unchanged():
    """No HR content -> the old free-form flow keeps its own skip semantics."""
    async def scenario():
        c = _controller(n_bg=0, n_hr=0, phase=InterviewPhase.CREATED)
        c.context.sections = {}
        _first_turn_llm(c)
        c.start_interview()
        await c.process_candidate_input(None)
        out = await c.process_ui_command("SKIP_QUESTION")
        assert c.context.current_phase != InterviewPhase.BACKGROUND or out.response != EN["skip_intro"]
    run(scenario())
