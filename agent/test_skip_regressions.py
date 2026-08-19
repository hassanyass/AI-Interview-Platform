import asyncio

from app.interview.controller import InterviewController
from app.interview.models import (
    CandidateControlAction,
    InterviewPhase,
    InterviewRuntimeContext,
)
from app.interview.persistence import MockPersistence
from app.interview.questions import QUESTION_BANK
from app.interview.questions import rank_questions_for_context
from app.interview.question_generator import generate_custom_question
from app.interview.models import Question


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


def test_vad_segments_are_coalesced_into_one_candidate_turn():
    from app.interview.voice_adapter import VoiceInterviewAdapter

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
    from app.interview.voice_adapter import VoiceInterviewAdapter

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
    from app.interview.voice_adapter import VoiceInterviewAdapter

    async def scenario():
        adapter = object.__new__(VoiceInterviewAdapter)
        adapter._is_interrupted = False
        adapter._generation_id = 12
        adapter._tts_queue = asyncio.Queue()
        adapter._current_synthesis_task = None
        adapter._handle_interruption()

        assert adapter._generation_id == 13
        assert adapter._is_interrupted is True

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


def test_final_evaluation_uses_transcript_and_is_persisted():
    from app.interview.models import DetailedEvaluation, Message

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
