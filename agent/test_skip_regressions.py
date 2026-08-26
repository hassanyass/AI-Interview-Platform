import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.interview.controller import InterviewController
from agent.interview.models import (
    CandidateControlAction,
    InterviewPhase,
    InterviewRuntimeContext,
    OrderedSectionProgress,
)
from agent.interview.persistence import MockPersistence
from agent.interview.questions import QUESTION_BANK
from agent.interview.questions import rank_questions_for_context
from agent.interview.question_generator import generate_custom_question
from agent.interview.models import Question
from agent.llm.prompts import SYSTEM_MESSAGES


def make_controller(phase: InterviewPhase) -> InterviewController:
    context = InterviewRuntimeContext(
        session_id="skip-regression",
        candidate_id="candidate",
        role="Backend Engineer",
        confirmed_level="junior",
        language="en",
        current_phase=phase,
        time_remaining_seconds=1800,
    )
    controller = InterviewController(object(), MockPersistence(), context)
    return controller


def test_question_ranking_uses_job_and_profile_context():
    ranked = rank_questions_for_context(
        role="Senior Backend Engineer",
        job_description="Design distributed APIs with PostgreSQL and Redis at scale.",
        candidate_profile={"skills": ["Python", "FastAPI"], "projects": ["built microservices"]},
        difficulty="senior",
    )

    assert ranked[0].id == "q3"
    assert ranked[0].competency == "system_design"


def test_resume_timer_starts_without_reentering_phase():
    controller = make_controller(InterviewPhase.TECHNICAL)

    controller.resume_timer()

    assert controller._start_time is not None
    assert controller.context.current_phase == InterviewPhase.TECHNICAL


def test_custom_question_generator_uses_structured_context():
    class QuestionLLM:
        async def generate_structured(self, system_prompt, messages, response_model):
            assert "Distributed APIs" in system_prompt
            assert "FastAPI" in system_prompt
            return Question(
                id="temporary",
                title="Tenant-aware request queue",
                problem_statement="Implement a bounded queue for tenant requests.",
                difficulty="senior",
                competency="system_design",
                expected_concepts=["hash_map", "queue"],
                hints=["Group requests by tenant."] * 4,
                follow_up_topics=["How would you handle starvation?"],
                time_budget_minutes=12,
                coding_required=True,
            )

    async def scenario():
        question = await generate_custom_question(
            QuestionLLM(),
            role="Senior Backend Engineer",
            level="senior",
            language="en",
            job_description="Distributed APIs with PostgreSQL and FastAPI.",
            candidate_profile={"skills": ["FastAPI"], "projects": ["Built tenant services"]},
        )
        assert question.id.startswith("custom-")
        assert question.coding_required is True
        assert question.supported_languages == ["python"]

    asyncio.run(scenario())


def test_runtime_technical_transition_exposes_generated_question():
    async def scenario():
        controller = make_controller(InterviewPhase.TECHNICAL_INTRO)
        generated = Question(
            id="custom-document-intelligence",
            title="OCR document ingestion pipeline",
            problem_statement="Implement the core batching step for OCR documents stored in object storage.",
            difficulty="junior",
            competency="document_intelligence",
            expected_concepts=["batching", "validation"],
            hints=["Start with the input contract."] * 4,
            follow_up_topics=["How would you retry failed documents?"],
            time_budget_minutes=10,
            coding_required=True,
            starter_code={"python": ""},
            supported_languages=["python"],
            source="LLM_GENERATED",
        )
        calls = []

        async def generator():
            calls.append(True)
            return generated

        controller.set_question_generator(generator)
        controller.set_custom_question(await controller._generate_personalized_question())
        controller._transition_to(InterviewPhase.TECHNICAL)
        state = controller.generate_ui_state()

        assert len(calls) == 1
        assert controller.context.current_question is generated
        assert controller.context.current_question.id not in {question.id for question in QUESTION_BANK}
        assert state["current_question"]["id"] == "custom-document-intelligence"
        assert state["current_question"]["source"] == "LLM_GENERATED"

    asyncio.run(scenario())


def test_skipping_generated_question_uses_personalized_replacement_not_question_bank():
    async def scenario():
        controller = make_controller(InterviewPhase.TECHNICAL)
        controller.context.job_description = "Build OCR document intelligence APIs with FastAPI and Redis."
        controller.context.candidate_profile = {"skills": ["OCR", "FastAPI", "Redis"]}
        first = Question(
            id="custom-first", title="OCR ingestion batching", problem_statement="Process OCR documents in batches.", difficulty="junior",
            competency="document_intelligence", expected_concepts=["batching"], hints=["Define the batch contract."] * 4,
            follow_up_topics=["Retries"], time_budget_minutes=10, coding_required=True, starter_code={"python": ""},
            supported_languages=["python"], source="LLM_GENERATED",
        )
        second = first.model_copy(update={"id": "custom-second", "title": "Redis-backed OCR deduplication", "source": "LLM_GENERATED"})
        controller.load_question(first)
        calls = []

        async def generator():
            calls.append((controller.context.job_description, controller.context.candidate_profile.copy()))
            return second

        controller.set_question_generator(generator)
        replacement_action = await controller._handle_candidate_control(CandidateControlAction.SKIP_QUESTION)

        assert replacement_action is not None
        assert controller.context.current_question.id == "custom-second"
        assert controller.context.current_question.source == "LLM_GENERATED"
        assert calls == [("Build OCR document intelligence APIs with FastAPI and Redis.", {"skills": ["OCR", "FastAPI", "Redis"]})]
        assert controller.context.current_question.id not in {question.id for question in QUESTION_BANK}

    asyncio.run(scenario())


def test_background_skip_stays_in_background_until_maximum():
    async def scenario():
        controller = make_controller(InterviewPhase.BACKGROUND)
        progress = controller.context.background_progress
        progress.questions_asked = 1
        progress.limits.max_questions = 3

        action = await controller._handle_candidate_control(
            CandidateControlAction.SKIP_QUESTION
        )

        assert action is not None
        assert controller.context.current_phase == InterviewPhase.BACKGROUND
        assert progress.questions_asked == 1
        assert progress.completed is False

    asyncio.run(scenario())


def test_arabic_background_skip_uses_same_progression():
    async def scenario():
        controller = make_controller(InterviewPhase.BACKGROUND)
        controller.context.language = "ar"
        controller.context.background_progress.questions_asked = 1
        controller.context.background_progress.limits.max_questions = 2

        await controller._handle_candidate_control(
            CandidateControlAction.SKIP_QUESTION
        )

        assert controller.context.current_phase == InterviewPhase.BACKGROUND
        assert controller.context.background_progress.questions_asked == 1

    asyncio.run(scenario())


def test_final_background_skip_enters_technical_intro_then_technical():
    async def scenario():
        controller = make_controller(InterviewPhase.BACKGROUND)
        progress = controller.context.background_progress
        progress.questions_asked = progress.limits.max_questions

        await controller._handle_candidate_control(
            CandidateControlAction.SKIP_QUESTION
        )

        assert controller.context.current_phase == InterviewPhase.TECHNICAL_INTRO
        assert controller.context.current_question is not None

        controller._transition_to(InterviewPhase.TECHNICAL)
        assert controller.context.current_phase == InterviewPhase.TECHNICAL
        assert controller.context.current_question is not None

    asyncio.run(scenario())


def test_technical_skip_uses_self_transition_and_loads_next_question():
    async def scenario():
        controller = make_controller(InterviewPhase.TECHNICAL)
        controller.context.current_question = QUESTION_BANK[0]

        await controller._handle_candidate_control(
            CandidateControlAction.SKIP_QUESTION
        )

        assert controller.context.current_phase == InterviewPhase.TECHNICAL
        assert controller.context.current_question is not None
        assert controller.context.current_question.id != QUESTION_BANK[0].id
        assert controller.context.technical_progress.questions_skipped == 1

    asyncio.run(scenario())


# ─── Issue 6 fix: SKIP_QUESTION/SKIP_SECTION/MOVE_TO_TECHNICAL vs.
# HR-approved core sections (context.sections) ──────────────────────────────
#
# Root cause: SKIP_QUESTION/SKIP_SECTION/MOVE_TO_TECHNICAL predate Phase
# 7D/9B's ordered core-question walk and jump straight into the legacy
# TECHNICAL_INTRO/TECHNICAL phase without ever checking
# _active_core_section()/context.sections — unlike _handle_automatic_
# transition(), which already checks it correctly for the LLM-TRANSITION-
# driven path. Each control below is tested BOTH with an active core section
# (must no-op/acknowledge, never touch the legacy technical phase) and
# without one (legacy behavior must be provably unchanged).

def _b2b_controller_with_active_verbal_section(phase: InterviewPhase = InterviewPhase.BACKGROUND):
    """A controller whose context has one incomplete, HR-approved VERBAL
    section — i.e. _active_core_section() returns non-None."""
    context = make_controller(phase).context
    question = Question(
        id="core-q1", title="Core Q1", problem_statement="Tell me about yourself.",
        difficulty="mid", competency="communication",
        expected_concepts=[], hints=[], follow_up_topics=[], time_budget_minutes=0,
        coding_required=False, source="HR_APPROVED",
    )
    context.sections["VERBAL"] = OrderedSectionProgress(section_type="VERBAL", questions=[question])
    return InterviewController(object(), MockPersistence(), context)


def test_skip_question_is_noop_when_core_section_active():
    async def scenario():
        controller = _b2b_controller_with_active_verbal_section()

        action = await controller._handle_candidate_control(CandidateControlAction.SKIP_QUESTION)

        assert action is not None
        assert action.should_transition is False
        assert action.response == SYSTEM_MESSAGES["en"]["core_section_no_skip"]
        # Nothing about the core section or phase moved.
        assert controller.context.current_phase == InterviewPhase.BACKGROUND
        assert controller.context.sections["VERBAL"].completed is False
        assert controller.context.sections["VERBAL"].current_index == 0

    asyncio.run(scenario())


def test_skip_question_is_noop_when_core_section_pending_during_briefing():
    """The actual Issue 6 repro: the candidate clicks Skip while still in
    BRIEFING, before the interview has ever reached BACKGROUND. Deliberately
    a SEPARATE test from the BACKGROUND-phase case above —
    _active_core_section() is phase-gated to only BACKGROUND by design, so a
    check against it (rather than _has_pending_core_content()) passes the
    BACKGROUND-phase test above while still missing this exact case, which
    is precisely the bug caught by this fix's own live verification."""
    async def scenario():
        controller = _b2b_controller_with_active_verbal_section(phase=InterviewPhase.BRIEFING)

        action = await controller._handle_candidate_control(CandidateControlAction.SKIP_QUESTION)

        assert action is not None
        assert action.should_transition is False
        assert action.response == SYSTEM_MESSAGES["en"]["core_section_no_skip"]
        # Must NOT have cascaded into WELCOME/BACKGROUND/TECHNICAL_INTRO.
        assert controller.context.current_phase == InterviewPhase.BRIEFING
        assert controller.context.sections["VERBAL"].completed is False

    asyncio.run(scenario())


def test_skip_question_is_noop_when_core_section_pending_during_welcome():
    async def scenario():
        controller = _b2b_controller_with_active_verbal_section(phase=InterviewPhase.WELCOME)

        action = await controller._handle_candidate_control(CandidateControlAction.SKIP_QUESTION)

        assert action.response == SYSTEM_MESSAGES["en"]["core_section_no_skip"]
        assert controller.context.current_phase == InterviewPhase.WELCOME
        assert controller.context.sections["VERBAL"].completed is False

    asyncio.run(scenario())


def test_skip_section_is_noop_when_core_section_active():
    """Per product decision, SKIP_SECTION gets the identical no-op treatment
    as SKIP_QUESTION while a core section is active — it is NOT an escape
    hatch to the next section for B2B sessions."""
    async def scenario():
        controller = _b2b_controller_with_active_verbal_section()

        action = await controller._handle_candidate_control(CandidateControlAction.SKIP_SECTION)

        assert action is not None
        assert action.should_transition is False
        assert action.response == SYSTEM_MESSAGES["en"]["core_section_no_skip"]
        assert controller.context.current_phase == InterviewPhase.BACKGROUND
        assert controller.context.sections["VERBAL"].completed is False

    asyncio.run(scenario())


def test_skip_question_arabic_message_when_core_section_active():
    async def scenario():
        controller = _b2b_controller_with_active_verbal_section()
        controller.context.language = "ar"

        action = await controller._handle_candidate_control(CandidateControlAction.SKIP_QUESTION)

        assert action.response == SYSTEM_MESSAGES["ar"]["core_section_no_skip"]

    asyncio.run(scenario())


def test_skip_question_legacy_behavior_unchanged_without_core_sections():
    """Regression guard: a plain legacy session (context.sections empty) —
    _active_core_section() is None, so SKIP_QUESTION must behave exactly as
    it always has (see test_background_skip_stays_in_background_until_maximum
    and test_final_background_skip_enters_technical_intro_then_technical for
    the full existing coverage; this just pins the "not core-section-gated"
    invariant explicitly)."""
    async def scenario():
        controller = make_controller(InterviewPhase.BACKGROUND)
        assert controller.context.sections == {}
        progress = controller.context.background_progress
        progress.questions_asked = progress.limits.max_questions

        action = await controller._handle_candidate_control(CandidateControlAction.SKIP_QUESTION)

        assert action.response != SYSTEM_MESSAGES["en"]["core_section_no_skip"]
        assert controller.context.current_phase == InterviewPhase.TECHNICAL_INTRO

    asyncio.run(scenario())


def test_move_to_technical_is_noop_when_sections_present():
    async def scenario():
        controller = _b2b_controller_with_active_verbal_section()

        action = await controller._handle_candidate_control(CandidateControlAction.MOVE_TO_TECHNICAL)

        assert action is not None
        assert action.should_transition is False
        assert action.response == SYSTEM_MESSAGES["en"]["core_move_to_technical_unavailable"]
        assert controller.context.current_phase == InterviewPhase.BACKGROUND

    asyncio.run(scenario())


def test_move_to_technical_is_noop_even_when_core_sections_are_already_exhausted():
    """Per product decision: disabled whenever context.sections is
    non-empty, regardless of whether any section is still active — not just
    while a section is currently in progress."""
    async def scenario():
        controller = _b2b_controller_with_active_verbal_section(phase=InterviewPhase.CLOSING)
        controller.context.sections["VERBAL"].completed = True
        controller.context.sections["VERBAL"].current_index = 1  # past the only question

        action = await controller._handle_candidate_control(CandidateControlAction.MOVE_TO_TECHNICAL)

        assert action is not None
        assert action.response == SYSTEM_MESSAGES["en"]["core_move_to_technical_unavailable"]
        assert controller.context.current_phase == InterviewPhase.CLOSING

    asyncio.run(scenario())


