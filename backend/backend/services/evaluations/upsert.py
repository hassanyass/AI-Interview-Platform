"""Normalized Evaluation + Score persistence (Phase 8C), shared by the
agent's submission (internal.submit_evaluation) and HR-triggered
regeneration (admin.regenerate_evaluation). Moved verbatim from
api/endpoints/internal.py in H2-A2."""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.interview import AssessmentCriterion, Evaluation, InterviewSession, Score

logger = logging.getLogger(__name__)


async def resolve_criteria_for_job(db: AsyncSession, job_id) -> list[AssessmentCriterion]:
    """Phase 8C. job_id-scoped enabled rows if any exist for this job;
    otherwise falls back to the enabled TEMPLATE tier (job_id/section_id both
    NULL) as this job's default set. That fallback is a deliberate, flagged
    interim behavior (no 8E authoring UI exists yet to create job-scoped
    rows) — see AssessmentCriterion's docstring in models/interview.py.
    Returns [] entirely for job_id=None (a legacy, non-B2B session)."""
    if job_id is None:
        return []
    result = await db.execute(
        select(AssessmentCriterion).where(
            AssessmentCriterion.job_id == job_id,
            AssessmentCriterion.enabled.is_(True),
        )
    )
    job_criteria = list(result.scalars().all())
    if job_criteria:
        return job_criteria

    template_result = await db.execute(
        select(AssessmentCriterion).where(
            AssessmentCriterion.job_id.is_(None),
            AssessmentCriterion.section_id.is_(None),
            AssessmentCriterion.enabled.is_(True),
        )
    )
    return list(template_result.scalars().all())


async def upsert_evaluation(
    db: AsyncSession,
    session: InterviewSession,
    *,
    overall_score,
    recommendation,
    evidence_sufficiency,
    summary,
    detailed_overview,
    criterion_scores,
) -> UUID:
    """Shared upsert for the normalized Evaluation + Score rows -- the one
    place both the agent's own submission (submit_evaluation below) and
    the HR-triggered regeneration (admin.py's regenerate_evaluation, added
    2026-09-03 -- see CURRENT_DECISIONS.md's "Evaluation regeneration for
    placeholder sessions" entry) write a real evaluation, so the
    weighted-score formula and Score-row handling exist in exactly one
    place. Idempotent on session_id -- a second call (retry, or an
    explicit regeneration) replaces rather than accumulates prior scores.
    Marks is_placeholder=False unconditionally: reaching this function at
    all means a real evaluation (initial or regenerated) was produced, not
    the generic fallback. `criterion_scores` items need only
    `.criterion_key`/`.score`/`.overview`/`.strengths`/`.improvements`/
    `.evidence_reference` attributes -- CriterionScoreSubmit instances
    from either caller satisfy this. Caller commits; returns the
    evaluation id (captured before commit -- see the comment below on
    why)."""
    result = await db.execute(
        select(Evaluation).where(Evaluation.session_id == session.id)
    )
    evaluation = result.scalar_one_or_none()

    if evaluation is None:
        evaluation = Evaluation(session_id=session.id)
        db.add(evaluation)
        await db.flush()  # assigns evaluation.id before Score rows reference it
    else:
        await db.execute(delete(Score).where(Score.evaluation_id == evaluation.id))

    evaluation.overall_score = overall_score
    evaluation.recommendation = recommendation
    evaluation.evidence_sufficiency = evidence_sufficiency
    evaluation.summary = summary
    evaluation.detailed_overview = detailed_overview
    evaluation.is_placeholder = False

    # Scoring-mechanism upgrade (2026-09-01, signed-off frozen-file touch,
    # see CURRENT_DECISIONS.md's "Scoring mechanism upgrade" entry): a
    # real, code-computed weighted aggregate of criterion_scores, using
    # each enabled criterion's AssessmentCriterion.weight. Deliberately
    # separate from overall_score (the LLM's own independent holistic
    # judgment, untouched by this change) -- computed once here, using the
    # weights in effect at submission time, then frozen on the Evaluation
    # row, same "recorded fact about this evaluation event" precedent as
    # overall_score/evidence_sufficiency.
    #
    # Formula (plan item 3): S = criteria that are both enabled for this
    # job AND have a non-null score in this submission. weighted_score =
    # sum(weight_i * score_i for i in S) / sum(weight_i for i in S).
    # Dividing by the sum of INCLUDED weights (not a fixed total) IS the
    # renormalization -- a disabled or null-scored criterion's weight is
    # simply absent from that denominator, so the remaining criteria's
    # shares grow proportionally on their own. None (not 0) when S is
    # empty -- nothing to average is "insufficient evidence", not "scored
    # zero", matching overall_score's own null convention.
    weighted_sum = 0.0
    total_weight = 0
    if criterion_scores:
        # Best-effort criterion_id resolution, scoped to this exact job's
        # resolved criteria set (not a bare global key lookup — a key is
        # only unique within one job/template scope, not across all of them).
        # resolve_criteria_for_job already filters to enabled.is_(True), so
        # a criterion disabled since the question was asked (or any key not
        # in this job's resolved set) is naturally excluded from both the
        # criterion_id lookup and the weighted-score computation below.
        resolved = await resolve_criteria_for_job(db, session.job_id)
        key_to_id = {c.key: c.id for c in resolved}
        key_to_weight = {c.key: c.weight for c in resolved}
        for cs in criterion_scores:
            db.add(Score(
                evaluation_id=evaluation.id,
                criterion_id=key_to_id.get(cs.criterion_key),
                criterion_key=cs.criterion_key,
                score=cs.score,
                overview=cs.overview,
                strengths=cs.strengths,
                improvements=cs.improvements,
                evidence_reference=cs.evidence_reference,
            ))
            weight = key_to_weight.get(cs.criterion_key)
            if weight is not None and cs.score is not None:
                weighted_sum += weight * cs.score
                total_weight += weight

    evaluation.weighted_score = (weighted_sum / total_weight) if total_weight > 0 else None

    # Audit fix (2026-08-27) pattern, same bug class: db.commit() expires the
    # ORM instance's attributes by default, so reading evaluation.id after
    # commit forces a lazy-refresh outside an async-safe context ->
    # sqlalchemy.exc.MissingGreenlet. Capture the value BEFORE commit, return
    # that local, never the (now-expired) ORM attribute.
    return evaluation.id
