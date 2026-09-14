import asyncio
import logging
from unittest.mock import AsyncMock

from agent.interview.models import (
    InterviewRuntimeContext,
    InterviewPhase,
    OrderedSectionProgress,
    Question,
)
from agent.interview.controller import InterviewController

logging.basicConfig(level=logging.INFO)

async def test_9b_generalization():
    # 1. Construct Mock Context
    context = InterviewRuntimeContext(
        session_id="mock-session-9b",
        candidate_id="c1",
        role="Backend Engineer",
        confirmed_level="mid",
        language="en",
    )
    
    # 2. Add multiple ordered core sections simulating /load parsing
    # VERBAL -> CODING -> MCQ
    context.sections = {
        "VERBAL": OrderedSectionProgress(
            section_type="VERBAL",
            questions=[
                Question(id="q1", title="Verbal Q1", problem_statement="Explain X", expected_concepts=[], hints=[], follow_up_topics=[], time_budget_minutes=0, coding_required=False, difficulty="mid")
            ]
        ),
        "CODING": OrderedSectionProgress(
            section_type="CODING",
            questions=[
                Question(id="q2", title="Coding Q1", problem_statement="Code Y", expected_concepts=[], hints=[], follow_up_topics=[], time_budget_minutes=0, coding_required=True, difficulty="mid", config={"starter_code": "def y(): pass"})
            ]
        ),
        "MCQ": OrderedSectionProgress(
            section_type="MCQ",
            questions=[
                Question(id="q3", title="MCQ Q1", problem_statement="Pick Z", expected_concepts=[], hints=[], follow_up_topics=[], time_budget_minutes=0, coding_required=False, difficulty="mid", config={"options": []})
            ]
        )
    }
    
    # 3. Setup Controller
    controller = InterviewController(
        llm=AsyncMock(),
        persistence=AsyncMock(),
        context=context
    )
    
    print("--- Starting 9B verification ---")
    
    # Simulate entering BACKGROUND (which is the loop for core sections)
    controller.context.current_phase = InterviewPhase.BACKGROUND
    print(f"Current phase: {controller.context.current_phase.value}")
    
    active = controller._active_core_section()
    print(f"Active section: {active.section_type if active else 'None'}")
    assert active.section_type == "VERBAL"
    
    # Complete VERBAL
    print("Advancing question in VERBAL...")
    controller._advance_core_question()
    
    # Check if section naturally progressed to CODING (by checking active section again)
    active = controller._active_core_section()
    print(f"Active section: {active.section_type if active else 'None'}")
    assert active.section_type == "CODING"
    
    # Check max followups for CODING (no competency means 0)
    print(f"CODING max followups (no competency): {controller._current_max_followups()}")
    
    # Complete CODING
    print("Advancing question in CODING...")
    controller._advance_core_question()
    
    active = controller._active_core_section()
    print(f"Active section: {active.section_type if active else 'None'}")
    assert active.section_type == "MCQ"
    
    # Check max followups for MCQ (should be 0 regardless)
    controller.context.sections["MCQ"].questions[0].competency = "Python" # give it a competency
    print(f"MCQ max followups (with competency): {controller._current_max_followups()}")
    assert controller._current_max_followups() == 0, "MCQ must have 0 followups"
    
    # Instead of manual advance, simulate the _handle_automatic_transition loop 
    # to see if it transitions to CLOSING when done.
    print("Calling _handle_automatic_transition for MCQ completion...")
    controller._handle_automatic_transition()
    
    print(f"Final phase after all sections exhausted: {controller.context.current_phase.value}")
    assert controller.context.current_phase == InterviewPhase.CLOSING, "Must transition to CLOSING!"
    
    print("--- SUCCESS: Generalization works across sections ---")


if __name__ == "__main__":
    asyncio.run(test_9b_generalization())