def test_move_to_technical_legacy_behavior_unchanged_without_sections():
    """Regression guard: MOVE_TO_TECHNICAL had no prior test coverage at
    all — this pins its existing (correct, for legacy sessions) behavior
    before/alongside the Issue 6 fix."""
    async def scenario():
        controller = make_controller(InterviewPhase.BACKGROUND)
        assert controller.context.sections == {}

        action = await controller._handle_candidate_control(CandidateControlAction.MOVE_TO_TECHNICAL)

        assert action is not None
        assert action.response != SYSTEM_MESSAGES["en"]["core_move_to_technical_unavailable"]
        assert controller.context.current_phase == InterviewPhase.TECHNICAL_INTRO

    asyncio.run(scenario())


# ─── WR-C: waiting-room boundary wiring ─────────────────────────────────────
# See docs/section-pacing-architecture.md. section_type must be unique per
# definition, so two-section scenarios use VERBAL + CODING (not two
# VERBALs) — not exercising CODING's own candidate-facing flow, just using
# it as a second, independently-budgeted core section.

def _two_section_controller(first_budget=10, second_budget=20, phase=InterviewPhase.BACKGROUND):
    context = make_controller(phase).context
    verbal_q = Question(
        id="v-q1", title="V1", problem_statement="Tell me about yourself.",
        difficulty="mid", competency="communication",
        expected_concepts=[], hints=[], follow_up_topics=[], time_budget_minutes=0,
        coding_required=False, source="HR_APPROVED",
    )
    coding_q = Question(
        id="c-q1", title="C1", problem_statement="Implement a rate limiter.",
        difficulty="mid", competency="systems",
        expected_concepts=[], hints=[], follow_up_topics=[], time_budget_minutes=0,
        coding_required=True, source="HR_APPROVED",
    )
    context.sections["VERBAL"] = OrderedSectionProgress(
        section_type="VERBAL", questions=[verbal_q], time_budget_minutes=first_budget,
    )
    context.sections["CODING"] = OrderedSectionProgress(
        section_type="CODING", questions=[coding_q], time_budget_minutes=second_budget,
    )
    return InterviewController(object(), MockPersistence(), context)


def test_exhausting_a_section_with_another_remaining_enters_waiting_room_not_closing():
    """The exact boundary 9B built as invisible: finishing VERBAL (the
    first section) with CODING still to go must stop at WAITING_ROOM, not
    silently continue into CODING's first question in the same turn."""
    from agent.interview.models import StructuredAction, ActionEnum

    class AskThenTransitionLLM:
        def __init__(self):
            self.calls = 0

        async def generate_structured(self, system_prompt, messages, response_model):
            self.calls += 1
            if self.calls % 2 == 1:
                return StructuredAction(action=ActionEnum.ASK, response="Q.", reason="Posing.")
            return StructuredAction(
                action=ActionEnum.TRANSITION, response="Thanks.", reason="Sufficient.",
                should_transition=True,
            )

    async def scenario():
        controller = _two_section_controller()
        controller.llm = AskThenTransitionLLM()
        # Nothing seeds _total_duration_sec from a section's own budget
        # except _start_section_clock() (only called on the way OUT of
        # WAITING_ROOM) — capture the pre-walk value to prove it's
        # genuinely left untouched by entering WAITING_ROOM, rather than
        # asserting a specific number nothing was ever supposed to set.
        duration_before = controller._total_duration_sec

        await controller.process_candidate_input()  # ASK v-q1
        await controller.process_candidate_input()  # TRANSITION -> exhausts VERBAL

        assert controller.context.current_phase == InterviewPhase.WAITING_ROOM
        assert controller.context.sections["VERBAL"].completed is True
        # CODING untouched — not silently advanced into.
        assert controller.context.sections["CODING"].current_index == 0
        assert controller.context.sections["CODING"].completed is False
        # The just-finished section's clock is deliberately left stale —
        # only reset on the way OUT of WAITING_ROOM, not on the way in.
        assert controller._total_duration_sec == duration_before

    asyncio.run(scenario())


def test_proceed_to_next_section_advances_with_a_freshly_reseeded_clock():
    async def scenario():
        controller = _two_section_controller(
            first_budget=10, second_budget=20, phase=InterviewPhase.WAITING_ROOM,
        )
        controller.context.sections["VERBAL"].completed = True
        controller.context.sections["VERBAL"].current_index = 1
        controller._total_duration_sec = 3  # stale leftover from VERBAL, about to expire

        action = await controller._handle_candidate_control(CandidateControlAction.PROCEED_TO_NEXT_SECTION)

        assert action is not None
        assert action.should_transition is False
        assert controller.context.current_phase == InterviewPhase.BACKGROUND
        assert controller._active_core_section() is controller.context.sections["CODING"]
        assert controller._total_duration_sec == 20 * 60
        # Candidate-initiated -> logged distinctly from an auto-timeout proceed.
        assert controller.persistence.events[-1]["event_type"] == "WAITING_ROOM_CANDIDATE_PROCEED"

    asyncio.run(scenario())


def test_proceed_to_next_section_is_noop_outside_waiting_room():
    async def scenario():
        controller = _two_section_controller(phase=InterviewPhase.BACKGROUND)

        action = await controller._handle_candidate_control(CandidateControlAction.PROCEED_TO_NEXT_SECTION)

        assert action is None
        assert controller.context.current_phase == InterviewPhase.BACKGROUND

    asyncio.run(scenario())


def test_waiting_room_auto_timeout_helper_logs_distinctly_from_candidate_proceed():
    async def scenario():
        controller = _two_section_controller(
            first_budget=10, second_budget=20, phase=InterviewPhase.WAITING_ROOM,
        )
        controller.context.sections["VERBAL"].completed = True
        controller.context.sections["VERBAL"].current_index = 1

        await controller._transition_out_of_waiting_room(auto=True)

        assert controller.context.current_phase == InterviewPhase.BACKGROUND
        assert controller._total_duration_sec == 20 * 60
        assert controller.persistence.events[-1]["event_type"] == "WAITING_ROOM_AUTO_PROCEED"

    asyncio.run(scenario())


def test_waiting_room_is_silent_and_unclocked_for_incidental_candidate_input():
    """CURRENT_DECISIONS.md: the waiting room is explicitly free/unclocked.
    Incidental candidate speech while waiting must not reach LLM
    generation, and — critically — must not force a transition even though
    the just-finished section's clock is deliberately left stale (and
    could easily read as already expired)."""
    async def scenario():
        controller = _two_section_controller(
            first_budget=10, second_budget=20, phase=InterviewPhase.WAITING_ROOM,
        )
        controller.context.sections["VERBAL"].completed = True
        controller._total_duration_sec = -999  # deliberately already "expired"
        controller.llm = MagicMock()  # would fail loudly if ever actually called

        action = await controller.process_candidate_input("just some background noise")

        assert action.response == ""
        assert action.should_transition is False
        assert controller.context.current_phase == InterviewPhase.WAITING_ROOM
        controller.llm.generate_structured.assert_not_called()

    asyncio.run(scenario())


def test_generate_ui_state_hides_time_remaining_during_waiting_room():
    controller = _two_section_controller(phase=InterviewPhase.WAITING_ROOM)
    controller._total_duration_sec = -999

    state = controller.generate_ui_state()

    assert state["time_remaining_seconds"] is None


def test_generate_ui_state_reports_time_remaining_outside_waiting_room():
    controller = _two_section_controller(phase=InterviewPhase.BACKGROUND)

    state = controller.generate_ui_state()

    assert state["time_remaining_seconds"] is not None


def test_submit_code_exhausting_a_section_with_another_remaining_enters_waiting_room():
    """Same section-boundary branching as the automatic-TRANSITION case
    above, exercised via the explicit SUBMIT_CODE data-channel path
    (process_ui_command), which has its own separate _advance_core_
    question() call site."""
    async def scenario():
        controller = _two_section_controller(first_budget=10, second_budget=20)
        # Make CODING the active section by exhausting VERBAL directly.
        controller.context.sections["VERBAL"].completed = True
        controller.context.sections["VERBAL"].current_index = 1
        # A third section still pending after CODING — otherwise CODING
        # would genuinely be the LAST remaining section and CLOSING would
        # be the correct (unchanged) outcome, not what this test means to
        # exercise.
        mcq_q = Question(
            id="m-q1", title="M1", problem_statement="Pick the best answer.",
            difficulty="mid", competency=None,
            expected_concepts=[], hints=[], follow_up_topics=[], time_budget_minutes=0,
            coding_required=False, source="HR_APPROVED",
        )
        controller.context.sections["MCQ"] = OrderedSectionProgress(
            section_type="MCQ", questions=[mcq_q], time_budget_minutes=15,
        )

        action = await controller.process_ui_command("SUBMIT_CODE", {"payload": {"code": "def f(): pass", "language": "python"}})

        assert action is not None
        assert controller.context.current_phase == InterviewPhase.WAITING_ROOM
        assert controller.context.sections["CODING"].completed is True
        assert controller.context.sections["MCQ"].completed is False

    asyncio.run(scenario())


def test_multiple_technical_skips_keep_a_question_loaded_until_final_limit():
    async def scenario():
        controller = make_controller(InterviewPhase.TECHNICAL)
        controller.context.technical_progress.limits.max_questions = 3
        controller.context.current_question = QUESTION_BANK[0]

        await controller._handle_candidate_control(
            CandidateControlAction.SKIP_QUESTION
        )
        first_replacement = controller.context.current_question.id
        await controller._handle_candidate_control(
            CandidateControlAction.SKIP_QUESTION
        )

        assert first_replacement != QUESTION_BANK[0].id
        assert controller.context.current_question is not None
        assert controller.context.technical_progress.questions_skipped == 2

    asyncio.run(scenario())


def test_state_payload_after_technical_skip_has_current_question():
    async def scenario():
        controller = make_controller(InterviewPhase.TECHNICAL)
        controller.context.current_question = QUESTION_BANK[0]
        await controller._handle_candidate_control(
            CandidateControlAction.SKIP_QUESTION
        )
        state = controller.generate_ui_state()
        assert state["phase"] == "TECHNICAL"
        assert state["current_question"] is not None
        assert state["questions_skipped"] == 1

    asyncio.run(scenario())


def test_duplicate_skip_commands_leave_consistent_technical_state():
    async def scenario():
        controller = make_controller(InterviewPhase.TECHNICAL)
        controller.context.current_question = QUESTION_BANK[0]
        await controller._handle_candidate_control(CandidateControlAction.SKIP_QUESTION)
        await controller._handle_candidate_control(CandidateControlAction.SKIP_QUESTION)
        assert controller.context.current_phase == InterviewPhase.TECHNICAL
        assert controller.context.current_question is not None
        assert controller.context.technical_progress.questions_skipped == 2

    asyncio.run(scenario())


def test_tts_interruption_invalidates_pending_generation():
    from agent.interview.voice_adapter import VoiceInterviewAdapter

    async def scenario():
        adapter = object.__new__(VoiceInterviewAdapter)
        adapter._is_interrupted = False
        adapter._generation_id = 4
        adapter._tts_queue = asyncio.Queue()
        await adapter._tts_queue.put(("pending", 1, 1, 4))
        adapter._current_synthesis_task = None
        # RT-B1: prove clear_queue() -- the SDK method that discards audio
        # already captured but not yet played -- actually gets called, not
        # just that internal state flips. This is exactly the gap RT-A
        # found: the prior version of this test never set _audio_source at
        # all, so it could only prove "generation marked stale," never "old
        # audio stopped playing."
        class FakeAudioSource:
            def __init__(self):
                self.clear_queue_calls = 0

            def clear_queue(self):
                self.clear_queue_calls += 1

        adapter._audio_source = FakeAudioSource()

        adapter._handle_interruption()

        assert adapter._is_interrupted is True
        assert adapter._generation_id == 5
        assert adapter._tts_queue.empty()
        assert adapter._audio_source.clear_queue_calls == 1

    asyncio.run(scenario())


def test_skip_acknowledgement_is_not_added_to_llm_history():
    async def scenario():
        controller = make_controller(InterviewPhase.TECHNICAL)
        controller.context.current_question = QUESTION_BANK[0]

        await controller.process_candidate_input("skip this question")

        assert not any(
            message.role == "assistant" and "skip" in message.content.lower()
            for message in controller.context.conversation_history
        )

    asyncio.run(scenario())


def test_vad_segments_are_coalesced_into_one_candidate_turn():
    from agent.interview.voice_adapter import VoiceInterviewAdapter

    async def scenario():
        adapter = object.__new__(VoiceInterviewAdapter)
        adapter._candidate_endpoint_delay = 0
        adapter._pending_candidate_parts = [
            "I would start with a hash map",
            "and then check each complement",
        ]
        adapter._last_final_candidate_text = ""
        adapter._candidate_turn_id = 0
        adapter._processed_candidate_turns = set()
        turns = []

        async def capture(text, **kwargs):
            turns.append((text, kwargs["turn_id"]))

        adapter._handle_candidate_turn = capture
        await adapter._finalize_pending_candidate_after_endpoint()

        assert turns == [("I would start with a hash map and then check each complement", 1)]

    asyncio.run(scenario())


def test_duplicate_final_turn_is_ignored():
    from agent.interview.voice_adapter import VoiceInterviewAdapter

    async def scenario():
        adapter = object.__new__(VoiceInterviewAdapter)
        adapter._candidate_endpoint_delay = 0
        adapter._candidate_turn_id = 0
        adapter._processed_candidate_turns = set()
        adapter._last_final_candidate_text = "same answer"
        adapter._last_final_candidate_at = asyncio.get_running_loop().time()
        adapter._pending_candidate_parts = ["same answer"]
        turns = []

        async def capture(*args, **kwargs):
            turns.append(args[0])

        adapter._handle_candidate_turn = capture
        await adapter._finalize_pending_candidate_after_endpoint()

        assert turns == []

    asyncio.run(scenario())


def test_candidate_speech_invalidates_old_tts_generation():
    from agent.interview.voice_adapter import VoiceInterviewAdapter

    async def scenario():
        adapter = object.__new__(VoiceInterviewAdapter)
        adapter._is_interrupted = False
        adapter._generation_id = 12
        adapter._tts_queue = asyncio.Queue()
        adapter._current_synthesis_task = None
        # RT-B1: same clear_queue() proof as the barge-in test above, for
        # the candidate-continues-speaking trigger path specifically.
        class FakeAudioSource:
            def __init__(self):
                self.clear_queue_calls = 0

            def clear_queue(self):
                self.clear_queue_calls += 1

        adapter._audio_source = FakeAudioSource()

        adapter._handle_interruption()

        assert adapter._generation_id == 13
        assert adapter._is_interrupted is True
        assert adapter._audio_source.clear_queue_calls == 1

    asyncio.run(scenario())


