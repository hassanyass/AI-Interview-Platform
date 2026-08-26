import asyncio
import uuid
import sys
import logging

from agent.llm.groq_provider import GroqProvider
from agent.interview.models import InterviewRuntimeContext, InterviewPhase
from agent.interview.persistence import MockPersistence
from agent.interview.planner import InterviewPlanner
from agent.interview.controller import InterviewController
from agent.interview.questions import get_questions_by_competency

from dotenv import load_dotenv
import os
load_dotenv("../.env")

async def run_auto_test():
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Inject predefined candidate answers
    candidate_answers = [
        "Hi there, I am ready to begin.",
        "I built a REST API for a fintech startup handling 1M requests per day using FastAPI and Postgres.",
        "Let's move on to the technical section.",
        "My approach would be to use a hash map to store the elements we've seen so far.",
        "This gives us O(N) time complexity.",
        "I think that's it.",
        "/skip",  # skip time
        "Goodbye"
    ]

    llm = GroqProvider()
    persistence = MockPersistence()
    planner = InterviewPlanner(llm)

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

    plan = await planner.generate_plan(role, level, duration_minutes, job_description, candidate_profile)
    print(f"Generated Plan Strategy: {plan.question_strategy}")

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

    technical_questions = get_questions_by_competency("data_structures", "junior")
    if technical_questions:
        controller.load_question(technical_questions[0])

    answer_idx = 0
    while controller.context.current_phase != InterviewPhase.COMPLETED and answer_idx < len(candidate_answers):
        user_input = candidate_answers[answer_idx]
        answer_idx += 1
        
        print(f"\nCandidate: {user_input}")
        
        if user_input.startswith("/skip"):
            controller._total_duration_sec = 0

        action = await controller.process_candidate_input(user_input)
        
        print(f"--- Phase: {controller.context.current_phase.value} ---")
        print(f"Action Type: {action.action.value}")
        print(f"AI: {action.response}")

    print("\nTEST COMPLETED SUCCESSFULLY.")

if __name__ == "__main__":
    asyncio.run(run_auto_test())
