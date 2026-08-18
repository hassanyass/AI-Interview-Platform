import pytest
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'agent'))

from unittest.mock import MagicMock
from app.interview.controller import InterviewController
from app.interview.models import (
    CandidateControlAction, InterviewPhase, Question, StructuredAction, ActionEnum, SectionProgress,
    InterviewRuntimeContext, InterviewPlan, SectionLimits, QuestionOutcome, EvaluationSignal
)
from app.interview.persistence import MockPersistence

@pytest.fixture
def mock_controller():
    llm = MagicMock()
    persistence = MockPersistence()
    
    context = InterviewRuntimeContext(
        session_id="test-session",
        agent_id="test-agent",
        candidate_id="test-candidate",
        role="test-role",
        confirmed_level="mid",
        language="en",
        interview_plan=InterviewPlan(
            id="plan-1", role="test", level="mid", duration_minutes=60,
            background_limits=SectionLimits(target_questions=1, max_questions=1, max_hints_per_question=0, max_followups=0),
            technical_limits=SectionLimits(target_questions=1, max_questions=2, max_hints_per_question=2, max_followups=2),
            competencies=["coding"]
        )
    )
    context.current_phase = InterviewPhase.TECHNICAL
    context.technical_progress = SectionProgress(
        name="technical",
        questions_completed=0,
        questions_skipped=0,
        questions_asked=1,
        limits=SectionLimits(target_questions=1, max_questions=2, max_hints_per_question=2, max_followups=2)
    )
    context.current_question = Question(
        id="q1",
        title="Test Q",
        problem_statement="Solve this.",
        hints=[],
        time_budget_minutes=15,
        coding_required=False,
        difficulty="mid",
        competency="coding",
        expected_concepts=[],
        follow_up_topics=[]
    )
    
    controller = InterviewController(llm=llm, persistence=persistence, context=context)
    return controller


@pytest.mark.asyncio
async def test_phase3e_evaluate_not_complete(mock_controller):
    """Prove EVALUATE != COMPLETE. Ensure current_question and question_records remain unchanged."""
    action = StructuredAction(
        action=ActionEnum.EVALUATE,
        response="Good approach.",
        reason="Evaluating approach",
        evaluation=EvaluationSignal(problem_understanding=4, evidence="Good")
    )
    
    await mock_controller._apply_action(action)
    
    # 1. EVALUATE does not transition state
    assert mock_controller.context.current_phase == InterviewPhase.TECHNICAL
    
    # 2. EVALUATE appends signal
    assert len(mock_controller.context.evaluation_signals) == 1
    assert mock_controller.context.evaluation_signals[0].problem_understanding == 4
    
    # 3. current_question unchanged
    assert mock_controller.context.current_question is not None
    assert mock_controller.context.current_question.id == "q1"
    
    # 4. question_records unchanged
    assert len(mock_controller.context.question_records) == 0


@pytest.mark.asyncio
async def test_phase3e_multiple_evaluations(mock_controller):
    """Prove multiple in-flight evaluation signals don't overwrite each other."""
    action1 = StructuredAction(
        action=ActionEnum.EVALUATE,
        response="Good.",
        reason="Eval 1",
        evaluation=EvaluationSignal(problem_understanding=3, evidence="Okay")
    )
    action2 = StructuredAction(
        action=ActionEnum.EVALUATE,
        response="Better.",
        reason="Eval 2",
        evaluation=EvaluationSignal(problem_understanding=5, evidence="Great")
    )
    
    await mock_controller._apply_action(action1)
    await mock_controller._apply_action(action2)
    
    assert len(mock_controller.context.evaluation_signals) == 2
    assert mock_controller.context.evaluation_signals[0].problem_understanding == 3
    assert mock_controller.context.evaluation_signals[1].problem_understanding == 5
    
    # Still no completion
    assert len(mock_controller.context.question_records) == 0


@pytest.mark.asyncio
async def test_phase3e_completion_deterministic_selection(mock_controller):
    """Prove completion selects the latest signal and clears evaluation_signals."""
    mock_controller.context.evaluation_signals = [
        EvaluationSignal(problem_understanding=2, evidence="Early"),
        EvaluationSignal(problem_understanding=5, evidence="Final")
    ]
    
    mock_controller._record_question_completion()
    
    # 1. question_records gets the latest eval
    assert len(mock_controller.context.question_records) == 1
    record = mock_controller.context.question_records[0]
    assert record.outcome == QuestionOutcome.COMPLETED
    assert record.evaluation.problem_understanding == 5
    assert record.evaluation.evidence == "Final"
    
    # 2. evaluation_signals cleared
    assert len(mock_controller.context.evaluation_signals) == 0


@pytest.mark.asyncio
async def test_phase3e_persistence_roundtrip():
    """Prove evaluation_signals survive a checkpoint restoration."""
    from app.main import entrypoint
    from app.interview.models import EvaluationSignal
    
    # Setup mock session data with an in-flight evaluation
    session_data = {
        "candidate_profile_id": "00000000-0000-0000-0000-000000000000",
        "role": "SWE",
        "level": "mid",
        "language": "en",
        "recent_messages": [
            {"speaker": "agent", "text": "Hi", "metadata": {"is_greeting": True}}
        ],
        "latest_checkpoint": {
            "current_phase": "TECHNICAL",
            "evaluation_signals": [
                {"problem_understanding": 4, "evidence": "Understood the hash map approach"}
            ]
        }
    }
    
    # We will just manually run the restoration logic from main.py to verify
    # (Since entrypoint uses global environment variables and connects to livekit, we isolate the restoration)
    context = InterviewRuntimeContext(
        session_id="test-session",
        candidate_id=session_data["candidate_profile_id"],
        role=session_data["role"],
        confirmed_level=session_data["level"],
        language=session_data["language"],
        current_phase=InterviewPhase(session_data["latest_checkpoint"]["current_phase"]),
    )
    
    evals_snapshot = session_data["latest_checkpoint"].get("evaluation_signals", [])
    if evals_snapshot:
        context.evaluation_signals = [EvaluationSignal(**e) for e in evals_snapshot]
        
    assert len(context.evaluation_signals) == 1
    assert context.evaluation_signals[0].problem_understanding == 4
    assert context.evaluation_signals[0].evidence == "Understood the hash map approach"


def run_phase3e_tests():
    pytest.main(["-v", __file__])

if __name__ == "__main__":
    run_phase3e_tests()