def test_handle_interruption_tolerates_missing_audio_source():
    """RT-B1: the interruption path must not crash on an adapter that never
    had _audio_source set at all (e.g. interruption logic exercised before
    start() has run) -- getattr(..., None) guards this explicitly."""
    from agent.interview.voice_adapter import VoiceInterviewAdapter

    adapter = object.__new__(VoiceInterviewAdapter)
    adapter._is_interrupted = False
    adapter._generation_id = 1
    adapter._tts_queue = asyncio.Queue()
    adapter._current_synthesis_task = None
    assert not hasattr(adapter, "_audio_source")

    adapter._handle_interruption()  # must not raise

    assert adapter._generation_id == 2


# ─── RT-B0 — Instrumentation ─────────────────────────────────────────────

def test_rtb0_llm_duration_metrics_logged_without_changing_behavior(caplog):
    """RT-B0: GroqProvider is a raw client call, not an SDK stt/tts plugin,
    so it has no metrics_collected event to wire up -- duration has to be
    measured explicitly. Proves the log line fires with the real duration/
    usage fields, and that adding it doesn't change the parsed return value."""
    from unittest.mock import AsyncMock, MagicMock
    from pydantic import BaseModel
    from agent.llm.groq_provider import GroqProvider

    class Dummy(BaseModel):
        value: str

    async def scenario():
        provider = object.__new__(GroqProvider)  # bypass __init__'s env-var requirement
        provider.model = "test-model"

        fake_response = MagicMock()
        fake_response.choices = [MagicMock(message=MagicMock(content='{"value": "ok"}'))]
        fake_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        provider.client = MagicMock()
        provider.client.chat.completions.create = AsyncMock(return_value=fake_response)

        with caplog.at_level("INFO"):
            result = await provider.generate_structured(
                system_prompt="test", messages=[{"role": "user", "content": "hi"}],
                response_model=Dummy,
            )

        assert result.value == "ok"  # behavior unchanged
        metrics_lines = [r.message for r in caplog.records if "[LLM-METRICS]" in r.message]
        assert len(metrics_lines) == 1
        assert "duration_ms=" in metrics_lines[0]
        assert "prompt_tokens=10" in metrics_lines[0]
        assert "completion_tokens=5" in metrics_lines[0]
        assert "total_tokens=15" in metrics_lines[0]

    asyncio.run(scenario())


def test_rtb0_stt_and_tts_metrics_handlers_log_sdk_provided_fields(caplog):
    """RT-B0: wires up stt.STT/tts.TTS's existing metrics_collected event
    (SDK-provided, previously zero listeners anywhere in this codebase)
    rather than hand-building STT/TTS timing."""
    from agent.interview.voice_adapter import VoiceInterviewAdapter

    class FakeMetrics:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    adapter = object.__new__(VoiceInterviewAdapter)

    with caplog.at_level("INFO"):
        adapter._on_stt_metrics(FakeMetrics(request_id="stt-1", duration=0.42, audio_duration=1.1))
        adapter._on_tts_metrics(FakeMetrics(
            request_id="tts-1", ttfb=0.1, duration=0.5, audio_duration=2.0, cancelled=False,
        ))

    stt_lines = [r.message for r in caplog.records if "[STT-METRICS]" in r.message]
    tts_lines = [r.message for r in caplog.records if "[TTS-METRICS]" in r.message]
    assert len(stt_lines) == 1 and "stt-1" in stt_lines[0]
    assert len(tts_lines) == 1 and "tts-1" in tts_lines[0]


# ─── RT-B2 — Provisional preservation of non-mid-playback responses ────────

def test_rtb2_is_speaking_set_on_first_frame_and_reset_on_completion_and_cancellation():
    """RT-B2 foundational: _is_speaking becomes True on/before the first
    captured frame of a generation, and resets to False both on normal
    completion and on mid-loop cancellation (the finally-block covers both
    uniformly, rather than duplicating the reset at each exit point)."""
    from agent.interview.voice_adapter import VoiceInterviewAdapter

    class FakeChunk:
        def __init__(self, frame):
            self.frame = frame

    class FakeAudioSource:
        def __init__(self, captured_states):
            self.captured_states = captured_states

        async def capture_frame(self, frame):
            self.captured_states.append(frame)

    async def scenario_completes_normally():
        adapter = object.__new__(VoiceInterviewAdapter)
        adapter._is_interrupted = False
        adapter._generation_id = 1
        adapter._is_speaking = False
        states_during_capture = []

        class FakeTTS:
            def synthesize(self, text, conn_options=None):
                async def gen():
                    states_during_capture.append(adapter._is_speaking)
                    yield FakeChunk("frame1")
                    states_during_capture.append(adapter._is_speaking)
                    yield FakeChunk("frame2")
                return gen()

        adapter.tts_plugin = FakeTTS()
        adapter._audio_source = FakeAudioSource([])

        assert adapter._is_speaking is False
        await adapter._synthesize_and_play("hello", gen_id=1)

        # False before the first frame's capture_frame() call, True by the
        # second (proving it flips on/before the first capture, not after).
        assert states_during_capture == [False, True]
        assert adapter._is_speaking is False  # reset on normal completion

    async def scenario_cancelled_mid_loop():
        adapter = object.__new__(VoiceInterviewAdapter)
        adapter._is_interrupted = False
        adapter._generation_id = 1
        adapter._is_speaking = False
        adapter._audio_source = FakeAudioSource([])

        class FakeTTS:
            def synthesize(self, text, conn_options=None):
                async def gen():
                    yield FakeChunk("frame1")
                    # Simulate an interruption landing mid-stream: bump the
                    # generation so the loop's own staleness check fires.
                    adapter._generation_id = 2
                    yield FakeChunk("frame2")
                return gen()

        adapter.tts_plugin = FakeTTS()

        with pytest.raises(asyncio.CancelledError):
            await adapter._synthesize_and_play("hello", gen_id=1)

        assert adapter._is_speaking is False  # reset even on cancellation

    asyncio.run(scenario_completes_normally())
    asyncio.run(scenario_cancelled_mid_loop())


class _FakeRtb2Context:
    def __init__(self):
        self.conversation_history = []
        self.current_phase = InterviewPhase.BACKGROUND
        self.message_sequence = 1  # non-zero: avoids the is_greeting metadata branch


class _FakeRtb2Controller:
    """Minimal stand-in for InterviewController -- only what
    _handle_candidate_turn() actually touches."""
    def __init__(self, response_text="A response.", on_process=None):
        self.context = _FakeRtb2Context()
        self._response_text = response_text
        self._on_process = on_process

    async def process_candidate_input(self, transcript):
        from agent.interview.models import StructuredAction, ActionEnum
        if self._on_process:
            self._on_process()
        return StructuredAction(action=ActionEnum.ASK, response=self._response_text, reason="test")


def _make_rtb2_adapter(controller, generation_id=5):
    from agent.interview.voice_adapter import VoiceInterviewAdapter

    adapter = object.__new__(VoiceInterviewAdapter)
    adapter.controller = controller
    adapter.persistence = None
    adapter._is_interrupted = False
    adapter._generation_id = generation_id
    adapter._is_speaking = False
    adapter._last_interruption_was_mid_playback = False
    adapter._tts_queue = asyncio.Queue()
    adapter._current_synthesis_task = None
    adapter._processed_candidate_turns = set()
    adapter._turn_lock = asyncio.Lock()
    adapter._audio_source = None
    adapter._emit_transcription = AsyncMock()
    adapter._emit_ui_state = AsyncMock()
    adapter._persist_message = AsyncMock()
    adapter._persist_action_event = AsyncMock()
    adapter._speak_text = AsyncMock()
    return adapter


def test_rtb2_mid_playback_interruption_behavior_unchanged_from_rtb1():
    """RT-B2 must not touch the mid-playback case at all: an interruption
    that lands while _is_speaking is True still discards the response
    outright (never reaches _speak_text), and clear_queue() still fires."""
    async def scenario():
        def interrupt_mid_generation():
            adapter._is_speaking = True  # the response currently playing IS audible
            adapter._handle_interruption()

        controller = _FakeRtb2Controller(on_process=interrupt_mid_generation)
        adapter = _make_rtb2_adapter(controller)

        class FakeAudioSource:
            def __init__(self):
                self.clear_queue_calls = 0

            def clear_queue(self):
                self.clear_queue_calls += 1

        adapter._audio_source = FakeAudioSource()

        await adapter._handle_candidate_turn("hello", turn_id=1)

        assert adapter._last_interruption_was_mid_playback is True
        adapter._speak_text.assert_not_called()
        assert adapter._audio_source.clear_queue_calls == 1

    asyncio.run(scenario())


def test_rtb2_stale_deferred_response_discarded_at_recheck():
    """A response invalidated while NOT mid-playback is provisionally
    preserved -- but a SECOND interruption landing before the final
    re-check (simulated here during _persist_action_event's await) must
    still discard it. Proves the re-check is real, not a rubber stamp."""
    async def scenario():
        def interrupt_not_mid_generation():
            adapter._is_speaking = False  # nothing audible yet
            adapter._handle_interruption()

        controller = _FakeRtb2Controller(on_process=interrupt_not_mid_generation)
        adapter = _make_rtb2_adapter(controller)

        async def second_interruption_during_persistence(*args, **kwargs):
            adapter._is_speaking = False
            adapter._handle_interruption()  # a further interruption, after the provisional decision

        adapter._persist_action_event = second_interruption_during_persistence

        await adapter._handle_candidate_turn("hello", turn_id=1)

        assert adapter._last_interruption_was_mid_playback is False
        adapter._speak_text.assert_not_called()  # discarded at the re-check, never spoken

    asyncio.run(scenario())


def test_rtb2_still_valid_deferred_response_is_spoken():
    """A response invalidated while NOT mid-playback, with nothing else
    changing before the re-check, must actually be spoken -- this is the
    entire point of provisional preservation, not just "doesn't crash"."""
    async def scenario():
        def interrupt_not_mid_generation():
            adapter._is_speaking = False
            adapter._handle_interruption()

        controller = _FakeRtb2Controller(
            response_text="Still relevant.", on_process=interrupt_not_mid_generation,
        )
        adapter = _make_rtb2_adapter(controller)
        # _persist_action_event stays the default no-op AsyncMock -- nothing
        # else changes generation/interrupted state before the re-check.

        await adapter._handle_candidate_turn("hello", turn_id=1)

        assert adapter._last_interruption_was_mid_playback is False
        adapter._speak_text.assert_awaited_once_with("Still relevant.")

    asyncio.run(scenario())


# ─── WR-C: waiting-room auto-timeout scheduling (voice_adapter.py) ─────────
# Mirrors _schedule_candidate_endpoint()'s own cancel-and-reschedule shape.
# Unlike _make_rtb2_adapter above, _emit_ui_state itself is NOT mocked out
# here — it's exactly what's under test — only the room's publish_data call
# underneath it is faked out.

class _FakeWaitingRoomController:
    """Minimal stand-in exposing only what _emit_ui_state()/
    _fire_waiting_room_timeout() actually touch. _transition_out_of_
    waiting_room actually flips current_phase to BACKGROUND, same as the
    real one — a bare AsyncMock() that leaves it at WAITING_ROOM would
    make _emit_ui_state()'s own real edge-detection logic (also under
    test here, not mocked) see it as still-freshly-entering and
    reschedule again inside the same call, double-firing in a way the
    real controller's actual phase change would never allow."""
    def __init__(self, phase):
        self.context = MagicMock()
        self.context.current_phase = phase
        self._transition_out_of_waiting_room = AsyncMock(side_effect=self._simulate_transition)

    async def _simulate_transition(self, auto):
        self.context.current_phase = InterviewPhase.BACKGROUND

    def generate_ui_state(self):
        return {"phase": self.context.current_phase.value, "sub_phase": None}


def _make_waiting_room_adapter(controller, timeout_seconds=0.02):
    from agent.interview.voice_adapter import VoiceInterviewAdapter

    adapter = object.__new__(VoiceInterviewAdapter)
    adapter.controller = controller
    adapter.room = MagicMock()
    adapter.room.local_participant.publish_data = AsyncMock()
    adapter._turn_lock = asyncio.Lock()
    adapter._waiting_room_timeout_seconds = timeout_seconds
    adapter._waiting_room_timeout_task = None
    adapter._last_emitted_phase = None
    return adapter


def test_schedule_waiting_room_timeout_cancels_a_pending_one_before_rescheduling():
    """Same reschedule discipline as _schedule_candidate_endpoint(): calling
    it again while one is still pending cancels the old task, not letting
    two race."""
    async def scenario():
        controller = _FakeWaitingRoomController(InterviewPhase.WAITING_ROOM)
        adapter = _make_waiting_room_adapter(controller, timeout_seconds=10)

        adapter._schedule_waiting_room_timeout()
        first_task = adapter._waiting_room_timeout_task
        adapter._schedule_waiting_room_timeout()
        second_task = adapter._waiting_room_timeout_task

        assert first_task is not second_task
        assert first_task.cancelled() or first_task.cancelling() > 0

        adapter._cancel_waiting_room_timeout()

    asyncio.run(scenario())


def test_waiting_room_timeout_fires_and_transitions_when_still_waiting():
    async def scenario():
        controller = _FakeWaitingRoomController(InterviewPhase.WAITING_ROOM)
        adapter = _make_waiting_room_adapter(controller, timeout_seconds=0.01)

        adapter._schedule_waiting_room_timeout()
        await asyncio.sleep(0.05)

        controller._transition_out_of_waiting_room.assert_awaited_once_with(auto=True)
        adapter.room.local_participant.publish_data.assert_awaited()  # _emit_ui_state ran for real

    asyncio.run(scenario())


def test_waiting_room_timeout_is_a_noop_if_phase_already_changed_before_it_fires():
    """Defensive re-check inside the lock: if the candidate proceeded
    (phase no longer WAITING_ROOM) right before the timeout fires, it must
    not double-transition even if cancellation somehow didn't land first."""
    async def scenario():
        controller = _FakeWaitingRoomController(InterviewPhase.WAITING_ROOM)
        adapter = _make_waiting_room_adapter(controller, timeout_seconds=0.01)

        adapter._schedule_waiting_room_timeout()
        controller.context.current_phase = InterviewPhase.BACKGROUND  # candidate proceeded first
        await asyncio.sleep(0.05)

        controller._transition_out_of_waiting_room.assert_not_awaited()

    asyncio.run(scenario())


