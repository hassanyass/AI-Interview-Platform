"""
AI Invitation Message Generation Service.

Uses the official Groq Python SDK, reading GROQ_API_KEY and GROQ_MODEL
from the existing backend.core.config.settings -- same independent-of-
agent-code pattern as question_generator.py and evaluation_generator.py.

Built 2026-09-03 for CandidateAccess.tsx's invitation email composer: a
regeneratable draft subject/body tailored to the job, which HR can then
edit freely before (eventually) sending. Actually sending email is
explicitly out of scope for this pass -- see docs/CURRENT_DECISIONS.md's
P1 (email provider, still unresolved/deferred) -- this service only ever
produces text; it never sends anything.
"""
import json
import logging
from typing import Optional

from backend.providers.factory import get_llm
from backend.providers.llm.base import LLMProvider

from backend.core.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are writing a short, warm, professional interview-invitation email on
behalf of an HR team, for a candidate about to be invited to an AI-driven
voice interview.

Return a single JSON object with exactly two keys:
- "subject": a concise, specific email subject line (no "Re:", no
  placeholders left unfilled)
- "body": the email body as plain text (no HTML). Use a real, generic
  greeting ("Hi there," or similar) since this may be sent to more than
  one candidate at once and the tool sending it does not personalize
  per-recipient. Mention the role by name, that this is a voice/AI
  interview they'll complete online, roughly how long it takes if a
  duration is given, and a warm, encouraging closing line. Do NOT invent
  a specific link, date, time, or sender name -- the real link and
  sender identity are added separately by the tool that actually sends
  this. Keep it to 3-5 short paragraphs, no bullet lists, no markdown.

Return ONLY the JSON object, no markdown fences, no commentary.
""".strip()


async def generate_invitation_message(
    *,
    job_title: str,
    job_description: Optional[str],
    seniority: Optional[str],
    duration_minutes: Optional[int],
    llm: LLMProvider | None = None,
) -> dict:
    """Call the LLM provider to draft an invitation email subject + body for this job.
    Returns {"subject": str, "body": str}. Raises on network/parse errors
    -- this is an HR-triggered, on-demand action (the "Regenerate"
    button), so the caller should surface a real error rather than
    silently swallow it."""
    llm = llm or get_llm()
    model = settings.GROQ_MODEL
    context = {
        "job_title": job_title,
        "job_description": job_description,
        "seniority": seniority,
        "duration_minutes": duration_minutes,
    }

    logger.info("[InvitationMessageGen] Calling LLM model=%s job=%s", model, job_title)

    raw = await llm.complete_json(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ],
        model=model,
        temperature=0.7,
        max_tokens=1024,
    )
    parsed = json.loads(raw)
    return {
        "subject": str(parsed.get("subject") or f"You're invited to interview for {job_title}"),
        "body": str(parsed.get("body") or ""),
    }
