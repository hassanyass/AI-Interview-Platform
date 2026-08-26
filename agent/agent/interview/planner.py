import json
from agent.llm.provider import LLMProvider
from agent.llm.prompts import PLANNER_PROMPT
from agent.interview.models import InterviewPlan
from agent.interview.input_limits import (
    MAX_JOB_DESCRIPTION_CHARS,
    MAX_PROFILE_CHARS,
    truncate_prompt_text,
)

class InterviewPlanner:
    def __init__(self, llm_provider: LLMProvider):
        self.llm = llm_provider
        
    async def generate_plan(
        self,
        role: str,
        level: str,
        duration_minutes: int,
        job_description: str,
        candidate_profile: dict
    ) -> InterviewPlan:
        """
        Calls the LLM to generate a structured InterviewPlan based on the JD and profile.
        """
        system_prompt = PLANNER_PROMPT.format(level=level)
        
        user_message = {
            "role": "user",
            "content": (
                f"Role: {role}\n"
                f"Duration: {duration_minutes} minutes\n"
                f"Job Description: {truncate_prompt_text(job_description, MAX_JOB_DESCRIPTION_CHARS) or 'None provided.'}\n"
                f"Candidate Profile: {truncate_prompt_text(json.dumps(candidate_profile, indent=2), MAX_PROFILE_CHARS)}\n"
            )
        }
        
        plan = await self.llm.generate_structured(
            system_prompt=system_prompt,
            messages=[user_message],
            response_model=InterviewPlan
        )
        
        return plan