def test_cancel_waiting_room_timeout_prevents_it_from_ever_firing():
    async def scenario():
        controller = _FakeWaitingRoomController(InterviewPhase.WAITING_ROOM)
        adapter = _make_waiting_room_adapter(controller, timeout_seconds=0.01)

        adapter._schedule_waiting_room_timeout()
        adapter._cancel_waiting_room_timeout()
        await asyncio.sleep(0.05)

        controller._transition_out_of_waiting_room.assert_not_awaited()

    asyncio.run(scenario())


def test_emit_ui_state_schedules_timeout_only_on_the_edge_into_waiting_room():
    """The bug this fix's own live verification is designed to catch: a
    naive "schedule whenever phase == WAITING_ROOM" would reset the
    countdown on every redundant re-emit (stray UI commands, incidental
    candidate speech) while still genuinely waiting, and could make the
    timeout effectively never fire. Must schedule exactly once across
    repeated emits of the same phase."""
    async def scenario():
        controller = _FakeWaitingRoomController(InterviewPhase.WAITING_ROOM)
        adapter = _make_waiting_room_adapter(controller, timeout_seconds=10)
        adapter._schedule_waiting_room_timeout = MagicMock(wraps=adapter._schedule_waiting_room_timeout)

        await adapter._emit_ui_state()
        await adapter._emit_ui_state()
        await adapter._emit_ui_state()

        assert adapter._schedule_waiting_room_timeout.call_count == 1
        adapter._cancel_waiting_room_timeout()

    asyncio.run(scenario())


def test_emit_ui_state_cancels_timeout_on_the_edge_out_of_waiting_room():
    async def scenario():
        controller = _FakeWaitingRoomController(InterviewPhase.WAITING_ROOM)
        adapter = _make_waiting_room_adapter(controller, timeout_seconds=10)

        await adapter._emit_ui_state()
        pending_task = adapter._waiting_room_timeout_task
        assert pending_task is not None and not pending_task.done()

        controller.context.current_phase = InterviewPhase.BACKGROUND
        await adapter._emit_ui_state()
        await asyncio.sleep(0)  # let the cancellation propagate

        assert pending_task.cancelled() or pending_task.cancelling() > 0

    asyncio.run(scenario())


def test_emit_ui_state_resuming_directly_into_waiting_room_schedules_a_fresh_timeout():
    """Item 5's approved answer: a fresh adapter's _last_emitted_phase
    starts as None, so resuming straight into a persisted WAITING_ROOM
    phase schedules a full-duration timeout on the very first emit — no
    separate resume-specific code path needed."""
    async def scenario():
        controller = _FakeWaitingRoomController(InterviewPhase.WAITING_ROOM)
        adapter = _make_waiting_room_adapter(controller, timeout_seconds=10)
        assert adapter._last_emitted_phase is None

        await adapter._emit_ui_state()

        assert adapter._waiting_room_timeout_task is not None
        assert not adapter._waiting_room_timeout_task.done()
        adapter._cancel_waiting_room_timeout()

    asyncio.run(scenario())


def test_submitting_one_technical_question_transitions_directly_to_closing():
    async def scenario():
        controller = make_controller(InterviewPhase.CODING)
        controller.context.current_question = QUESTION_BANK[0]
        controller.context.technical_question_ids_seen = [QUESTION_BANK[0].id]

        action = await controller.process_ui_command(
            "SUBMIT_CODE", {"payload": {"code": "return value", "language": "python"}}
        )

        assert action is not None
        assert controller.context.current_phase == InterviewPhase.CLOSING
        assert controller.context.current_question is None
        assert controller.context.technical_question_id_submitted == QUESTION_BANK[0].id
        assert controller.context.technical_submission["code"] == "return value"
        assert len(controller.context.question_records) == 1
        assert controller.context.question_records[0].outcome.value == "COMPLETED"

    asyncio.run(scenario())


def test_end_during_existing_closing_turn_does_not_create_second_message():
    controller = make_controller(InterviewPhase.CLOSING)

    action = asyncio.run(controller.process_ui_command("END_INTERVIEW"))

    assert action is not None
    assert action.response == ""
    assert controller.context.current_phase == InterviewPhase.COMPLETED
    assert not any(message.content for message in controller.context.conversation_history)


def test_technical_questions_are_unique_and_exhaustion_does_not_repeat():
    async def scenario():
        controller = make_controller(InterviewPhase.TECHNICAL)
        controller.context.current_question = None

        selected = []
        for _ in range(3):
            question = controller._load_next_technical_question()
            assert question is not None
            selected.append(question.id)
            controller._record_question_skip()

        assert selected == ["q1", "q2", "q3"]
        assert len(set(selected)) == 3
        assert controller._load_next_technical_question() is None

    asyncio.run(scenario())


def test_followup_cap_is_deterministically_enforced_in_background():
    """Phase 7C: the follow-up cap is now a hard, deterministically enforced
    limit rather than advisory-only prompt text — an intentional, accepted
    change to legacy BACKGROUND/TECHNICAL/CODING behavior (see the 7C
    completion report). Drives a mock LLM that always returns FOLLOW_UP
    through more than max_followups_per_question consecutive turns and
    confirms the (N+1)th is downgraded to ACKNOWLEDGE."""
    from agent.interview.models import StructuredAction, ActionEnum

    class AlwaysFollowUpLLM:
        async def generate_structured(self, system_prompt, messages, response_model):
            return StructuredAction(
                action=ActionEnum.FOLLOW_UP,
                response="Can you elaborate on that a bit more?",
                reason="Probing for additional detail.",
            )

    async def scenario():
        context = make_controller(InterviewPhase.BACKGROUND).context
        context.background_progress.limits.max_followups_per_question = 2
        controller = InterviewController(AlwaysFollowUpLLM(), MockPersistence(), context)

        actions = []
        for _ in range(3):
            action = await controller.process_candidate_input()
            actions.append(action.action)

        # First 2 (== max) are allowed through as FOLLOW_UP; the 3rd (N+1th)
        # is deterministically downgraded to ACKNOWLEDGE.
        assert actions == [ActionEnum.FOLLOW_UP, ActionEnum.FOLLOW_UP, ActionEnum.ACKNOWLEDGE]
        assert controller.context.followups_used == 2  # capped, not incremented past the limit

    asyncio.run(scenario())


def test_b2b_core_question_walk_advances_then_transitions_to_closing():
    """Phase 7D: an ordered, HR-approved core-question Verbal section stays
    in BACKGROUND between questions (no phase change — BACKGROUND->BACKGROUND
    is not a modeled state_machine transition) and only transitions to
    CLOSING once the list is exhausted, skipping TECHNICAL_INTRO/TECHNICAL/
    CODING entirely for B2B sessions. Also covers a null-competency question
    (q2) not crashing the CORE_QUESTION_PROMPT formatting.

    Drives ASK then TRANSITION per question (realistic turn order) rather
    than TRANSITION-only — the 7F-scoping addendum
    (test_adversarial_first_turn_transition_cannot_silently_skip_core_question)
    now blocks a bare TRANSITION before the question has been asked, so a
    TRANSITION-only mock no longer advances after one call the way it used
    to before that fix."""
    from agent.interview.models import StructuredAction, ActionEnum, OrderedSectionProgress

    class AskThenTransitionLLM:
        def __init__(self):
            self.calls = 0

        async def generate_structured(self, system_prompt, messages, response_model):
            self.calls += 1
            if self.calls % 2 == 1:
                return StructuredAction(
                    action=ActionEnum.ASK, response="Here's the question.",
                    reason="Posing the core question.",
                )
            return StructuredAction(
                action=ActionEnum.TRANSITION,
                response="Thanks, let's move on.",
                reason="Answer was sufficient.",
                should_transition=True,
            )

    async def scenario():
        context = make_controller(InterviewPhase.BACKGROUND).context
        q1 = Question(
            id="iq-1", title="Q1", problem_statement="Tell me about a challenging bug you fixed.",
            difficulty="mid", competency="debugging",
            expected_concepts=[], hints=[], follow_up_topics=[], time_budget_minutes=0,
            coding_required=False, source="HR_APPROVED",
        )
        q2 = Question(
            id="iq-2", title="Q2", problem_statement="Explain REST API design principles.",
            difficulty="mid", competency=None,
            expected_concepts=[], hints=[], follow_up_topics=[], time_budget_minutes=0,
            coding_required=False, source="HR_APPROVED",
        )
        context.sections["VERBAL"] = OrderedSectionProgress(section_type="VERBAL", questions=[q1, q2])
        controller = InterviewController(AskThenTransitionLLM(), MockPersistence(), context)

        await controller.process_candidate_input()  # ASK iq-1
        assert context.sections["VERBAL"].current_question_asked is True
        await controller.process_candidate_input()  # TRANSITION -> iq-2
        assert controller.context.current_phase == InterviewPhase.BACKGROUND
        assert context.sections["VERBAL"].current_index == 1
        assert context.sections["VERBAL"].current_question.id == "iq-2"

        await controller.process_candidate_input()  # ASK iq-2
        await controller.process_candidate_input()  # TRANSITION -> CLOSING
        assert controller.context.current_phase == InterviewPhase.CLOSING
        assert context.sections["VERBAL"].completed is True

        assert [r.question_id for r in controller.context.question_records] == ["iq-1", "iq-2"]
        assert all(r.outcome.value == "COMPLETED" for r in controller.context.question_records)

    asyncio.run(scenario())


def test_build_core_sections_is_empty_for_legacy_load_payload():
    """Phase 7E: main.py's build_core_sections() — the actual translation
    code entrypoint() runs — must produce {} for a legacy /load payload
    (no "sections" key, or an empty list), never crash or invent a section."""
    from agent.main import build_core_sections

    assert build_core_sections({"role": "Backend Engineer", "level": "mid"}) == {}
    assert build_core_sections({"sections": []}) == {}


def test_build_core_sections_maps_b2b_load_payload_correctly():
    """Phase 7E: a realistic /load payload (matching 7D's SectionPayload/
    QuestionPayload shape) maps into an ordered OrderedSectionProgress,
    including the null-competency passthrough and level-inherited difficulty."""
    from agent.main import build_core_sections

    session_data = {
        "level": "senior",
        "sections": [
            {
                "section_type": "VERBAL",
                "questions": [
                    # Deliberately out of order — must be sorted by order_index.
                    {"id": "iq-2", "order_index": 1, "title": "Q2", "competency": None, "text": "Explain REST."},
                    {"id": "iq-1", "order_index": 0, "title": "Q1", "competency": "debugging", "text": "Tell me about a bug."},
                ],
            }
        ],
    }

    built = build_core_sections(session_data)

    assert list(built.keys()) == ["VERBAL"]
    section = built["VERBAL"]
    assert section.section_type == "VERBAL"
    assert [q.id for q in section.questions] == ["iq-1", "iq-2"]  # re-ordered by order_index
    assert section.questions[0].competency == "debugging"
    assert section.questions[1].competency is None
    assert section.questions[0].difficulty == "senior"  # inherited from session_data["level"]
    assert section.questions[0].source == "HR_APPROVED"
    assert section.current_index == 0
    assert section.current_question is section.questions[0]


def test_build_core_sections_maps_time_budget_minutes():
    """WR-A (docs/section-pacing-architecture.md): a /load payload carrying
    the new time_budget_minutes field on a section maps it onto
    OrderedSectionProgress unchanged. Not consumed by anything yet
    (_start_section_clock() has no call site until WR-C) — this only
    proves the carry-through is correct."""
    from agent.main import build_core_sections

    session_data = {
        "level": "mid",
        "sections": [
            {
                "section_type": "VERBAL",
                "time_budget_minutes": 12,
                "questions": [
                    {"id": "iq-1", "order_index": 0, "title": "Q1", "competency": "debugging", "text": "Tell me about a bug."},
                ],
            }
        ],
    }

    built = build_core_sections(session_data)

    assert built["VERBAL"].time_budget_minutes == 12


def test_build_core_sections_defaults_time_budget_minutes_to_none_when_absent():
    """Backward-compat: an older /load payload (pre-WR-A) or a legacy
    session's section data has no time_budget_minutes key at all — must not
    crash, defaults to None (the OrderedSectionProgress field default)."""
    from agent.main import build_core_sections

    session_data = {
        "level": "mid",
        "sections": [
            {
                "section_type": "VERBAL",
                "questions": [
                    {"id": "iq-1", "order_index": 0, "title": "Q1", "competency": "debugging", "text": "Tell me about a bug."},
                ],
            }
        ],
    }

    built = build_core_sections(session_data)

    assert built["VERBAL"].time_budget_minutes is None


def test_start_section_clock_reseeds_remaining_time_and_tier():
    """WR-A's actual mechanism, exercised directly (no call site exists
    yet — that's WR-C's job): _start_section_clock() reseeds the timer to
    the given section's own budget, and get_remaining_time()/_time_tier()
    — unchanged formulas — then correctly operate against it, proving the
    reseed-not-dual-clock design is sound before anything calls it live."""
    from agent.interview.models import OrderedSectionProgress

    controller = make_controller(InterviewPhase.BACKGROUND)
    # Simulate having been mid-interview already, with very little of the
    # OLD (pre-reseed) clock left — proves the reseed genuinely replaces
    # the previous clock rather than just extending it.
    controller._total_duration_sec = 30
    controller._start_time = None

    short_section = OrderedSectionProgress(section_type="CODING", questions=[], time_budget_minutes=20)
    controller._start_section_clock(short_section)

    assert controller._total_duration_sec == 20 * 60
    assert controller._start_time is None
    assert controller.get_remaining_time() == 20 * 60
    assert controller._time_tier() == "normal"  # 1200s >= normal_min_seconds (300)


def test_start_section_clock_is_a_noop_when_section_has_no_budget():
    """Defensive fallback: must not zero out the clock for a
    malformed/legacy section that reaches this method without a budget —
    should not happen for a published B2B session (publish_job requires
    it), but this is a safety net, not a trust assumption."""
    from agent.interview.models import OrderedSectionProgress

    controller = make_controller(InterviewPhase.BACKGROUND)
    controller._total_duration_sec = 777
    controller._start_time = None

    unbudgeted_section = OrderedSectionProgress(section_type="VERBAL", questions=[], time_budget_minutes=None)
    controller._start_section_clock(unbudgeted_section)

    assert controller._total_duration_sec == 777


