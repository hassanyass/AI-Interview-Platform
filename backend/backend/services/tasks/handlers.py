"""What each task kind actually does (H2-F).

These are the bodies the four admin endpoints used to run inline, moved
here unchanged apart from where their inputs come from (a JSON payload
instead of path/query parameters) and what they return (a JSON result
instead of a response model). The endpoint still does its own 404/409
validation before queueing, so an admin gets an immediate error for a
missing section or a PUBLISHED job; a handler re-loads the row because
minutes may pass between queueing and running, and it may be gone by then.

The generators are called through their module (``question_generator.
generate_questions(...)``), not through a bound name, so a test patching
``backend.services.question_generator.generate_questions`` still
intercepts the call -- exactly as when this code lived in admin.py.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from backend.core.errors import Conflict, NotFound, UpstreamError, ValidationFailed
from backend.models.interview import (
    InterviewDefinition,
    InterviewQuestion,
    InterviewSection,
    InterviewSession,
)
from backend.schemas.admin import validate_question_config
from backend.services import evaluation_generator, invitation_message_generator, question_generator
from backend.services.evaluations.upsert import resolve_criteria_for_job, upsert_evaluation
from backend.services.results.candidate_result import (
    get_live_question_records_and_submission,
    get_live_transcript,
)

logger = logging.getLogger(__name__)

GENERATE_QUESTIONS = "generate_questions"
REGENERATE_QUESTION = "regenerate_question"
GENERATE_INVITATION_MESSAGE = "generate_invitation_message"
REGENERATE_EVALUATION = "regenerate_evaluation"


def _job_context(job) -> dict[str, Any]:
    """The job fields both generation handlers pass to the LLM."""
    return {
        "job_title": job.title,
        "job_description": job.description,
        "seniority": job.seniority,
        "required_skills": job.required_skills,
        "preferred_skills": job.preferred_skills,
        "responsibilities": job.responsibilities,
        "location": job.location,
        "candidate_instructions": job.instructions,
    }


async def generate_questions(db: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    section_id = UUID(payload["section_id"])
    num_questions = payload["num_questions"]

    section = (
        await db.execute(
            select(InterviewSection)
            .options(selectinload(InterviewSection.definition).selectinload(InterviewDefinition.job))
            .where(InterviewSection.id == section_id)
        )
    ).scalar_one_or_none()
    if not section:
        raise NotFound("Section not found")
    job = section.definition.job
    if job.status != "DRAFT":
        raise Conflict(f"Job is {job.status}; edits are only allowed while DRAFT")

    generated = await question_generator.generate_questions(
        **_job_context(job),
        section_type=section.section_type,
        section_config=section.config,
        num_questions=num_questions,
    )

    # Determine starting order_index
    result = await db.execute(
        select(InterviewQuestion)
        .where(InterviewQuestion.section_id == section_id)
        .order_by(InterviewQuestion.order_index.desc())
    )
    last = result.scalars().first()
    start_idx = (last.order_index + 1) if last else 0

    created_questions = []
    for i, q in enumerate(generated):
        # Validate config from AI output against section type
        try:
            validated_config = validate_question_config(section.section_type, q.get("config"))
        except ValueError as e:
            raise ValidationFailed(f"AI-generated question {i+1} has invalid config: {str(e)}") from e

        question = InterviewQuestion(
            section_id=section_id,
            order_index=start_idx + i,
            title=q["title"],
            competency=q.get("competency"),
            text=q["text"],
            eval_criteria=q.get("eval_criteria"),
            config=validated_config,
        )
        db.add(question)
        created_questions.append(question)

    # Ids captured before the commit: committing expires the instances, and
    # reading an attribute back would lazy-load outside the async context
    # (MissingGreenlet -- the same trap H2-B hit in resume_ingest).
    await db.flush()
    created_ids = [str(q.id) for q in created_questions]
    await db.commit()
    return {
        "section_id": str(section_id),
        "created_question_ids": created_ids,
        "count": len(created_ids),
    }


async def regenerate_question(db: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    question_id = UUID(payload["question_id"])

    question = (
        await db.execute(
            select(InterviewQuestion)
            .options(
                selectinload(InterviewQuestion.section)
                .selectinload(InterviewSection.definition)
                .selectinload(InterviewDefinition.job)
            )
            .where(InterviewQuestion.id == question_id)
        )
    ).scalar_one_or_none()
    if not question:
        raise NotFound("Question not found")
    job = question.section.definition.job
    if job.status != "DRAFT":
        raise Conflict(f"Job is {job.status}; edits are only allowed while DRAFT")

    generated = await question_generator.generate_questions(
        **_job_context(job),
        section_type=question.section.section_type,
        section_config=question.section.config,
        num_questions=1,
    )
    if not generated:
        raise UpstreamError("AI generation returned no results", code="llm_empty_result")

    new_q = generated[0]
    question.title = new_q["title"]
    question.competency = new_q.get("competency")
    question.text = new_q["text"]
    question.eval_criteria = new_q.get("eval_criteria")

    # Validate config from AI output against section type
    try:
        question.config = validate_question_config(question.section.section_type, new_q.get("config"))
    except ValueError as e:
        raise ValidationFailed(f"AI-regenerated question has invalid config: {str(e)}") from e

    await db.commit()
    return {"question_id": str(question_id)}


async def generate_invitation_message(db: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    """Purely generative: nothing is persisted anywhere else, so the draft
    lives in the task's ``result`` and that is where the composer reads it.
    Before H2-F a browser timeout lost it outright."""
    definition_id = UUID(payload["definition_id"])

    definition = (
        await db.execute(
            select(InterviewDefinition)
            .options(selectinload(InterviewDefinition.job))
            .where(InterviewDefinition.id == definition_id)
        )
    ).scalar_one_or_none()
    if not definition:
        raise NotFound("InterviewDefinition not found")

    try:
        generated = await invitation_message_generator.generate_invitation_message(
            job_title=definition.job.title,
            job_description=definition.job.description,
            seniority=definition.job.seniority,
            duration_minutes=definition.duration_minutes,
        )
    except Exception as e:  # noqa: BLE001 -- any provider failure becomes one typed error for HR
        logger.exception("Failed to generate invitation message for definition %s", definition_id)
        raise UpstreamError(
            "Failed to generate an invitation message. Check the backend logs and try again.",
            code="llm_generation_failed",
        ) from e

    return {"subject": generated["subject"], "body": generated["body"]}


async def regenerate_evaluation(db: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    """See the endpoint's own docstring for why TERMINATED sessions are
    eligible (CURRENT_DECISIONS.md, 2026-09-03). Unchanged here: the only
    difference is that HR no longer holds an HTTP connection open for it."""
    session_id = UUID(payload["session_id"])

    session = (
        await db.execute(
            select(InterviewSession)
            .options(selectinload(InterviewSession.profile))
            .where(InterviewSession.id == session_id)
        )
    ).scalar_one_or_none()
    if not session:
        raise NotFound("Interview session not found.")
    if session.status not in ("COMPLETED", "TERMINATED"):
        raise Conflict("Cannot generate an evaluation for a session that hasn't ended yet.")

    transcript = await get_live_transcript(db, session_id)
    raw_question_records, technical_submission = await get_live_question_records_and_submission(db, session_id)

    question_uuids = []
    for r in raw_question_records:
        try:
            question_uuids.append(UUID(r["question_id"]))
        except (KeyError, ValueError, TypeError):
            continue
    question_eval_criteria = {}
    if question_uuids:
        q_result = await db.execute(
            select(InterviewQuestion).where(InterviewQuestion.id.in_(question_uuids))
        )
        question_eval_criteria = {
            str(q.id): q.eval_criteria for q in q_result.scalars().all() if q.eval_criteria is not None
        }

    resolved_criteria = await resolve_criteria_for_job(db, session.job_id)
    criteria = [
        {
            "key": c.key,
            "label": c.label,
            "kind": c.kind,
            "guidance_text": c.guidance_text,
            "section_id": str(c.section_id) if c.section_id else None,
        }
        for c in resolved_criteria
    ]

    # Verbal Background subsection (plan §2 "Evaluation"): the same profile
    # dict /load hands the agent, so both evaluators judge cv_alignment
    # against identical evidence.
    profile = session.profile
    candidate_profile = {
        "full_name": profile.full_name,
        "email": profile.email,
        "education": profile.education,
        "years_of_experience": profile.years_of_experience,
        "skills": profile.skills,
        "programming_languages": profile.programming_languages,
        "frameworks": profile.frameworks,
        "projects": profile.projects,
        "professional_title": profile.professional_title,
        "recommended_level": profile.recommended_level,
        "confirmed_level": profile.confirmed_level,
    } if profile else {}

    try:
        generated = await evaluation_generator.generate_evaluation(
            role=session.role or "",
            level=session.level or "",
            transcript=transcript,
            question_records=raw_question_records,
            technical_submission=technical_submission,
            question_eval_criteria=question_eval_criteria,
            criteria=criteria,
            candidate_profile=candidate_profile,
        )
    except Exception as e:  # noqa: BLE001 -- any provider failure becomes one typed error for HR
        logger.exception("Failed to regenerate evaluation for session %s", session_id)
        raise UpstreamError(
            "Failed to generate a new evaluation. Check the backend logs and try again.",
            code="llm_generation_failed",
        ) from e

    await upsert_evaluation(
        db, session,
        overall_score=generated["overall_score"],
        recommendation=generated["recommendation"],
        evidence_sufficiency=generated["evidence_sufficiency"],
        summary=generated["summary"],
        detailed_overview=generated["detailed_overview"],
        criterion_scores=generated["criterion_scores"],
    )
    await db.commit()
    # The result page re-reads GET /admin/interviews/{id}/result, which is
    # the single source for that view; no need to duplicate it here.
    return {"session_id": str(session_id)}
