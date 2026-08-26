"""
AI Question Generation Service — Phase 4.

Uses the official Groq Python SDK, reading GROQ_API_KEY and GROQ_MODEL
from the existing backend.core.config.settings.  This is a completely new
code path; it does NOT import from or depend on agent/agent/* in any way.
"""
import json
import logging
from typing import List, Optional

from groq import Groq

from backend.core.config import settings

logger = logging.getLogger(__name__)

# ── Prompt templates per section type ──────────────────────────────────────

_SYSTEM_PROMPTS: dict[str, str] = {
    "VERBAL": """\
You are an expert technical interviewer designing interview questions for
a hiring pipeline.  You will be given a job context and a section type.
Generate interview questions that are specific, practical, and directly
relevant to the role described.

Return your answer as a JSON array of objects.  Each object MUST have:
  - "title": a short label for the question (≤80 chars)
  - "competency": the skill or competency area being assessed
  - "text": the full question text the interviewer should ask
  - "eval_criteria": an object with keys "excellent", "good", "adequate",
    "poor" describing what each quality band looks like for this question

Return ONLY the JSON array, no markdown fences, no commentary.
""",
    "CODING": """\
You are an expert technical interviewer designing coding interview questions
for a hiring pipeline.  You will be given a job context.
Generate coding problems that are specific, practical, and relevant.

Return your answer as a JSON array of objects.  Each object MUST have:
  - "title": a short label for the problem (≤80 chars)
  - "competency": the skill area being assessed (e.g. "algorithms", "data structures")
  - "text": the problem statement in plain prose (describe the task clearly,
    include input/output examples inline)
  - "eval_criteria": an object with keys "time_complexity", "space_complexity",
    "edge_cases" (array of strings), and "rubric" (brief grading guidance)
  - "config": an object with:
      - "starter_code": a starter code template string (use Python unless
        the job context specifies otherwise)
      - "supported_languages": an array of language name strings (e.g. ["python", "javascript"])
      - "constraints": a string describing input constraints and limits
      - "hints": an array of 2-4 graduated hint strings, ordered from a
        gentle nudge toward the right approach to a stronger nudge. This is
        a LIVE interview — the candidate can ask for a hint while thinking
        aloud, not just after submitting. Hints must guide, never state the
        final answer, complete solution, or exact code outright.

Return ONLY the JSON array, no markdown fences, no commentary.
""",
    "MCQ": """\
You are an expert technical interviewer designing multiple-choice questions
for a hiring pipeline.  You will be given a job context.
Generate MCQ questions that are specific, practical, and relevant.

Return your answer as a JSON array of objects.  Each object MUST have:
  - "title": a short label for the question (≤80 chars)
  - "competency": the skill area being assessed
  - "text": the question stem in plain prose
  - "eval_criteria": null or an object with a single key "explanation" containing a brief string explaining why the correct answer is correct
  - "config": an object with:
      - "options": an array of objects, each with "id" (a short stable identifier
        like "A", "B", "C", "D") and "text" (the option text)
      - "correct_answers": an array of id strings matching the correct option(s)
      - "is_multi_select": boolean (true if more than one answer is correct)

Generate exactly 4 options per question.  Use single-select (is_multi_select: false)
unless the question genuinely has multiple correct answers.

Return ONLY the JSON array, no markdown fences, no commentary.
""",
}



def _build_user_prompt(
    *,
    job_title: str,
    job_description: Optional[str],
    seniority: Optional[str],
    required_skills: Optional[list],
    preferred_skills: Optional[list],
    responsibilities: Optional[list],
    location: Optional[str],
    candidate_instructions: Optional[str],
    section_type: str,
    section_config: Optional[dict],
    num_questions: int,
) -> str:
    parts = [f"Generate {num_questions} interview questions.\n"]
    parts.append(f"Job title: {job_title}")
    if job_description:
        parts.append(f"Job description: {job_description}")
    if seniority:
        parts.append(f"Seniority level: {seniority}")
    if required_skills:
        parts.append(f"Required skills: {', '.join(required_skills)}")
    if preferred_skills:
        parts.append(f"Preferred skills: {', '.join(preferred_skills)}")
    if responsibilities:
        parts.append(f"Responsibilities: {', '.join(responsibilities)}")
    if location:
        parts.append(f"Location: {location}")
    if candidate_instructions:
        parts.append(f"Candidate instructions: {candidate_instructions}")
    parts.append(f"\nSection type: {section_type}")
    if section_config:
        parts.append(f"Section config: {json.dumps(section_config)}")
    return "\n".join(parts)


# ── Public API ─────────────────────────────────────────────────────────────

async def generate_questions(
    *,
    job_title: str,
    job_description: Optional[str],
    seniority: Optional[str],
    required_skills: Optional[list],
    preferred_skills: Optional[list],
    responsibilities: Optional[list],
    location: Optional[str],
    candidate_instructions: Optional[str],
    section_type: str,
    section_config: Optional[dict],
    num_questions: int = 5,
) -> List[dict]:
    """Call Groq to generate draft interview questions.

    Returns a list of dicts each containing title, competency, text,
    eval_criteria, and config.  Raises on network / parse errors — callers
    should handle gracefully.
    """
    api_key = settings.GROQ_API_KEY
    model = settings.GROQ_MODEL or "llama-3.3-70b-versatile"

    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not configured in backend settings")

    client = Groq(api_key=api_key)

    user_prompt = _build_user_prompt(
        job_title=job_title,
        job_description=job_description,
        seniority=seniority,
        required_skills=required_skills,
        preferred_skills=preferred_skills,
        responsibilities=responsibilities,
        location=location,
        candidate_instructions=candidate_instructions,
        section_type=section_type,
        section_config=section_config,
        num_questions=num_questions,
    )

    logger.info("[QuestionGen] Calling Groq model=%s questions=%d section=%s",
                model, num_questions, section_type)

    chat_completion = client.chat.completions.create(
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPTS.get(section_type, _SYSTEM_PROMPTS["VERBAL"])},
            {"role": "user", "content": user_prompt},
        ],
        model=model,
        temperature=0.7,
        max_tokens=4096,
        response_format={"type": "json_object"},
    )

    raw = chat_completion.choices[0].message.content
    parsed = json.loads(raw)

    # The model may wrap the array in an object like {"questions": [...]}.
    # For num_questions=1 specifically (used by regenerate_question), Groq
    # sometimes returns a single flat question object instead — e.g.
    # {"title": ..., "text": ...} rather than {"questions": [{...}]}.
    # Normalize that shape here too so every caller still gets the same
    # List[dict] contract, without special-casing the caller.
    if isinstance(parsed, dict):
        for key in ("questions", "items", "data"):
            if key in parsed and isinstance(parsed[key], list):
                parsed = parsed[key]
                break
        else:
            if "title" in parsed and "text" in parsed:
                parsed = [parsed]
            else:
                raise ValueError(f"Unexpected JSON shape from Groq: {list(parsed.keys())}")

    if not isinstance(parsed, list):
        raise ValueError(f"Expected a JSON array, got {type(parsed).__name__}")

    # Normalize each item
    questions = []
    for item in parsed:
        questions.append({
            "title": str(item.get("title", "Untitled")),
            "competency": item.get("competency"),
            "text": str(item.get("text", "")),
            "eval_criteria": item.get("eval_criteria"),
            "config": item.get("config"),
        })

    logger.info("[QuestionGen] Received %d questions from Groq", len(questions))
    return questions