def test_adversarial_first_turn_transition_cannot_silently_skip_core_question():
    """7F-scoping addendum: a mock LLM that emits TRANSITION on the very
    first turn of a core question — before ever using ASK to pose it — must
    not be allowed to record that question as COMPLETED and advance past
    it. This was a confirmed, real gap: _should_allow_transition() used to
    return True unconditionally for the core-question flow, trusting the
    LLM's judgment with no check that the question was ever actually asked."""
    from agent.interview.models import StructuredAction, ActionEnum, OrderedSectionProgress

    class AlwaysTransitionLLM:
        async def generate_structured(self, system_prompt, messages, response_model):
            return StructuredAction(
                action=ActionEnum.TRANSITION,
                response="Moving on.",  # deliberately NOT the question text
                reason="(adversarial) skipping without asking",
                should_transition=True,
            )

    async def scenario():
        context = make_controller(InterviewPhase.BACKGROUND).context
        q1 = Question(
            id="iq-1", title="Q1", problem_statement="Tell me about a challenging bug you fixed.",
            difficulty="mid", competency="debugging",
            expected_concepts=[], hints=[], follow_up_topics=[], time_budget_minutes=0,
            coding_required=False, source="HR_APPROVED",
        )
        context.sections["VERBAL"] = OrderedSectionProgress(section_type="VERBAL", questions=[q1])
        controller = InterviewController(AlwaysTransitionLLM(), MockPersistence(), context)

        action = await controller.process_candidate_input()

        # The adversarial TRANSITION must be corrected into an ASK, and the
        # actual question text must be what gets said -- not the LLM's
        # rejected "Moving on." response.
        assert action.action == ActionEnum.ASK
        assert action.response == "Tell me about a challenging bug you fixed."
        assert controller.context.current_phase == InterviewPhase.BACKGROUND
        assert context.sections["VERBAL"].current_index == 0  # did not advance
        assert context.sections["VERBAL"].current_question.id == "iq-1"  # still the same question
        assert context.sections["VERBAL"].current_question_asked is True  # corrected turn counts as asked
        assert controller.context.question_records == []  # nothing recorded as completed

        # A second adversarial attempt, now that the question HAS been
        # asked, must be allowed through normally.
        action2 = await controller.process_candidate_input()
        assert action2.action == ActionEnum.TRANSITION
        assert controller.context.current_phase == InterviewPhase.CLOSING
        assert [r.question_id for r in controller.context.question_records] == ["iq-1"]
        assert controller.context.question_records[0].outcome.value == "COMPLETED"

    asyncio.run(scenario())


def test_final_evaluation_uses_transcript_and_is_persisted():
    from agent.interview.models import DetailedEvaluation, Message

    class EvaluationLLM:
        def __init__(self):
            self.received = None

        async def generate_structured(self, system_prompt, messages, response_model):
            self.received = messages
            return DetailedEvaluation(
                overall_score=4,
                recommendation="Hire",
                summary="Evidence-based summary.",
            )

    async def scenario():
        persistence = MockPersistence()
        llm = EvaluationLLM()
        context = make_controller(InterviewPhase.COMPLETED).context
        context.conversation_history.append(Message(role="user", content="I would use a hash map."))
        controller = InterviewController(llm, persistence, context)

        evaluation = await controller.generate_final_evaluation()
        await persistence.save_completion(context)

        assert evaluation is not None
        assert "I would use a hash map." in llm.received[0]["content"]
        assert persistence.storage[context.session_id]["final_result"]["evaluation"]["recommendation"] == "Hire"

    asyncio.run(scenario())


# ─── Phase 7F — Integration verification ────────────────────────────────────

def test_7f_full_ordered_three_question_walk_with_evaluation_persistence():
    """7F: a real HR-approved 3-question Verbal section, driven through a
    realistic ASK -> FOLLOW_UP* -> TRANSITION turn sequence per question,
    ending in CLOSING -> COMPLETED with a persisted final evaluation.
    Proves, together, in the NEW ordered-core-question flow specifically
    (not just the legacy counters 7C's own test covered):
      - question order enforcement (never skipped/reordered — q1, q2, q3)
      - the follow-up cap is enforced for the new flow's flat max-2 (q2
        attempts a 3rd follow-up; it must be downgraded, not honored)
      - the null-competency rule forces 0 follow-ups (q3 attempts one; it
        must be downgraded too)
      - correct final transcript/evaluation persistence for a completed
        core-question walk
    """
    from agent.interview.models import (
        StructuredAction, ActionEnum, OrderedSectionProgress, DetailedEvaluation,
    )

    class ScriptedLLM:
        def __init__(self, script):
            self.script = list(script)

        async def generate_structured(self, system_prompt, messages, response_model):
            if response_model is DetailedEvaluation:
                return DetailedEvaluation(
                    overall_score=4, recommendation="Hire",
                    summary="Strong performance across all three core questions.",
                )
            return self.script.pop(0)

    def ask(text="Here's the question."):
        return StructuredAction(action=ActionEnum.ASK, response=text, reason="Posing the core question.")

    def follow_up():
        return StructuredAction(action=ActionEnum.FOLLOW_UP, response="Can you elaborate?", reason="Probing further.")

    def transition():
        return StructuredAction(
            action=ActionEnum.TRANSITION, response="Thanks, let's move on.",
            reason="Answer was sufficient.", should_transition=True,
        )

    def end():
        return StructuredAction(action=ActionEnum.END, response="Thanks for your time today!", reason="Wrapping up.")

    script = [
        ask(), follow_up(), transition(),                       # q1: 1 follow-up, under cap of 2
        ask(), follow_up(), follow_up(), follow_up(), transition(),  # q2: attempts 3 follow-ups, cap is 2
        ask(), follow_up(), transition(),                       # q3: attempts 1 follow-up, null-competency cap is 0
        end(),                                                   # CLOSING -> COMPLETED
    ]

    async def scenario():
        context = make_controller(InterviewPhase.BACKGROUND).context
        q1 = Question(
            id="iq-1", title="Debugging", problem_statement="Tell me about a challenging bug you fixed.",
            difficulty="mid", competency="debugging",
            expected_concepts=[], hints=[], follow_up_topics=[], time_budget_minutes=0,
            coding_required=False, source="HR_APPROVED",
        )
        q2 = Question(
            id="iq-2", title="System Design", problem_statement="Design a rate limiter.",
            difficulty="mid", competency="system_design",
            expected_concepts=[], hints=[], follow_up_topics=[], time_budget_minutes=0,
            coding_required=False, source="HR_APPROVED",
        )
        q3 = Question(
            id="iq-3", title="REST", problem_statement="Explain REST API design principles.",
            difficulty="mid", competency=None,
            expected_concepts=[], hints=[], follow_up_topics=[], time_budget_minutes=0,
            coding_required=False, source="HR_APPROVED",
        )
        context.sections["VERBAL"] = OrderedSectionProgress(section_type="VERBAL", questions=[q1, q2, q3])
        llm = ScriptedLLM(script)
        persistence = MockPersistence()
        controller = InterviewController(llm, persistence, context)

        actions = []
        while controller.context.current_phase != InterviewPhase.COMPLETED:
            actions.append((await controller.process_candidate_input()).action)

        # Order enforcement: exactly q1, q2, q3, never skipped or reordered.
        assert [r.question_id for r in controller.context.question_records] == ["iq-1", "iq-2", "iq-3"]
        assert all(r.outcome.value == "COMPLETED" for r in controller.context.question_records)

        # Follow-up cap enforced in the NEW flow: q2's script tried 3
        # FOLLOW_UPs; only 2 should have landed as real FOLLOW_UP actions,
        # the 3rd must have been downgraded (to ACKNOWLEDGE) by the cap.
        assert controller.context.question_records[1].followups_used == 2

        # Null-competency rule: q3's script tried 1 FOLLOW_UP; it must have
        # been downgraded too (cap is 0 for a question with no competency).
        assert controller.context.question_records[2].followups_used == 0

        # The corrected (downgraded) turns must show up as ACKNOWLEDGE, not
        # FOLLOW_UP, in the actual observed action sequence.
        assert ActionEnum.ACKNOWLEDGE in actions

        assert controller.context.current_phase == InterviewPhase.COMPLETED

        # Final transcript/evaluation persistence.
        evaluation = await controller.generate_final_evaluation()
        await persistence.save_completion(context)
        assert evaluation is not None
        assert evaluation.recommendation == "Hire"
        final_result = persistence.storage[context.session_id]["final_result"]
        assert final_result["completed"] == 3
        assert final_result["evaluation"]["recommendation"] == "Hire"
        assert [qr["question_id"] for qr in final_result["question_records"]] == ["iq-1", "iq-2", "iq-3"]

    asyncio.run(scenario())


def test_7f_time_tier_thresholds_gate_the_new_flow_followup_budget():
    """7F: confirms the (provisional) TimeTierThresholds boundaries actually
    drive _current_max_followups() for the new ordered core-question flow,
    across all three bands. Interpreting "confirm against a real timed run"
    as deterministic time-value manipulation, not literal wall-clock
    waiting — matching how every other time-pressure behavior in this
    codebase has always been tested (nothing here uses sleep())."""
    from agent.interview.models import OrderedSectionProgress

    controller = make_controller(InterviewPhase.BACKGROUND)
    q1 = Question(
        id="iq-1", title="Q1", problem_statement="Tell me about a challenging bug you fixed.",
        difficulty="mid", competency="debugging",
        expected_concepts=[], hints=[], follow_up_topics=[], time_budget_minutes=0,
        coding_required=False, source="HR_APPROVED",
    )
    controller.context.sections["VERBAL"] = OrderedSectionProgress(section_type="VERBAL", questions=[q1])

    tiers = controller.context.interview_plan.time_tiers

    controller.context.time_remaining_seconds = tiers.normal_min_seconds
    controller._start_time = None  # get_remaining_time() falls back to _total_duration_sec when no timer started
    controller._total_duration_sec = tiers.normal_min_seconds
    assert controller._time_tier() == "normal"
    assert controller._current_max_followups() == 2

    controller._total_duration_sec = tiers.limited_min_seconds
    assert controller._time_tier() == "limited"
    assert controller._current_max_followups() == 1

    controller._total_duration_sec = tiers.limited_min_seconds - 1
    assert controller._time_tier() == "very_limited"
    assert controller._current_max_followups() == 0

    # Boundary just below "normal" must read as "limited", not "normal".
    controller._total_duration_sec = tiers.normal_min_seconds - 1
    assert controller._time_tier() == "limited"


# ─── Phase 9B — Integration verification (multi-section-type ordered walk) ──

def test_9b_multi_section_type_ordered_walk_enforces_per_type_followup_caps():
    """Phase 9B: mirrors 7F's full-walk pattern but across all three section
    types in one interview, in a deliberately NON-default admin-configured
    order (CODING, MCQ, VERBAL -- not creation/alphabetical order), proving:
      - _active_core_section() walks context.sections in insertion order
        regardless of type (generalizes 7F's VERBAL-only coverage; the
        DB/API-level equivalent of this ordering guarantee is covered by
        test_9b_reordered_multi_type_sections_walk_in_admin_configured_order
        in test_phase9b.py)
      - _current_max_followups() gives CODING and MCQ a hard 0-follow-up
        cap -- the bug this sub-phase fixed; CODING no longer silently
        inherits VERBAL's up-to-2 budget -- while VERBAL keeps its existing
        up-to-2 time-tiered budget completely unaffected (standing rule 4)

    Updated post-9E: CODING/MCQ no longer complete via a bare LLM
    TRANSITION at all (9E's _should_allow_transition() fix -- discovered
    during 9I prep when this test, still scripted to TRANSITION those two
    types, hung in an infinite loop: TRANSITION now downgrades to ASK
    forever once the script is exhausted, and process_candidate_input()'s
    broad except-Exception fallback silently swallows the resulting
    IndexError instead of surfacing it). CODING/MCQ now complete via
    SUBMIT_CODE/SUBMIT_MCQ_ANSWER (process_ui_command), matching the real
    production completion path; VERBAL is untouched and still completes
    via a scripted conversational TRANSITION."""
    from agent.interview.models import (
        StructuredAction, ActionEnum, OrderedSectionProgress, DetailedEvaluation,
    )

    class ScriptedLLM:
        def __init__(self, script):
            self.script = list(script)

        async def generate_structured(self, system_prompt, messages, response_model):
            if response_model is DetailedEvaluation:
                return DetailedEvaluation(
                    overall_score=4, recommendation="Hire",
                    summary="Strong performance across all three section types.",
                )
            return self.script.pop(0)

    def ask(text="Here's the question."):
        return StructuredAction(action=ActionEnum.ASK, response=text, reason="Posing the core question.")

    def follow_up():
        return StructuredAction(action=ActionEnum.FOLLOW_UP, response="Can you elaborate?", reason="Probing further.")

    def transition():
        return StructuredAction(
            action=ActionEnum.TRANSITION, response="Thanks, let's move on.",
            reason="Answer was sufficient.", should_transition=True,
        )

    def end():
        return StructuredAction(action=ActionEnum.END, response="Thanks for your time today!", reason="Wrapping up.")

    # Only ASK/FOLLOW_UP turns are LLM-driven now for CODING/MCQ -- their
    # completion (SUBMIT_CODE/SUBMIT_MCQ_ANSWER) never calls the LLM at all.
    script = [
        ask(), follow_up(),                 # CODING q: FOLLOW_UP attempt must be downgraded (cap 0)
        ask(), follow_up(),                 # MCQ q: FOLLOW_UP attempt must be downgraded (cap 0)
        ask(), follow_up(), transition(),   # VERBAL q: FOLLOW_UP allowed (cap 2, unaffected by the fix)
        end(),
    ]

    async def scenario():
        context = make_controller(InterviewPhase.BACKGROUND).context
        coding_q = Question(
            id="iq-coding-1", title="Two Sum", problem_statement="Find two numbers that sum to target.",
            difficulty="mid", competency="algorithms",
            expected_concepts=[], hints=[], follow_up_topics=[], time_budget_minutes=0,
            coding_required=True, source="HR_APPROVED",
        )
        mcq_q = Question(
            id="iq-mcq-1", title="Python Basics", problem_statement="Which best describes Python?",
            difficulty="mid", competency="fundamentals",
            expected_concepts=[], hints=[], follow_up_topics=[], time_budget_minutes=0,
            coding_required=False, source="HR_APPROVED",
            config={
                "options": [{"id": "A", "text": "A programming language"}, {"id": "B", "text": "A snake"}],
                "correct_answers": ["A"], "is_multi_select": False,
            },
        )
        verbal_q = Question(
            id="iq-verbal-1", title="Debugging", problem_statement="Tell me about a challenging bug you fixed.",
            difficulty="mid", competency="debugging",
            expected_concepts=[], hints=[], follow_up_topics=[], time_budget_minutes=0,
            coding_required=False, source="HR_APPROVED",
        )

        # Deliberately non-default admin-configured order: CODING, MCQ, VERBAL.
        context.sections["CODING"] = OrderedSectionProgress(section_type="CODING", questions=[coding_q])
        context.sections["MCQ"] = OrderedSectionProgress(section_type="MCQ", questions=[mcq_q])
        context.sections["VERBAL"] = OrderedSectionProgress(section_type="VERBAL", questions=[verbal_q])

        llm = ScriptedLLM(script)
        persistence = MockPersistence()
        controller = InterviewController(llm, persistence, context)

        actions = []

        # CODING: ASK, FOLLOW_UP-attempt (downgraded), then complete via the
        # real production mechanism -- SUBMIT_CODE -- never a bare TRANSITION.
        actions.append((await controller.process_candidate_input()).action)
        actions.append((await controller.process_candidate_input()).action)
        actions.append((await controller.process_ui_command(
            "SUBMIT_CODE", {"payload": {"code": "return sum", "language": "python"}}
        )).action)

        # WR-C: CODING's completion leaves MCQ+VERBAL remaining -- stops at
        # WAITING_ROOM rather than 9B's original invisible same-turn
        # continuation straight into MCQ. Proceed explicitly to reach it,
        # exactly as a real candidate/the auto-timeout would.
        assert controller.context.current_phase == InterviewPhase.WAITING_ROOM
        await controller._handle_candidate_control(CandidateControlAction.PROCEED_TO_NEXT_SECTION)
        assert controller._active_core_section() is controller.context.sections["MCQ"]

        # MCQ: ASK, FOLLOW_UP-attempt (downgraded), then complete via
        # SUBMIT_MCQ_ANSWER -- same reasoning as CODING above.
        actions.append((await controller.process_candidate_input()).action)
        actions.append((await controller.process_candidate_input()).action)
        actions.append((await controller.process_ui_command(
            "SUBMIT_MCQ_ANSWER", {"payload": {"selected_option_ids": ["A"]}}
        )).action)

        # WR-C: same boundary again -- VERBAL still remains after MCQ.
        assert controller.context.current_phase == InterviewPhase.WAITING_ROOM
        await controller._handle_candidate_control(CandidateControlAction.PROCEED_TO_NEXT_SECTION)
        assert controller._active_core_section() is controller.context.sections["VERBAL"]

        # VERBAL: unaffected by 9E -- still completes via a conversational
        # TRANSITION, exactly as 7F already proved. Drive the rest of the
        # scripted turns (including END) through the normal loop. VERBAL is
        # the LAST section, so exhausting it goes straight to CLOSING as
        # before -- no further waiting room.
        while controller.context.current_phase != InterviewPhase.COMPLETED:
            actions.append((await controller.process_candidate_input()).action)

        # Order enforcement across types: CODING, then MCQ, then VERBAL --
        # the admin-configured insertion order, not alphabetical/creation order.
        assert [r.question_id for r in controller.context.question_records] == [
            "iq-coding-1", "iq-mcq-1", "iq-verbal-1",
        ]
        assert all(r.outcome.value == "COMPLETED" for r in controller.context.question_records)

        # CODING and MCQ: the attempted FOLLOW_UP must have been downgraded --
        # 0 landed, not 1. This is the bug this sub-phase fixed for CODING.
        assert controller.context.question_records[0].followups_used == 0  # CODING
        assert controller.context.question_records[1].followups_used == 0  # MCQ

        # VERBAL is unaffected by the CODING/MCQ fix -- its follow-up landed
        # normally, exactly as 7F already proved.
        assert controller.context.question_records[2].followups_used == 1  # VERBAL

        assert ActionEnum.ACKNOWLEDGE in actions  # the two downgraded turns
        assert controller.context.current_phase == InterviewPhase.COMPLETED

        # Final transcript/evaluation persistence, unaffected across types.
        evaluation = await controller.generate_final_evaluation()
        await persistence.save_completion(context)
        assert evaluation is not None
        final_result = persistence.storage[context.session_id]["final_result"]
        assert [qr["question_id"] for qr in final_result["question_records"]] == [
            "iq-coding-1", "iq-mcq-1", "iq-verbal-1",
        ]

    asyncio.run(scenario())


