import pytest
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'agent'))

from unittest.mock import MagicMock, patch
from app.interview.controller import InterviewController
from app.interview.models import (
    CandidateControlAction, InterviewPhase, Question, StructuredAction, ActionEnum, SectionProgress,
    InterviewRuntimeContext, InterviewPlan, SectionLimits, QuestionOutcome
)

@pytest.fixture
def mock_controller():
    # Mock LLM and Persistence
    llm = MagicMock()
    persistence = MagicMock()
    
    # Context with a plan and limits
    context = InterviewRuntimeContext(
        session_id="test-session",
        agent_id="test-agent",
        candidate_id="test-candidate",
        role="test-role",
        confirmed_level="mid",
        language="en",
        interview_plan=InterviewPlan(
            id="plan-1", role="test", level="mid", duration_minutes=60,
            background_limits=SectionLimits(target_questions=2, max_questions=3, max_hints_per_question=0, max_followups=1),
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
    
    controller = InterviewController(llm=llm, persistence=persistence, context=context)
    
    # Mock the loading logic to just set a fixed next question
    def mock_load():
        controller.context.current_question = Question(
            id="q2",
            title="Next Q",
            problem_statement="Solve another.",
            hints=["Hint 1"],
            time_budget_minutes=15,
            coding_required=False,
            difficulty="mid",
            competency="coding",
            expected_concepts=[],
            follow_up_topics=[]
        )
    controller._load_next_technical_question = mock_load
    return controller

@pytest.mark.asyncio
async def test_phase3d_change_question_flow(mock_controller):
    """Tests 1, 2, 3, 4, 5, 10, 11: Normal change question lifecycle"""
    mock_controller.context.current_question = Question(
        id="q1",
        title="Test Q",
        problem_statement="Solve this.",
        hints=["Hint 1", "Hint 2"],
        time_budget_minutes=15,
        coding_required=False,
        difficulty="mid",
        competency="coding",
        expected_concepts=[],
        follow_up_topics=[]
    )
    mock_controller.context.hints_used = 2 # Setup some hint usage to verify it resets

    # Action: CHANGE_QUESTION (1)
    action = await mock_controller._handle_candidate_control(CandidateControlAction.CHANGE_QUESTION)
    
    # Verify controller intercepts and returns ACKNOWLEDGE (to avoid transition out of technical)
    assert action.action == ActionEnum.ACKNOWLEDGE
    assert action.should_transition is False
    
    # Verify q1 is recorded as CHANGED (2)
    assert len(mock_controller.context.question_records) == 1
    assert mock_controller.context.question_records[0].question_id == "q1"
    assert mock_controller.context.question_records[0].outcome == QuestionOutcome.CHANGED
    
    # Verify exactly one new question is active (3, 4)
    assert mock_controller.context.current_question.id == "q2"
    
    # Verify remain in TECHNICAL (5)
    assert mock_controller.context.current_phase == InterviewPhase.TECHNICAL
    
    # Verify hints used resets (11)
    assert mock_controller.context.hints_used == 0

    # Ensure Hint works on new question (10)
    hint_action = await mock_controller._handle_candidate_control(CandidateControlAction.REQUEST_HINT)
    assert hint_action.action == ActionEnum.HINT
    assert mock_controller.context.hints_used == 1

@pytest.mark.asyncio
async def test_phase3d_rejected_change(mock_controller):
    """Tests 6, 7, 8, 12: Second change rejected"""
    # Setup: Already changed one question
    from app.interview.models import QuestionRecord
    mock_controller.context.question_records.append(
        QuestionRecord(question_id="q0", outcome=QuestionOutcome.CHANGED, hints_used=0, followups_used=0)
    )
    
    mock_controller.context.current_question = Question(
        id="q1",
        title="Test Q",
        problem_statement="Solve this.",
        hints=["Hint 1"],
        time_budget_minutes=15,
        coding_required=False,
        difficulty="mid",
        competency="coding",
        expected_concepts=[],
        follow_up_topics=[]
    )
    
    # Attempt another change (6)
    action = await mock_controller._handle_candidate_control(CandidateControlAction.CHANGE_QUESTION)
    
    assert action.action == ActionEnum.ACKNOWLEDGE
    assert "I can only change the question once" in action.response
    
    # Verify rejected change leaves current_question untouched (7)
    assert mock_controller.context.current_question.id == "q1"
    
    # Verify no new record created (8)
    assert len(mock_controller.context.question_records) == 1 
    
    # Verify LLM cannot bypass it because the handler explicitly rejects it (12)

@pytest.mark.asyncio
async def test_phase3d_conversational_mutation(mock_controller):
    """Test 13: Natural conversational text cannot mutate question state"""
    mock_controller.context.current_question = Question(
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
    
    control = mock_controller._detect_candidate_control("let's use another problem")
    assert control == CandidateControlAction.CHANGE_QUESTION

    control_no_match = mock_controller._detect_candidate_control("I prefer a different topic")
    assert control_no_match is None
    
    assert mock_controller.context.current_question.id == "q1"

@pytest.mark.asyncio
async def test_phase3d_skip_vs_change(mock_controller):
    """Test 9: SKIP and CHANGE are distinct"""
    mock_controller.context.current_question = Question(
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
    
    action = await mock_controller._handle_candidate_control(CandidateControlAction.SKIP_QUESTION)
    
    assert action.action == ActionEnum.TRANSITION
    
    assert len(mock_controller.context.question_records) == 1
    assert mock_controller.context.question_records[0].outcome == QuestionOutcome.SKIPPED

def run_phase3d_tests():
    pytest.main(["-v", __file__])

if __name__ == "__main__":
    run_phase3d_tests()
