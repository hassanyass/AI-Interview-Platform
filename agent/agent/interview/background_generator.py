"""Verbal Background subsection: CV-grounded question generation.

docs/verbal-background-subsection-plan.md §1/§2/§10. One structured Groq
call at session bootstrap turns the candidate's parsed CV profile into N
short questions, returned as ordinary `Question` objects tagged
source="BACKGROUND" so main.py can prepend them to the VERBAL section and
the controller walks them with the machinery it already has (verbatim first
turn, follow-up cap, forced advance, records).

Mirrors question_generator.py's shape (prompt -> llm.generate_structured ->
post-fix ids/source). Deliberately has NO fallback question set: the plan
rules that when there is nothing usable, background is skipped silently and
the interview proceeds to the discussion -- it never blocks.
"""
import json
import logging
import re
import uuid
from typing import List, Optional

from pydantic import BaseModel, Field

from agent.interview.input_limits import MAX_JOB_DESCRIPTION_CHARS, MAX_PROFILE_CHARS, truncate_prompt_text
from agent.interview.models import Question
from agent.llm.prompts import BACKGROUND_GENERATION_PROMPT
from agent.llm.provider import LLMProvider

logger = logging.getLogger(__name__)

BACKGROUND_QUESTION_COUNT_DEFAULT = 3
BACKGROUND_QUESTION_COUNT_MAX = 6  # keep in step with backend SectionConfig

# The profile keys that carry something a question can be grounded in. A
# profile with none of these (e.g. extraction failed, or only name/email)
# gives the model nothing but licence to invent -- so we don't call it.
_GROUNDING_KEYS = (
    "professional_title", "education", "skills", "programming_languages",
    "frameworks", "projects", "years_of_experience",
)


class BackgroundEvalBands(BaseModel):
    excellent: str = ""
    good: str = ""
    adequate: str = ""
    poor: str = ""


class BackgroundQuestionDraft(BaseModel):
    title: str
    competency: str
    text: str
    eval_criteria: BackgroundEvalBands = Field(default_factory=BackgroundEvalBands)


class BackgroundQuestionSet(BaseModel):
    questions: List[BackgroundQuestionDraft]


def profile_is_groundable(candidate_profile: Optional[dict]) -> bool:
    """True when the profile has at least one non-empty CV-derived field."""
    profile = candidate_profile or {}
    for key in _GROUNDING_KEYS:
        value = profile.get(key)
        if value in (None, "", [], {}, 0):
            continue
        return True
    return False


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")
    return slug or "background"


def draft_to_question(draft: BackgroundQuestionDraft, level: str, index: int) -> Question:
    return Question(
        id=f"bg-{index + 1}-{uuid.uuid4().hex[:10]}",
        title=draft.title.strip() or f"Background question {index + 1}",
        problem_statement=draft.text.strip(),
        difficulty=level,
        # "background:<topic>" -- the plan's tagging convention, so results
        # and evaluators can tell these apart from HR competencies at a glance.
        competency=f"background:{_slug(draft.competency)}",
        expected_concepts=[], hints=[], follow_up_topics=[],
        time_budget_minutes=0, coding_required=False,
        # Same band shape a VERBAL HR question carries, so the evaluators'
        # question_eval_criteria handling needs no special case.
        eval_criteria=draft.eval_criteria.model_dump(),
        source="BACKGROUND",
    )


async def generate_background_questions(
    llm: LLMProvider,
    role: str,
    level: str,
    language: str,
    job_description: Optional[str],
    candidate_profile: dict,
    count: Optional[int] = None,
) -> List[Question]:
    """Generate up to `count` background questions from the CV profile.

    Returns [] (never raises) when the profile has nothing to ground on, the
    model fails, or it returns nothing usable -- the caller then simply has
    no background subsection for this session.
    """
    count = max(1, min(int(count or BACKGROUND_QUESTION_COUNT_DEFAULT), BACKGROUND_QUESTION_COUNT_MAX))
    if not profile_is_groundable(candidate_profile):
        logger.info("[BG-GEN] Skipped: candidate profile has no CV-derived fields to ground on")
        return []

    prompt = BACKGROUND_GENERATION_PROMPT.format(
        count=count,
        role=truncate_prompt_text(role, 240),
        level=level,
        language=language,
        job_description=truncate_prompt_text(job_description, MAX_JOB_DESCRIPTION_CHARS) or "No job description provided.",
        candidate_profile=truncate_prompt_text(json.dumps(candidate_profile or {}, ensure_ascii=False), MAX_PROFILE_CHARS),
    )
    try:
        result = await llm.generate_structured(
            system_prompt=prompt,
            messages=[{"role": "user", "content": f"Write the {count} background questions now."}],
            response_model=BackgroundQuestionSet,
        )
    except Exception as error:  # noqa: BLE001 -- by design: never block the interview
        logger.exception("[BG-GEN] Generation FAILED, background subsection skipped: %s", error)
        return []

    questions: List[Question] = []
    for draft in result.questions:
        if not (draft.text or "").strip():
            continue
        questions.append(draft_to_question(draft, level, len(questions)))
        if len(questions) >= count:
            break
    if not questions:
        logger.warning("[BG-GEN] Model returned no usable questions; background subsection skipped")
    else:
        logger.info("[BG-GEN] Generated %d background question(s): %s", len(questions), [q.title for q in questions])
    return questions
