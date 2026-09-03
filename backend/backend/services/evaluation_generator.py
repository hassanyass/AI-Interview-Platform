"""
AI Evaluation Regeneration Service.

Uses the official Groq Python SDK, reading GROQ_API_KEY and GROQ_MODEL
from the existing backend.core.config.settings — same pattern as
question_generator.py (a completely new code path; it does NOT import
from or depend on agent/agent/* in any way).

Built 2026-09-03 (see docs/CURRENT_DECISIONS.md's "Evaluation
regeneration for placeholder sessions" entry) to let HR regenerate a real
evaluation for a session stuck on the generic placeholder
(_ensure_evaluation_placeholder in api/endpoints/internal.py). An agent
worker only exists transiently per live interview job — there's no idle
agent process to hand this to after the fact — so the backend needs its
own path, following the same precedent question_generator.py already
established for admin-side AI generation.

The prompt below is a direct backend-side port of
agent/agent/llm/prompts.py's EVALUATOR_PROMPT and
agent/agent/interview/controller.py's generate_final_evaluation() — same
evidence shape, same instructions — adapted to build that evidence from
durable DB rows (InterviewMessage/InterviewCheckpoint/InterviewQuestion/
AssessmentCriterion, via api/endpoints/admin.py's regenerate_evaluation)
instead of the agent's live in-memory context, since this always runs
after the interview has already ended.
"""
import asyncio
import json
import logging
from typing import Optional

from groq import Groq

from backend.core.config import settings
from backend.schemas.persistence import CriterionScoreSubmit

logger = logging.getLogger(__name__)

EVALUATOR_SYSTEM_PROMPT = """
You are an expert technical interviewer producing the final, structured evaluation of a completed interview.
You MUST provide concrete evidence (a quote or specific reasoning from the transcript/submission) for every score -- never invent evidence that isn't in the supplied material, and leave a score null rather than guess when evidence is missing.

Return a single JSON object with exactly these keys:
- "overall_score": integer 1-5, or null if there isn't enough evidence for an overall judgment
- "recommendation": exactly one of "Hire", "Consider / Mixed", "No Hire"
- "evidence_sufficiency": float 0.0-1.0 -- the fraction of criteria below, plus your overall judgment, that you could actually ground in real evidence from the transcript/submission -- NOT a quality score. A candidate who was genuinely weak but gave plenty to go on should still score HIGH evidence_sufficiency. A candidate who didn't speak or didn't attempt questions should score LOW evidence_sufficiency regardless of what overall_score that produces. Low score + low evidence_sufficiency means "insufficient data, not a fair assessment"; low score + high evidence_sufficiency means "assessed and found weak."
- "summary": a concise overall summary string
- "criterion_scores": an array with exactly one entry per item in the supplied `criteria` list -- do NOT invent a criterion that isn't listed, do NOT omit one that is. Each entry: {"criterion_key": copied verbatim from the matching `criteria` entry, "score": 1-5 or null, "overview": what was observed for this criterion (if score is null because there's no evidence, say so plainly -- never phrase "no evidence" and "genuinely weak" the same way), "strengths": [specific strengths, empty if none], "improvements": [specific gaps, empty if none], "evidence_reference": a question_id or short transcript quote this score is actually grounded in, or null}
- "detailed_overview": a fuller narrative synthesis string

`criteria` entries have `key`, `label`, `kind` ("behavioral" or "content"), and `guidance_text`. `guidance_text` for a "behavioral" criterion describes a trait observable across the WHOLE transcript, not tied to any one question -- judge it holistically. If `criteria` is empty (a legacy session or a job with nothing configured), return an empty criterion_scores array -- still fill in every other field from the transcript/question_records/technical_submission; an empty criterion_scores array is not an error.

`question_eval_criteria` maps question_id -> the HR-authored grading rubric for that specific question (VERBAL: excellent/good/adequate/poor bands; CODING: time_complexity/space_complexity/edge_cases/rubric, score technical_submission against these with PARTIAL CREDIT for a right approach that's incomplete or imperfect, never a binary pass/fail; MCQ: question_records already carries the deterministic right/wrong result). Feed what you learn from it into overall_score/summary/detailed_overview, not into a criterion_scores entry, unless a "content"-kind criterion in `criteria` explicitly names that exact question.

This session may have ended early (a TERMINATED/incomplete interview, not every question necessarily reached) -- evaluate honestly from whatever evidence exists. A short or partial transcript is not itself an error; reflect it in evidence_sufficiency rather than inventing scores to fill the gap.

Return ONLY the JSON object, no markdown fences, no commentary.
""".strip()


async def generate_evaluation(
    *,
    role: str,
    level: str,
    transcript: list,
    question_records: list,
    technical_submission: dict,
    question_eval_criteria: dict,
    criteria: list,
) -> dict:
    """Call Groq to produce a structured evaluation from the given
    evidence. Returns a dict with overall_score/recommendation/
    evidence_sufficiency/summary/detailed_overview/criterion_scores (the
    last as a list of CriterionScoreSubmit instances, ready for
    api/endpoints/internal.py's _upsert_evaluation). Raises on network/
    parse errors -- this is an HR-triggered, on-demand action, so the
    caller should surface a real error rather than swallow it the way a
    live interview's degrade-gracefully paths must."""
    api_key = settings.GROQ_API_KEY
    model = settings.GROQ_MODEL or "llama-3.3-70b-versatile"
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not configured in backend settings")

    client = Groq(api_key=api_key)
    evidence = {
        "role": role,
        "level": level,
        "technical_submission": technical_submission,
        "question_records": question_records,
        "question_eval_criteria": question_eval_criteria,
        "criteria": criteria,
        "transcript": transcript[-40:],
    }

    logger.info(
        "[EvaluationGen] Calling Groq model=%s transcript_turns=%d criteria=%d",
        model, len(transcript), len(criteria),
    )

    def _call():
        return client.chat.completions.create(
            messages=[
                {"role": "system", "content": EVALUATOR_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(evidence, ensure_ascii=False)},
            ],
            model=model,
            temperature=0.3,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )

    # Off the event loop -- unlike question_generator.py's admin-authoring
    # call (a single, infrequent action against a short prompt), this can
    # run over a full transcript and must not freeze the backend for
    # every other request while it's in flight.
    chat_completion = await asyncio.to_thread(_call)
    raw = chat_completion.choices[0].message.content
    parsed = json.loads(raw)

    criterion_scores = [
        CriterionScoreSubmit(
            criterion_key=str(cs["criterion_key"]),
            score=cs.get("score"),
            overview=cs.get("overview"),
            strengths=[str(s) for s in (cs.get("strengths") or [])],
            improvements=[str(s) for s in (cs.get("improvements") or [])],
            evidence_reference=cs.get("evidence_reference"),
        )
        for cs in (parsed.get("criterion_scores") or [])
        if cs.get("criterion_key")
    ]

    return {
        "overall_score": parsed.get("overall_score"),
        "recommendation": parsed.get("recommendation"),
        "evidence_sufficiency": parsed.get("evidence_sufficiency"),
        "summary": parsed.get("summary") or "",
        "detailed_overview": parsed.get("detailed_overview") or "",
        "criterion_scores": criterion_scores,
    }
