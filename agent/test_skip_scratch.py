import asyncio
from app.interview.controller import InterviewController
from app.interview.models import InterviewRuntimeContext, InterviewPhase, CandidateControlAction
from app.llm.groq_client import GroqClient
import json

async def test_skip():
    ctx = InterviewRuntimeContext(
        session_id="test",
        candidate_id="test_candidate",
        role="Backend Engineer",
        confirmed_level="junior",
        language="ar"
    )
    llm = GroqClient()
    controller = InterviewController(ctx, llm, None)
    
    # Force phase to BACKGROUND
    controller.context.current_phase = InterviewPhase.BACKGROUND
    controller.context.background_progress.questions_asked = 1
    
    print("Initial phase:", controller.context.current_phase)
    
    action = await controller.process_ui_command("SKIP_QUESTION")
    print("UI Command action:", action.action if action else None)
    
    print("Phase after SKIP:", controller.context.current_phase)
    
    next_action = await controller.process_candidate_input("")
    print("Chained next action:", next_action.action)
    print("Chained response:", next_action.response)
    print("Phase after chain:", controller.context.current_phase)
    print("State:", json.dumps(controller.get_interview_state_contract(), indent=2))

if __name__ == "__main__":
    asyncio.run(test_skip())
