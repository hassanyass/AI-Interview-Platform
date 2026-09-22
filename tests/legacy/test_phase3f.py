import pytest
from uuid import uuid4
from datetime import datetime, timezone

from agent.interview.controller import InterviewController
from agent.interview.models import (
    InterviewRuntimeContext, InterviewPhase, ActionEnum,
    CandidateControlAction, QuestionOutcome, EvaluationSignal, QuestionRecord,
    Question, InterviewPlan, SectionLimits
)
from agent.interview.persistence import MockPersistence

@pytest.fixture
def mock_persistence():
    return MockPersistence()

from agent.llm.provider import LLMProvider
class DummyLLM(LLMProvider):
    async def generate_response(self, context): return None
    async def stream_response(self, context): pass
    async def generate_structured(self, *args, **kwargs): return None
    async def generate_text(self, *args, **kwargs): return ""
    
@pytest.fixture
def mock_controller(mock_persistence):
    context = InterviewRuntimeContext(
        session_id=str(uuid4()),
        candidate_id=str(uuid4()),
        role="Backend Engineer",
        confirmed_level="mid",
        language="en",
        current_phase=InterviewPhase.CLOSING,
        interview_plan=InterviewPlan(
            role="Backend",
            level="mid",
            duration_minutes=30,
            technical_limits=SectionLimits(target_questions=2, max_questions=3, max_followups_per_question=2, max_hints_per_question=4)
        )
    )
    context.question_records = [
        QuestionRecord(question_id="q1", outcome=QuestionOutcome.COMPLETED),
        QuestionRecord(question_id="q2", outcome=QuestionOutcome.SKIPPED),
        QuestionRecord(question_id="q3", outcome=QuestionOutcome.CHANGED),
        QuestionRecord(question_id="q4", outcome=QuestionOutcome.COMPLETED)
    ]
    return InterviewController(llm=DummyLLM(), persistence=mock_persistence, context=context)

@pytest.mark.asyncio
async def test_phase3f_completion_flow(mock_controller):
    """Test standard completion flow from CLOSING."""
    
    # We are in CLOSING. If the candidate ends or the agent decides to transition to END.
    from agent.interview.models import StructuredAction
    action = StructuredAction(
        action=ActionEnum.END,
        response="Goodbye.",
        reason="Interview finished.",
        should_transition=True
    )
    
    await mock_controller._apply_action(action)
    
    assert mock_controller.context.current_phase == InterviewPhase.COMPLETED
    assert mock_controller.context.current_question is None
    
    # Save completion
    await mock_controller.persistence.save_completion(mock_controller.context)
    
    # Check final result in persistence
    data = mock_controller.persistence.storage[mock_controller.context.session_id]
    assert data["status"] == "COMPLETED"
    assert "final_result" in data
    
    final = data["final_result"]
    assert final["total_questions"] == 4
    assert final["completed"] == 2
    assert final["skipped"] == 1
    assert final["changed"] == 1

@pytest.mark.asyncio
async def test_phase3f_immutability(mock_controller):
    """Test that a COMPLETED session rejects further interactions."""
    mock_controller.context.current_phase = InterviewPhase.COMPLETED
    
    # Attempt to send more text
    action = await mock_controller.process_candidate_input("Hello again")
    
    # It must return an END action and not modify phase
    assert action.action == ActionEnum.END
    assert mock_controller.context.current_phase == InterviewPhase.COMPLETED
    
@pytest.mark.asyncio
async def test_phase3f_evaluate_does_not_complete():
    """Verify that EVALUATE cannot transition to COMPLETED by itself."""
    from agent.interview.models import StructuredAction
    
    context = InterviewRuntimeContext(
        session_id=str(uuid4()),
        candidate_id=str(uuid4()),
        role="Test",
        confirmed_level="mid",
        language="en",
        current_phase=InterviewPhase.TECHNICAL,
    )
    controller = InterviewController(llm=DummyLLM(), persistence=MockPersistence(), context=context)
    
    action = StructuredAction(
        action=ActionEnum.EVALUATE,
        response="Evaluating",
        reason="Test",
        evaluation=EvaluationSignal(problem_understanding=5, evidence="Good")
    )
    
    await controller._apply_action(action)
    
    # Phase must not transition to COMPLETED
    assert controller.context.current_phase == InterviewPhase.TECHNICAL
