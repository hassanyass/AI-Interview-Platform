import asyncio

from app.interview.controller import InterviewController
from app.interview.models import (
    CandidateControlAction,
    InterviewPhase,
    InterviewRuntimeContext,
)
from app.interview.persistence import MockPersistence
from app.interview.questions import QUESTION_BANK


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
    from app.interview.voice_adapter import VoiceInterviewAdapter

    async def scenario():
        adapter = object.__new__(VoiceInterviewAdapter)
        adapter._is_interrupted = False
        adapter._generation_id = 4
        adapter._tts_queue = asyncio.Queue()
        await adapter._tts_queue.put(("pending", 1, 1, 4))
        adapter._current_synthesis_task = None

        adapter._handle_interruption()

        assert adapter._is_interrupted is True
        assert adapter._generation_id == 5
        assert adapter._tts_queue.empty()

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
