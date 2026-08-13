import asyncio
import json
import logging
import uuid
from pprint import pprint

from app.llm.groq_provider import GroqProvider
from app.interview.models import InterviewRuntimeContext, InterviewPhase
from app.interview.persistence import MockPersistence
from app.interview.planner import InterviewPlanner
from app.interview.controller import InterviewController
from app.interview.questions import get_questions_by_competency

# Disable excessive logging for the CLI experience
logging.getLogger("httpx").setLevel(logging.WARNING)

async def run_simulator():
    print("========================================")
    print("   AI INTERVIEW SIMULATOR (PHASE 3)   ")
    print("========================================")

    # 1. Initialize dependencies
    llm = GroqProvider()
    persistence = MockPersistence()
    planner = InterviewPlanner(llm)

    # 2. Mock Candidate and JD
    role = "Software Engineer"
    level = "mid"
    duration_minutes = 15
    job_description = "We are looking for a backend engineer familiar with Python, FastAPI, and PostgreSQL."
    candidate_profile = {
        "full_name": "Test Candidate",
        "years_of_experience": 4,
        "skills": ["Python", "FastAPI", "SQL"],
        "projects": ["Built a REST API for a fintech startup handling 1M req/day"]
    }

    print("\n[Simulator] Generating Interview Plan...")
    plan = await planner.generate_plan(
        role=role,
        level=level,
        duration_minutes=duration_minutes,
        job_description=job_description,
        candidate_profile=candidate_profile
    )
    print("\n[Interview Plan Generated]")
    print(f"Competencies: {plan.competencies}")
    print(f"Strategy: {plan.question_strategy}")
    print("----------------------------------------\n")

    # 3. Create Runtime Context
    context = InterviewRuntimeContext(
        session_id=str(uuid.uuid4()),
        candidate_id=str(uuid.uuid4()),
        role=role,
        confirmed_level=level,
        language="en",
        job_description=job_description,
        candidate_profile=candidate_profile,
        time_remaining_seconds=duration_minutes * 60
    )

    controller = InterviewController(llm, persistence, context)
    controller.start_interview()

    # Select a mock question for the technical phase
    technical_questions = get_questions_by_competency("data_structures", "junior")
    if technical_questions:
        controller.load_question(technical_questions[0])

    print(f"--- Phase: {controller.context.current_phase.value} ---")
    print("AI: Hello! Welcome to your interview. Let me know when you are ready to begin.")

    # 4. Interactive Loop
    while controller.context.current_phase != InterviewPhase.COMPLETED:
        user_input = input("\nCandidate: ")
        
        if user_input.strip().lower() in ["exit", "quit"]:
            print("[Simulator] Exiting early.")
            break
            
        # Optional: commands to skip time for testing
        if user_input.startswith("/skip"):
            controller._total_duration_sec = 0 # Force expiration
            print("[Simulator] Forced time expiration.")

        print("[AI thinking...]")
        action = await controller.process_candidate_input(user_input)
        
        print(f"\n--- Phase: {controller.context.current_phase.value} ---")
        print(f"Action Type: {action.action.value}")
        print(f"AI: {action.response}")
        
        if action.evaluation:
            print("\n[Internal Evaluation Generated]")
            pprint(action.evaluation.model_dump(exclude_none=True))

    print("\n========================================")
    print("           INTERVIEW COMPLETE           ")
    print("========================================")

if __name__ == "__main__":
    asyncio.run(run_simulator())
