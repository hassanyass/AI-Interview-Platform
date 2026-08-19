import json
import uuid
from typing import Optional

from app.interview.input_limits import MAX_JOB_DESCRIPTION_CHARS, MAX_PROFILE_CHARS, truncate_prompt_text
from app.interview.models import Question
from app.llm.provider import LLMProvider


CUSTOM_QUESTION_PROMPT = """
You are designing one realistic technical interview coding problem for a candidate.
Use the candidate CV and the optional target job description as the primary source of
context. The problem must test a skill relevant to both the role and the candidate's
background, but must not copy a project verbatim or ask for private information.

Requirements:
- Generate one original, practical problem, not a generic Two Sum, LRU Cache, or rate limiter question.
- Make the scenario fit the target role and the technologies or responsibilities in the job description.
- Use the candidate's experience only to choose an appropriate level and realistic context.
- The candidate must explain the approach first and then submit code, so coding_required must be true.
- Keep the problem solvable in a focused interview and include clear constraints, examples, hints, and expected concepts.
- Do not require a framework or external service to run the solution.
- Return only JSON matching the Question schema.

Target role: {role}
Seniority: {level}
Interview language: {language}
Job description (optional): {job_description}
Candidate CV profile: {candidate_profile}
Previously used technical questions in this session (do not repeat them): {previous_questions}
""".strip()

LEGACY_QUESTION_MARKERS = ("two sum", "target sum", "least recently used", "lru cache", "rate limiter")


async def generate_custom_question(
    llm: LLMProvider,
    role: str,
    level: str,
    language: str,
    job_description: Optional[str],
    candidate_profile: dict,
    previous_questions: Optional[list[str]] = None,
) -> Question:
    """Generate one bounded, structured question from the interview context."""
    prompt = CUSTOM_QUESTION_PROMPT.format(
        role=truncate_prompt_text(role, 240),
        level=level,
        language=language,
        job_description=truncate_prompt_text(job_description, MAX_JOB_DESCRIPTION_CHARS) or "No job description provided.",
        candidate_profile=truncate_prompt_text(json.dumps(candidate_profile or {}, ensure_ascii=False), MAX_PROFILE_CHARS),
        previous_questions=truncate_prompt_text("\n".join(previous_questions or []) or "None", 2400),
    )
    question = await llm.generate_structured(
        system_prompt=prompt,
        messages=[{"role": "user", "content": "Create the tailored technical problem now."}],
        response_model=Question,
    )
    combined_text = f"{question.title} {question.problem_statement}".lower()
    if any(marker in combined_text for marker in LEGACY_QUESTION_MARKERS):
        raise ValueError("Generated question matched a legacy QUESTION_BANK problem")
    question.id = f"custom-{uuid.uuid4().hex[:12]}"
    question.source = "LLM_GENERATED"
    question.difficulty = level
    question.coding_required = True
    if not question.supported_languages:
        question.supported_languages = ["python"]
    if not question.starter_code:
        question.starter_code = {language: "" for language in question.supported_languages}
    return question


def build_contextual_fallback_question(role: str, level: str, language: str, job_description: Optional[str], candidate_profile: dict) -> Question:
    """Create an emergency contextual problem without using QUESTION_BANK."""
    profile = candidate_profile or {}
    technologies = [str(value) for key in ("skills", "programming_languages", "frameworks") for value in (profile.get(key) or [])]
    technology_text = ", ".join(technologies[:6]) or "the technologies in the target role"
    focus = truncate_prompt_text(job_description, 220) or f"the responsibilities of a {role}"
    if level == "junior":
        problem = f"For a {role} role using {technology_text}, implement a small component that validates and groups incoming records. The target context is: {focus}. Explain your data structures, handle malformed input, and provide a working solution."
    elif level == "senior":
        problem = f"For a {role} role involving {technology_text}, design and implement a production-oriented component for this target context: {focus}. Address throughput, failure handling, concurrency, and observable tradeoffs before writing the core solution."
    else:
        problem = f"For a {role} role using {technology_text}, implement a reliable component for this target context: {focus}. Explain the algorithm, edge cases, complexity, and practical production tradeoffs before coding."
    return Question(
        id=f"fallback-{uuid.uuid4().hex[:12]}", title=f"{role} contextual implementation challenge", problem_statement=problem,
        difficulty=level, competency="contextual_engineering", expected_concepts=["requirements_analysis", "edge_cases", "complexity", "production_tradeoffs"],
        hints=["Start by identifying the input and output contract.", "Separate validation from the core operation.", "Discuss the most important failure and scale tradeoff.", "Keep the implementation focused on the stated target context."],
        follow_up_topics=["What would you monitor in production?", "How would you test the riskiest edge case?"], time_budget_minutes=12,
        coding_required=True, starter_code={"python": "# Explain your approach, then implement the solution here\n"}, supported_languages=["python"], source="CONTEXTUAL_FALLBACK",
    )