# ─── Phase 9C — Candidate submission handling ───────────────────────────────

def test_9c_provide_hint_ported_to_ordered_coding_core_question():
    """9C: _provide_hint() previously only ever read self.context.current_question,
    which the ordered flow never populates -- an ordered CODING question's
    REQUEST_HINT would silently always report "no hints available" even
    with predefined hints on the question. Now prefers the active core
    section's current_question when one exists."""
    from agent.interview.models import ActionEnum

    async def scenario():
        controller = make_controller(InterviewPhase.BACKGROUND)
        coding_q = Question(
            id="iq-coding-hint", title="Two Sum", problem_statement="Find two numbers that sum to target.",
            difficulty="mid", competency="algorithms",
            expected_concepts=[], hints=["Consider a hash map of seen values.", "What's the complement?"],
            follow_up_topics=[], time_budget_minutes=0, coding_required=True, source="HR_APPROVED",
        )
        controller.context.sections["CODING"] = OrderedSectionProgress(section_type="CODING", questions=[coding_q])

        first = await controller.process_ui_command("REQUEST_HINT")
        assert first is not None
        assert first.action == ActionEnum.HINT
        assert first.response == "Consider a hash map of seen values."
        assert controller.context.hints_used == 1
        # The legacy field this used to (wrongly) read stays untouched --
        # proves the fix is reading the ordered core section, not this.
        assert controller.context.current_question is None

        second = await controller.process_ui_command("REQUEST_HINT")
        assert second.response == "What's the complement?"
        assert controller.context.hints_used == 2

        # A third request exceeds the 2 predefined hints -- graceful decline,
        # not a crash.
        third = await controller.process_ui_command("REQUEST_HINT")
        assert third.action == ActionEnum.ACKNOWLEDGE
        assert controller.context.hints_used == 2

    asyncio.run(scenario())


def test_9c_request_hint_on_verbal_or_mcq_core_question_gracefully_declines():
    """9C: REQUEST_HINT is now allowed in BACKGROUND generally (not gated by
    section_type), but VERBAL/MCQ questions never populate Question.hints,
    so _provide_hint()'s existing "no hints available" fallback handles
    them -- no crash, no false hint."""
    from agent.interview.models import ActionEnum

    async def scenario():
        controller = make_controller(InterviewPhase.BACKGROUND)
        mcq_q = Question(
            id="iq-mcq-hint", title="Q", problem_statement="Which best describes Python?",
            difficulty="mid", competency="fundamentals",
            expected_concepts=[], hints=[], follow_up_topics=[],
            time_budget_minutes=0, coding_required=False, source="HR_APPROVED",
        )
        controller.context.sections["MCQ"] = OrderedSectionProgress(section_type="MCQ", questions=[mcq_q])

        action = await controller.process_ui_command("REQUEST_HINT")

        assert action is not None
        assert action.action == ActionEnum.ACKNOWLEDGE
        assert controller.context.hints_used == 0

    asyncio.run(scenario())


def test_9c_build_core_sections_wires_coding_hints_from_config():
    """9C: config.hints (9A's schema addition) now actually reaches
    Question.hints -- previously build_core_sections() hardcoded hints=[]
    unconditionally, so 9A's schema field was dead on arrival at runtime."""
    from agent.main import build_core_sections

    session_data = {
        "level": "mid",
        "sections": [
            {
                "section_type": "CODING",
                "questions": [{
                    "id": "iq-coding", "order_index": 0, "title": "Two Sum",
                    "competency": "algorithms", "text": "Find two numbers that sum to target.",
                    "config": {
                        "starter_code": "def f(): pass",
                        "supported_languages": ["python"],
                        "constraints": "n <= 100",
                        "hints": ["Hint one.", "Hint two."],
                    },
                }],
            },
            {
                "section_type": "VERBAL",
                "questions": [{
                    "id": "iq-verbal", "order_index": 0, "title": "Q",
                    "competency": None, "text": "Tell me about yourself.",
                }],
            },
        ],
    }

    built = build_core_sections(session_data)

    assert built["CODING"].questions[0].hints == ["Hint one.", "Hint two."]
    # VERBAL's config never carries a "hints" key -- must stay [], not crash.
    assert built["VERBAL"].questions[0].hints == []


def test_9c_submit_code_advances_ordered_walk_not_straight_to_closing():
    """9C: the previous SUBMIT_CODE handler only ever accepted phase
    TECHNICAL/CODING (legacy flow) and unconditionally transitioned straight
    to CLOSING -- for the ordered flow, an active CODING core question runs
    under phase BACKGROUND, so the submission was silently dropped (returned
    None), and even if it hadn't been, jumping straight to CLOSING would
    have skipped a later MCQ section entirely.

    WR-C update: exhausting CODING with MCQ still remaining now stops at
    WAITING_ROOM rather than 9B's original invisible same-turn continuation
    into MCQ — that boundary is this feature's whole point (docs/section-
    pacing-architecture.md). MCQ becoming reachable (not skipped) is now
    proven by explicitly proceeding out of the waiting room, preserving
    this test's original intent."""
    async def scenario():
        controller = make_controller(InterviewPhase.BACKGROUND)
        coding_q = Question(
            id="iq-coding-submit", title="Two Sum", problem_statement="Find two numbers that sum to target.",
            difficulty="mid", competency="algorithms",
            expected_concepts=[], hints=[], follow_up_topics=[],
            time_budget_minutes=0, coding_required=True, source="HR_APPROVED",
        )
        mcq_q = Question(
            id="iq-mcq-after", title="Q", problem_statement="Which best describes Python?",
            difficulty="mid", competency="fundamentals",
            expected_concepts=[], hints=[], follow_up_topics=[],
            time_budget_minutes=0, coding_required=False, source="HR_APPROVED",
        )
        controller.context.sections["CODING"] = OrderedSectionProgress(
            section_type="CODING", questions=[coding_q], time_budget_minutes=20,
        )
        controller.context.sections["MCQ"] = OrderedSectionProgress(
            section_type="MCQ", questions=[mcq_q], time_budget_minutes=10,
        )

        action = await controller.process_ui_command(
            "SUBMIT_CODE", {"payload": {"code": "def two_sum(): pass", "language": "python"}}
        )

        assert action is not None
        assert controller.context.current_phase == InterviewPhase.WAITING_ROOM  # not CLOSING, not silently BACKGROUND/MCQ
        assert controller.context.technical_submission["code"] == "def two_sum(): pass"
        assert controller.context.sections["CODING"].completed is True
        assert controller.context.sections["MCQ"].completed is False
        assert [r.question_id for r in controller.context.question_records] == ["iq-coding-submit"]
        assert controller.context.question_records[0].outcome.value == "COMPLETED"

        # MCQ is reachable, not skipped — proceeding out of the waiting
        # room reaches it with a freshly reseeded clock.
        proceed_action = await controller._handle_candidate_control(CandidateControlAction.PROCEED_TO_NEXT_SECTION)
        assert proceed_action is not None
        assert controller.context.current_phase == InterviewPhase.BACKGROUND
        assert controller._active_core_section() is controller.context.sections["MCQ"]
        assert controller._total_duration_sec == 10 * 60

    asyncio.run(scenario())


def test_9c_submit_code_as_last_ordered_section_transitions_to_closing():
    """9C: once no core section remains after the submission, CLOSING is
    still reached -- exactly like TRANSITION exhausting the last VERBAL
    question in 7F/9B's tests."""
    async def scenario():
        controller = make_controller(InterviewPhase.BACKGROUND)
        coding_q = Question(
            id="iq-coding-only", title="Two Sum", problem_statement="Find two numbers that sum to target.",
            difficulty="mid", competency="algorithms",
            expected_concepts=[], hints=[], follow_up_topics=[],
            time_budget_minutes=0, coding_required=True, source="HR_APPROVED",
        )
        controller.context.sections["CODING"] = OrderedSectionProgress(section_type="CODING", questions=[coding_q])

        action = await controller.process_ui_command(
            "SUBMIT_CODE", {"payload": {"code": "x = 1", "language": "python"}}
        )

        assert action is not None
        assert controller.context.current_phase == InterviewPhase.CLOSING

    asyncio.run(scenario())


def _mcq_question(question_id: str, correct_answers, is_multi_select: bool = False) -> Question:
    return Question(
        id=question_id, title="Q", problem_statement="Which best describes Python?",
        difficulty="mid", competency="fundamentals",
        expected_concepts=[], hints=[], follow_up_topics=[],
        time_budget_minutes=0, coding_required=False, source="HR_APPROVED",
        config={
            "options": [
                {"id": "A", "text": "A programming language"},
                {"id": "B", "text": "A snake"},
                {"id": "C", "text": "An interpreted language"},
            ],
            "correct_answers": correct_answers,
            "is_multi_select": is_multi_select,
        },
    )


def test_9c_submit_mcq_answer_correct_grades_and_advances():
    """9C: MCQ answer submission via the new SUBMIT_MCQ_ANSWER data-channel
    command -- deterministic grading (no LLM call), recorded via
    EvaluationSignal (no new schema), and advances the ordered walk exactly
    like SUBMIT_CODE/TRANSITION do for the other two types."""
    async def scenario():
        controller = make_controller(InterviewPhase.BACKGROUND)
        controller.context.sections["MCQ"] = OrderedSectionProgress(
            section_type="MCQ", questions=[_mcq_question("iq-mcq-correct", ["A"])],
        )

        action = await controller.process_ui_command(
            "SUBMIT_MCQ_ANSWER", {"payload": {"selected_option_ids": ["A"]}}
        )

        assert action is not None
        assert controller.context.current_phase == InterviewPhase.CLOSING  # only section, now exhausted
        record = controller.context.question_records[0]
        assert record.question_id == "iq-mcq-correct"
        assert record.outcome.value == "COMPLETED"
        assert record.evaluation is not None
        assert "result=CORRECT." in record.evaluation.evidence
        assert "result=INCORRECT." not in record.evaluation.evidence

    asyncio.run(scenario())


def test_9c_submit_mcq_answer_incorrect_grades_correctly():
    async def scenario():
        controller = make_controller(InterviewPhase.BACKGROUND)
        controller.context.sections["MCQ"] = OrderedSectionProgress(
            section_type="MCQ", questions=[_mcq_question("iq-mcq-wrong", ["A"])],
        )

        await controller.process_ui_command("SUBMIT_MCQ_ANSWER", {"payload": {"selected_option_ids": ["B"]}})

        record = controller.context.question_records[0]
        assert "result=INCORRECT." in record.evaluation.evidence

    asyncio.run(scenario())


