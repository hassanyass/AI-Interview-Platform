"""
One-off backfill: normalized Evaluation/Score rows from already-saved
final_result JSONB (Phase A of the evaluation-pipeline investigation —
see the session that diagnosed this).

Why this is needed: build_final_result() (agent/agent/interview/
persistence.py) has always embedded the LLM-generated evaluation into
InterviewSession.final_result['evaluation'] whenever a session completes.
Separately, POST /internal/interviews/{id}/evaluation (added later, Phase
8C) writes that same data into the NORMALIZED evaluations/scores tables —
what the HR dashboard's GET /admin/interviews/{id}/result actually reads.
Sessions completed before that second write path existed in the deployed
agent have real evaluation data sitting in final_result but no matching
`evaluations` row, so the dashboard reports "not evaluated yet" even
though nothing needs to be regenerated -- it just needs to be copied over.

Safe to re-run: skips any session that already has an Evaluation row, and
skips any session with no usable evaluation data in final_result (nothing
to backfill, not an error). Does not touch or require the agent/LLM at
all -- pure DB-to-DB copy.

Usage:
    python scripts/backfill_evaluations.py            # do it
    python scripts/backfill_evaluations.py --dry-run   # report only, no writes
"""
import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, "./backend")
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select

from backend.db.session import engine  # reuses the same engine (and Windows DNS workaround) as the app
import backend.models.profile  # noqa: F401 -- must be imported before any query compiles so
# SQLAlchemy's lazy mapper configuration can resolve InterviewSession/JobApplication's
# relationship("CandidateProfile", ...) string reference (2026-09-01 fix: this script
# previously only imported backend.models.interview, which left CandidateProfile
# unregistered and made the very first select() raise InvalidRequestError).
from backend.models.interview import InterviewSession, Evaluation, Score, AssessmentCriterion


async def _resolve_criteria_for_job(db: AsyncSession, job_id):
    """Mirrors internal.py's _resolve_criteria_for_job exactly, so a
    backfilled Score's criterion_id resolves the same way a live
    POST /evaluation submission would have resolved it at the time."""
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


async def backfill(dry_run: bool = False):
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    backfilled = 0
    already_had_row = 0
    no_evaluation_data = 0
    errored = 0

    async with async_session() as db:
        result = await db.execute(
            select(InterviewSession).where(InterviewSession.status == "COMPLETED")
        )
        sessions = list(result.scalars().all())
        print(f"Found {len(sessions)} COMPLETED session(s) to check.\n")

        for session in sessions:
            final_result = session.final_result or {}
            evaluation_data = final_result.get("evaluation")
            evaluation_status = final_result.get("evaluation_status")

            if not evaluation_data or evaluation_status != "COMPLETED":
                # Nothing saved to copy — either the session predates this
                # embedding, or generate_final_evaluation() itself failed
                # for it (evaluation_status == "FAILED"). Not this script's
                # job to regenerate that; it only copies what already exists.
                no_evaluation_data += 1
                continue

            existing = await db.execute(
                select(Evaluation).where(Evaluation.session_id == session.id)
            )
            if existing.scalar_one_or_none() is not None:
                already_had_row += 1
                continue

            print(f"Backfilling session {session.id} ({session.role}, {session.level})...")
            if dry_run:
                backfilled += 1
                continue

            try:
                evaluation = Evaluation(
                    session_id=session.id,
                    overall_score=evaluation_data.get("overall_score"),
                    recommendation=evaluation_data.get("recommendation"),
                    evidence_sufficiency=evaluation_data.get("evidence_sufficiency"),
                    summary=evaluation_data.get("summary"),
                    detailed_overview=evaluation_data.get("detailed_overview"),
                )
                db.add(evaluation)
                await db.flush()  # assigns evaluation.id before Score rows reference it

                criterion_scores = evaluation_data.get("criterion_scores") or []
                if criterion_scores:
                    resolved = await _resolve_criteria_for_job(db, session.job_id)
                    key_to_id = {c.key: c.id for c in resolved}
                    for cs in criterion_scores:
                        db.add(Score(
                            evaluation_id=evaluation.id,
                            criterion_id=key_to_id.get(cs.get("criterion_key")),
                            criterion_key=cs.get("criterion_key"),
                            score=cs.get("score"),
                            overview=cs.get("overview"),
                            strengths=cs.get("strengths") or [],
                            improvements=cs.get("improvements") or [],
                            evidence_reference=cs.get("evidence_reference"),
                        ))

                await db.commit()
                backfilled += 1
            except Exception as e:
                await db.rollback()
                print(f"  ERROR backfilling session {session.id}: {e}")
                errored += 1

    print("\n--- Summary ---")
    print(f"Backfilled:            {backfilled}{' (dry run — no writes made)' if dry_run else ''}")
    print(f"Already had a row:     {already_had_row}")
    print(f"No evaluation to copy: {no_evaluation_data}")
    print(f"Errored:               {errored}")


if __name__ == "__main__":
    asyncio.run(backfill(dry_run="--dry-run" in sys.argv))