def test_9c_submit_mcq_answer_multi_select_is_order_independent():
    async def scenario():
        controller = make_controller(InterviewPhase.BACKGROUND)
        controller.context.sections["MCQ"] = OrderedSectionProgress(
            section_type="MCQ",
            questions=[_mcq_question("iq-mcq-multi", ["A", "C"], is_multi_select=True)],
        )

        # Submitted in the opposite order from correct_answers -- must still grade correct.
        await controller.process_ui_command(
            "SUBMIT_MCQ_ANSWER", {"payload": {"selected_option_ids": ["C", "A"]}}
        )

        record = controller.context.question_records[0]
        assert "result=CORRECT." in record.evaluation.evidence

    asyncio.run(scenario())


def test_9c_submit_mcq_answer_rejected_when_active_section_is_not_mcq():
    """9C: SUBMIT_MCQ_ANSWER must not silently grade/advance a non-MCQ
    active core section (e.g. a stray/buggy client message during a VERBAL
    question)."""
    async def scenario():
        controller = make_controller(InterviewPhase.BACKGROUND)
        verbal_q = Question(
            id="iq-verbal-guard", title="Q", problem_statement="Tell me about yourself.",
            difficulty="mid", competency=None,
            expected_concepts=[], hints=[], follow_up_topics=[],
            time_budget_minutes=0, coding_required=False, source="HR_APPROVED",
        )
        controller.context.sections["VERBAL"] = OrderedSectionProgress(section_type="VERBAL", questions=[verbal_q])

        action = await controller.process_ui_command(
            "SUBMIT_MCQ_ANSWER", {"payload": {"selected_option_ids": ["A"]}}
        )

        assert action is None
        assert controller.context.sections["VERBAL"].current_index == 0  # untouched
        assert controller.context.question_records == []

    asyncio.run(scenario())


# ─── Phase 9D — Evaluation logic per type ───────────────────────────────────

def test_9d_eval_criteria_reaches_final_evaluation_evidence_per_type():
    """9D: HR-authored eval_criteria (9A's schema field) previously never
    reached the agent runtime at all -- build_core_sections() dropped it
    when constructing each Question, and generate_final_evaluation()'s
    evidence dict never included it either. Now wired end-to-end, keeping
    each section type's own native rubric shape (Option C: VERBAL's
    excellent/good/adequate/poor bands, CODING's time_complexity/
    space_complexity/edge_cases/rubric, MCQ's explanation-only) rather than
    reshaping one type's rubric into another's."""
    import json
    from agent.interview.models import DetailedEvaluation

    class CapturingLLM:
        def __init__(self):
            self.received = None

        async def generate_structured(self, system_prompt, messages, response_model):
            self.received = messages
            return DetailedEvaluation(overall_score=4, recommendation="Hire", summary="Solid overall performance.")

    async def scenario():
        context = make_controller(InterviewPhase.COMPLETED).context
        verbal_q = Question(
            id="iq-verbal-ec", title="Q", problem_statement="Tell me about a challenging bug you fixed.",
            difficulty="mid", competency="debugging",
            expected_concepts=[], hints=[], follow_up_topics=[],
            time_budget_minutes=0, coding_required=False, source="HR_APPROVED",
            eval_criteria={
                "excellent": "Specific bug, clear root-cause reasoning, concrete fix.",
                "good": "Plausible bug and fix, some detail missing.",
                "adequate": "Generic answer, little specific detail.",
                "poor": "No coherent example.",
            },
        )
        coding_q = Question(
            id="iq-coding-ec", title="Two Sum", problem_statement="Find two numbers that sum to target.",
            difficulty="mid", competency="algorithms",
            expected_concepts=[], hints=[], follow_up_topics=[],
            time_budget_minutes=0, coding_required=True, source="HR_APPROVED",
            eval_criteria={
                "time_complexity": "O(n)", "space_complexity": "O(n)",
                "edge_cases": ["empty array", "no valid pair"],
                "rubric": "Award partial credit for a correct hash-map approach even if incomplete.",
            },
        )
        mcq_q = Question(
            id="iq-mcq-ec", title="Q", problem_statement="Which best describes Python?",
            difficulty="mid", competency="fundamentals",
            expected_concepts=[], hints=[], follow_up_topics=[],
            time_budget_minutes=0, coding_required=False, source="HR_APPROVED",
            eval_criteria={"explanation": "Python is an interpreted, general-purpose language."},
        )
        context.sections["VERBAL"] = OrderedSectionProgress(section_type="VERBAL", questions=[verbal_q])
        context.sections["CODING"] = OrderedSectionProgress(section_type="CODING", questions=[coding_q])
        context.sections["MCQ"] = OrderedSectionProgress(section_type="MCQ", questions=[mcq_q])

        llm = CapturingLLM()
        controller = InterviewController(llm, MockPersistence(), context)

        await controller.generate_final_evaluation()

        assert llm.received is not None
        evidence = json.loads(llm.received[0]["content"])
        criteria = evidence["question_eval_criteria"]

        # Each type's rubric reaches the evaluator in its own native shape --
        # none reshaped to match another type's.
        assert criteria["iq-verbal-ec"]["excellent"] == "Specific bug, clear root-cause reasoning, concrete fix."
        assert "time_complexity" not in criteria["iq-verbal-ec"]

        assert criteria["iq-coding-ec"]["rubric"] == "Award partial credit for a correct hash-map approach even if incomplete."
        assert criteria["iq-coding-ec"]["edge_cases"] == ["empty array", "no valid pair"]
        assert "excellent" not in criteria["iq-coding-ec"]

        assert criteria["iq-mcq-ec"]["explanation"] == "Python is an interpreted, general-purpose language."
        assert "rubric" not in criteria["iq-mcq-ec"]

    asyncio.run(scenario())


def test_9d_eval_criteria_empty_for_legacy_session_without_crashing():
    """9D: a legacy (pre-Phase-7) session has no context.sections at all --
    question_eval_criteria must degrade to {} gracefully, not crash, and
    generate_final_evaluation()'s pre-9D evidence keys stay unaffected."""
    import json
    from agent.interview.models import DetailedEvaluation, Message

    class CapturingLLM:
        def __init__(self):
            self.received = None

        async def generate_structured(self, system_prompt, messages, response_model):
            self.received = messages
            return DetailedEvaluation(overall_score=3, recommendation="Consider / Mixed", summary="Mixed evidence.")

    async def scenario():
        context = make_controller(InterviewPhase.COMPLETED).context
        context.conversation_history.append(Message(role="user", content="I would use a hash map."))
        llm = CapturingLLM()
        controller = InterviewController(llm, MockPersistence(), context)

        await controller.generate_final_evaluation()

        evidence = json.loads(llm.received[0]["content"])
        assert evidence["question_eval_criteria"] == {}
        assert "I would use a hash map." in evidence["transcript"][0]["text"]

    asyncio.run(scenario())


# ─── Phase 9E — Prompt engineering per type ─────────────────────────────────

class _CapturingSystemPromptLLM:
    """Captures the system_prompt _generate_next_action() built, without
    caring what StructuredAction is returned."""
    def __init__(self):
        self.received_system_prompt = None

    async def generate_structured(self, system_prompt, messages, response_model):
        self.received_system_prompt = system_prompt
        from agent.interview.models import StructuredAction, ActionEnum
        return StructuredAction(action=ActionEnum.ASK, response="ok", reason="test")


def test_9e_core_coding_question_prompt_uses_the_new_template():
    """9E: a CODING core question must get its own prompt -- correct phase
    label, the real problem/config content, and the explicit
    never-self-TRANSITION completion instruction -- not the generic
    CORE_QUESTION_PROMPT (which used to hardcode "CURRENT PHASE: VERBAL"
    even for CODING/MCQ questions and never mentioned config at all)."""
    async def scenario():
        context = make_controller(InterviewPhase.BACKGROUND).context
        coding_q = Question(
            id="iq-coding-prompt", title="Two Sum", problem_statement="Find two numbers that sum to target.",
            difficulty="mid", competency="algorithms",
            expected_concepts=[], hints=["Consider a hash map."], follow_up_topics=[],
            time_budget_minutes=0, coding_required=True, source="HR_APPROVED",
            config={
                "starter_code": "def two_sum(nums, target):\n    pass",
                "supported_languages": ["python", "javascript"],
                "constraints": "2 <= nums.length <= 10^4",
            },
        )
        context.sections["CODING"] = OrderedSectionProgress(section_type="CODING", questions=[coding_q])
        llm = _CapturingSystemPromptLLM()
        controller = InterviewController(llm, MockPersistence(), context)

        await controller._generate_next_action()

        prompt = llm.received_system_prompt
        assert "CURRENT PHASE: CODING" in prompt
        assert "CURRENT PHASE: VERBAL" not in prompt
        assert "Find two numbers that sum to target." in prompt
        assert "def two_sum(nums, target):" in prompt
        assert "python, javascript" in prompt
        assert "2 <= nums.length <= 10^4" in prompt
        assert "0 / 1 available" in prompt  # hints_used / _effective_max_hints(q)
        assert "SUBMITTING their code" in prompt  # deterministic completion instruction present

    asyncio.run(scenario())


def test_9e_core_mcq_question_prompt_uses_the_new_template():
    """9E: an MCQ core question must present its options (never done by the
    generic CORE_QUESTION_PROMPT before this) and correctly label the
    phase, plus the explicit "don't answer verbally" / never-self-complete
    instructions."""
    async def scenario():
        context = make_controller(InterviewPhase.BACKGROUND).context
        mcq_q = Question(
            id="iq-mcq-prompt", title="Q", problem_statement="Which best describes Python?",
            difficulty="mid", competency="fundamentals",
            expected_concepts=[], hints=[], follow_up_topics=[],
            time_budget_minutes=0, coding_required=False, source="HR_APPROVED",
            config={
                "options": [
                    {"id": "A", "text": "A programming language"},
                    {"id": "B", "text": "A snake"},
                ],
                "correct_answers": ["A"],
                "is_multi_select": False,
            },
        )
        context.sections["MCQ"] = OrderedSectionProgress(section_type="MCQ", questions=[mcq_q])
        llm = _CapturingSystemPromptLLM()
        controller = InterviewController(llm, MockPersistence(), context)

        await controller._generate_next_action()

        prompt = llm.received_system_prompt
        assert "CURRENT PHASE: MCQ" in prompt
        assert "CURRENT PHASE: VERBAL" not in prompt
        assert "Which best describes Python?" in prompt
        assert "A) A programming language" in prompt
        assert "B) A snake" in prompt
        assert "Select ONE option" in prompt
        assert "on-screen options" in prompt  # don't-answer-verbally instruction present

    asyncio.run(scenario())


def test_9e_core_verbal_question_prompt_unchanged():
    """9E standing-rule-4 regression: VERBAL core questions must keep using
    the exact same CORE_QUESTION_PROMPT as before -- none of the new
    CODING/MCQ-only text leaks in, and its own real content is untouched."""
    async def scenario():
        context = make_controller(InterviewPhase.BACKGROUND).context
        verbal_q = Question(
            id="iq-verbal-prompt", title="Debugging", problem_statement="Tell me about a challenging bug you fixed.",
            difficulty="mid", competency="debugging",
            expected_concepts=[], hints=[], follow_up_topics=[],
            time_budget_minutes=0, coding_required=False, source="HR_APPROVED",
        )
        context.sections["VERBAL"] = OrderedSectionProgress(section_type="VERBAL", questions=[verbal_q])
        llm = _CapturingSystemPromptLLM()
        controller = InterviewController(llm, MockPersistence(), context)

        await controller._generate_next_action()

        prompt = llm.received_system_prompt
        assert "CURRENT PHASE: VERBAL" in prompt
        assert "Tell me about a challenging bug you fixed." in prompt
        assert "You may ask up to 2 follow-up(s)" in prompt  # normal time tier, unchanged wording
        # None of the new type-specific text leaked into VERBAL's prompt.
        assert "SUBMITTING their code" not in prompt
        assert "on-screen options" not in prompt
        assert "CURRENT PHASE: CODING" not in prompt
        assert "CURRENT PHASE: MCQ" not in prompt

    asyncio.run(scenario())


def test_9e_coding_transition_cannot_self_complete_the_question():
    """9E-found gap, now fixed: mirrors
    test_adversarial_first_turn_transition_cannot_silently_skip_core_question,
    but proves the deeper case -- even an ALREADY-ASKED CODING question
    (current_question_asked=True, so the pre-9E "asked at least once" gate
    alone would have let this through) must not be completed by a bare LLM
    TRANSITION. Only SUBMIT_CODE (9C) may complete it."""
    from agent.interview.models import StructuredAction, ActionEnum

    class AlwaysTransitionLLM:
        async def generate_structured(self, system_prompt, messages, response_model):
            return StructuredAction(
                action=ActionEnum.TRANSITION,
                response="Sounds like a solid approach, let's move on.",
                reason="(should be rejected) LLM judged the discussion sufficient",
                should_transition=True,
            )

    async def scenario():
        context = make_controller(InterviewPhase.BACKGROUND).context
        coding_q = Question(
            id="iq-coding-guard", title="Two Sum", problem_statement="Find two numbers that sum to target.",
            difficulty="mid", competency="algorithms",
            expected_concepts=[], hints=[], follow_up_topics=[],
            time_budget_minutes=0, coding_required=True, source="HR_APPROVED",
        )
        section = OrderedSectionProgress(section_type="CODING", questions=[coding_q])
        section.current_question_asked = True
        context.sections["CODING"] = section
        controller = InterviewController(AlwaysTransitionLLM(), MockPersistence(), context)

        action = await controller.process_candidate_input()

        assert action.action == ActionEnum.ASK  # downgraded, not TRANSITION
        assert action.response == "Find two numbers that sum to target."  # real question substituted in
        assert controller.context.current_phase == InterviewPhase.BACKGROUND
        assert context.sections["CODING"].current_index == 0  # did not advance
        assert context.sections["CODING"].completed is False
        assert controller.context.question_records == []  # nothing recorded as completed

    asyncio.run(scenario())


def test_9e_mcq_transition_cannot_self_complete_the_question():
    """9E-found gap, now fixed: same as the CODING guard test, for MCQ."""
    from agent.interview.models import StructuredAction, ActionEnum

    class AlwaysTransitionLLM:
        async def generate_structured(self, system_prompt, messages, response_model):
            return StructuredAction(
                action=ActionEnum.TRANSITION,
                response="Great, moving on.",
                reason="(should be rejected)",
                should_transition=True,
            )

    async def scenario():
        context = make_controller(InterviewPhase.BACKGROUND).context
        mcq_q = Question(
            id="iq-mcq-guard", title="Q", problem_statement="Which best describes Python?",
            difficulty="mid", competency="fundamentals",
            expected_concepts=[], hints=[], follow_up_topics=[],
            time_budget_minutes=0, coding_required=False, source="HR_APPROVED",
        )
        section = OrderedSectionProgress(section_type="MCQ", questions=[mcq_q])
        section.current_question_asked = True
        context.sections["MCQ"] = section
        controller = InterviewController(AlwaysTransitionLLM(), MockPersistence(), context)

        action = await controller.process_candidate_input()

        assert action.action == ActionEnum.ASK
        assert action.response == "Which best describes Python?"
        assert context.sections["MCQ"].current_index == 0
        assert context.sections["MCQ"].completed is False
        assert controller.context.question_records == []

    asyncio.run(scenario())


# ─── Phase 9I — Integration verification (mirrors 7F) ───────────────────────
#
# Explored first (per 9I's own instruction) what 7F/9B/9D/9E's existing
# tests already cover, so this doesn't duplicate them:
#   - 7F: full VERBAL-only 3-question walk with follow-up cap + persistence.
#   - 9B (fixed): all three types in one walk, ordering + follow-up caps +
#     persistence -- but with minimal/empty question config, no hints
#     exercised, and no per-question eval_criteria/prompt-content assertions.
#   - 9C: SUBMIT_CODE/SUBMIT_MCQ_ANSWER/REQUEST_HINT mechanics, each in
#     ISOLATION (one command against a freshly-constructed controller).
#   - 9D: eval_criteria reaching generate_final_evaluation()'s evidence,
#     called directly (no walk -- context.sections built by hand, no ASK/
#     hint/submission ever actually happened first).
#   - 9E: prompt content (CODING/MCQ templates) and the TRANSITION-guard,
#     each verified via one isolated _generate_next_action()/
#     process_candidate_input() call, not a full walk.
#
# What was NOT yet proven anywhere: a single CODING interview and a single
# MCQ interview, each run start-to-finish (presentation with REAL config,
# in CODING's case a mid-solving hint request, completion via the real
# submission command, final evaluation actually seeing that exact
# question's real eval_criteria shape, and persistence) as ONE continuous
# scenario -- proving the pieces work together, not just each in isolation.

def test_9i_full_coding_interview_walk_with_hints_submission_and_evaluation():
    """9I: full simulated CODING interview, mirroring 7F's pattern (for
    VERBAL) but for CODING. Proves, together, in one continuous walk:
      - the question is presented with its real config (starter_code,
        constraints) via CORE_CODING_QUESTION_PROMPT (9E)
      - REQUEST_HINT mid-solving returns the real predefined hint,
        deterministically, without an LLM call (9C's ported _provide_hint())
      - a bare LLM TRANSITION attempt mid-walk (after presentation, before
        submission) is deterministically downgraded, not just in 9E's
        isolated test but inside this full continuous walk
      - the question completes via SUBMIT_CODE, never an LLM TRANSITION (9E)
      - generate_final_evaluation()'s evidence carries this exact question's
        real CODING-shaped eval_criteria (time_complexity/space_complexity/
        edge_cases/rubric, not VERBAL's bands) alongside the actual
        submitted code (9D)
      - final persistence captures the completed record with hints_used
    """
    import json
    from agent.interview.models import StructuredAction, ActionEnum, OrderedSectionProgress, DetailedEvaluation

    class CodingWalkLLM:
        def __init__(self):
            self.system_prompts = []
            self.turn = 0
            self.evaluator_messages = None

        async def generate_structured(self, system_prompt, messages, response_model):
            if response_model is DetailedEvaluation:
                self.evaluator_messages = messages
                return DetailedEvaluation(
                    overall_score=4, recommendation="Hire",
                    summary="Right approach (hash map), implementation left incomplete.",
                )
            self.system_prompts.append(system_prompt)
            if "CURRENT PHASE: CLOSING" in system_prompt:
                return StructuredAction(action=ActionEnum.END, response="Thanks for your time!", reason="Wrapping up.")
            self.turn += 1
            if self.turn == 1:
                return StructuredAction(action=ActionEnum.ASK, response="Here's the problem.", reason="Posing the core question.")
            if self.turn == 2:
                # Illegitimate: reuses 9E's exact scripted-action pattern
                # (test_9e_coding_transition_cannot_self_complete_the_question)
                # -- the LLM judges the discussion sufficient and tries to
                # end the question itself. Must be downgraded here too, mid-
                # walk, not just when exercised in isolation.
                return StructuredAction(
                    action=ActionEnum.TRANSITION,
                    response="Sounds like a solid approach, let's move on.",
                    reason="(should be rejected) LLM judged the discussion sufficient",
                    should_transition=True,
                )
            return StructuredAction(action=ActionEnum.ACKNOWLEDGE, response="Sounds good, take your time.", reason="Acknowledging approach discussion.")

    async def scenario():
        context = make_controller(InterviewPhase.BACKGROUND).context
        coding_q = Question(
            id="iq-coding-full", title="Two Sum",
            problem_statement="Given an array of integers, return indices of the two numbers that add up to a target.",
            difficulty="mid", competency="algorithms",
            expected_concepts=[],
            hints=["Consider a hash map of seen values.", "What's the complement of the current number?"],
            follow_up_topics=[], time_budget_minutes=0, coding_required=True, source="HR_APPROVED",
            config={
                "starter_code": "def two_sum(nums, target):\n    pass",
                "supported_languages": ["python"],
                "constraints": "2 <= nums.length <= 10^4",
            },
            eval_criteria={
                "time_complexity": "O(n)", "space_complexity": "O(n)",
                "edge_cases": ["empty array", "no valid pair"],
                "rubric": "Award partial credit for a correct hash-map approach even if incomplete.",
            },
        )
        context.sections["CODING"] = OrderedSectionProgress(section_type="CODING", questions=[coding_q])
        llm = CodingWalkLLM()
        persistence = MockPersistence()
        controller = InterviewController(llm, persistence, context)

        # 1. Presentation -- real config reaches the prompt (9E).
        ask_action = await controller.process_candidate_input()
        assert ask_action.action == ActionEnum.ASK
        assert "CURRENT PHASE: CODING" in llm.system_prompts[0]
        assert "def two_sum(nums, target):" in llm.system_prompts[0]
        assert "2 <= nums.length <= 10^4" in llm.system_prompts[0]
        assert context.sections["CODING"].current_question_asked is True

        # 2. Bare LLM TRANSITION attempt, mid-walk -- must be downgraded to
        #    ASK with the real question substituted in, not allowed to
        #    complete the question (9E, now proven inside a full walk).
        transition_attempt = await controller.process_candidate_input("I think that covers it.")
        assert transition_attempt.action == ActionEnum.ASK
        assert transition_attempt.response == coding_q.problem_statement
        assert context.sections["CODING"].current_index == 0  # did not advance
        assert context.sections["CODING"].completed is False
        assert context.question_records == []  # nothing recorded as completed

        # 3. Live discussion -- candidate thinks aloud, LLM acknowledges.
        ack_action = await controller.process_candidate_input("I'd use a hash map to track seen values.")
        assert ack_action.action == ActionEnum.ACKNOWLEDGE

        # 4. Mid-solving hint request -- deterministic, no LLM call, ported
        #    from the legacy single-question mechanism (9C).
        hint_action = await controller.process_ui_command("REQUEST_HINT")
        assert hint_action.action == ActionEnum.HINT
        assert hint_action.response == "Consider a hash map of seen values."
        assert context.hints_used == 1

        # 5. Completion -- SUBMIT_CODE, not the LLM's own judgment (9E).
        submit_action = await controller.process_ui_command(
            "SUBMIT_CODE",
            {"payload": {
                "code": "def two_sum(nums, target):\n    seen = {}\n    for i, n in enumerate(nums):\n        ...",
                "language": "python",
            }},
        )
        assert submit_action.action == ActionEnum.ACKNOWLEDGE
        assert context.current_phase == InterviewPhase.CLOSING  # only section, now exhausted
        assert context.sections["CODING"].completed is True
        assert context.question_records[0].outcome.value == "COMPLETED"
        assert context.question_records[0].hints_used == 1
        assert context.technical_submission["code"].startswith("def two_sum")

        # 6. Wrap to COMPLETED.
        end_action = await controller.process_candidate_input()
        assert end_action.action == ActionEnum.END
        assert context.current_phase == InterviewPhase.COMPLETED

        # 7. Final evaluation -- this exact question's real CODING-shaped
        #    eval_criteria reaches the evaluator (9D), inside a real walk
        #    this time, not a hand-built evidence dict.
        evaluation = await controller.generate_final_evaluation()
        await persistence.save_completion(context)
        assert evaluation is not None
        evidence = json.loads(llm.evaluator_messages[0]["content"])
        criteria = evidence["question_eval_criteria"]["iq-coding-full"]
        assert criteria["rubric"] == "Award partial credit for a correct hash-map approach even if incomplete."
        assert criteria["edge_cases"] == ["empty array", "no valid pair"]
        assert "excellent" not in criteria  # never reshaped to VERBAL's bands (Option C)
        assert evidence["technical_submission"]["code"].startswith("def two_sum")

        final_result = persistence.storage[context.session_id]["final_result"]
        assert final_result["completed"] == 1
        assert final_result["evaluation"]["recommendation"] == "Hire"
        assert final_result["question_records"][0]["question_id"] == "iq-coding-full"

    asyncio.run(scenario())


def test_9i_full_mcq_interview_walk_with_submission_and_evaluation():
    """9I: full simulated MCQ interview, same pattern as the CODING test
    above. Proves, together, in one continuous walk:
      - real options are presented via CORE_MCQ_QUESTION_PROMPT (9E)
      - a bare LLM TRANSITION attempt mid-walk (after presentation, before
        submission) is deterministically downgraded, not just in 9E's
        isolated test but inside this full continuous walk
      - SUBMIT_MCQ_ANSWER grades deterministically and completes the
        question -- never an LLM TRANSITION (9C/9E)
      - generate_final_evaluation()'s evidence carries this exact
        question's real MCQ-shaped eval_criteria (explanation-only, not
        VERBAL's bands or CODING's complexity fields) AND the deterministic
        grading result already recorded on the question_record (9D)
      - final persistence captures the completed record
    """
    import json
    from agent.interview.models import StructuredAction, ActionEnum, OrderedSectionProgress, DetailedEvaluation

    class McqWalkLLM:
        def __init__(self):
            self.system_prompts = []
            self.turn = 0
            self.evaluator_messages = None

        async def generate_structured(self, system_prompt, messages, response_model):
            if response_model is DetailedEvaluation:
                self.evaluator_messages = messages
                return DetailedEvaluation(overall_score=5, recommendation="Hire", summary="Correctly answered.")
            self.system_prompts.append(system_prompt)
            if "CURRENT PHASE: CLOSING" in system_prompt:
                return StructuredAction(action=ActionEnum.END, response="Thanks!", reason="Wrapping up.")
            self.turn += 1
            if self.turn == 1:
                return StructuredAction(action=ActionEnum.ASK, response="Here's the question.", reason="Posing the core question.")
            # Illegitimate: reuses 9E's exact scripted-action pattern
            # (test_9e_mcq_transition_cannot_self_complete_the_question) --
            # must be downgraded here too, mid-walk.
            return StructuredAction(
                action=ActionEnum.TRANSITION,
                response="Great, moving on.",
                reason="(should be rejected)",
                should_transition=True,
            )

    async def scenario():
        context = make_controller(InterviewPhase.BACKGROUND).context
        mcq_q = Question(
            id="iq-mcq-full", title="Python Basics", problem_statement="Which best describes Python?",
            difficulty="mid", competency="fundamentals",
            expected_concepts=[], hints=[], follow_up_topics=[],
            time_budget_minutes=0, coding_required=False, source="HR_APPROVED",
            config={
                "options": [
                    {"id": "A", "text": "An interpreted, general-purpose programming language"},
                    {"id": "B", "text": "A snake species"},
                ],
                "correct_answers": ["A"], "is_multi_select": False,
            },
            eval_criteria={"explanation": "Python is an interpreted, general-purpose language."},
        )
        context.sections["MCQ"] = OrderedSectionProgress(section_type="MCQ", questions=[mcq_q])
        llm = McqWalkLLM()
        persistence = MockPersistence()
        controller = InterviewController(llm, persistence, context)

        # 1. Presentation -- real options reach the prompt (9E).
        ask_action = await controller.process_candidate_input()
        assert ask_action.action == ActionEnum.ASK
        assert "CURRENT PHASE: MCQ" in llm.system_prompts[0]
        assert "A) An interpreted, general-purpose programming language" in llm.system_prompts[0]
        assert "B) A snake species" in llm.system_prompts[0]

        # 2. Bare LLM TRANSITION attempt, mid-walk -- must be downgraded to
        #    ASK with the real question substituted in (9E, now proven
        #    inside a full walk).
        transition_attempt = await controller.process_candidate_input("I think it's A.")
        assert transition_attempt.action == ActionEnum.ASK
        assert transition_attempt.response == mcq_q.problem_statement
        assert context.sections["MCQ"].current_index == 0  # did not advance
        assert context.sections["MCQ"].completed is False
        assert context.question_records == []  # nothing recorded as completed

        # 3. Completion -- SUBMIT_MCQ_ANSWER grades and completes; never an
        #    LLM TRANSITION (9C/9E).
        submit_action = await controller.process_ui_command(
            "SUBMIT_MCQ_ANSWER", {"payload": {"selected_option_ids": ["A"]}}
        )
        assert submit_action.action == ActionEnum.ACKNOWLEDGE
        assert context.current_phase == InterviewPhase.CLOSING  # only section, now exhausted
        assert context.sections["MCQ"].completed is True
        assert context.question_records[0].outcome.value == "COMPLETED"
        assert "result=CORRECT." in context.question_records[0].evaluation.evidence

        # 4. Wrap to COMPLETED.
        end_action = await controller.process_candidate_input()
        assert end_action.action == ActionEnum.END
        assert context.current_phase == InterviewPhase.COMPLETED

        # 5. Final evaluation -- this exact question's real MCQ-shaped
        #    eval_criteria (explanation-only) reaches the evaluator (9D).
        evaluation = await controller.generate_final_evaluation()
        await persistence.save_completion(context)
        assert evaluation is not None
        evidence = json.loads(llm.evaluator_messages[0]["content"])
        criteria = evidence["question_eval_criteria"]["iq-mcq-full"]
        assert criteria == {"explanation": "Python is an interpreted, general-purpose language."}
        # The deterministic 9C grading result is what the evaluator is told
        # to trust as ground truth -- confirm it's actually there.
        assert "result=CORRECT." in evidence["question_records"][0]["evaluation"]["evidence"]

        final_result = persistence.storage[context.session_id]["final_result"]
        assert final_result["completed"] == 1
        assert final_result["evaluation"]["recommendation"] == "Hire"
        assert final_result["question_records"][0]["question_id"] == "iq-mcq-full"

    asyncio.run(scenario())
