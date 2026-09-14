"""One-off: seed 3 demo jobs plus fabricated COMPLETED candidate results,
for the free-tier 2-week demo (docs/deployment-guide.md).

  - IT Support Engineer  -- DRAFT, VERBAL+CODING, 2 mock candidates
  - Sales Executive      -- DRAFT, VERBAL+MCQ only, 2 mock candidates
  - AI Engineer          -- PUBLISHED, VERBAL+CODING+MCQ, 1 mock candidate
    (the second real data point is meant to come from an actual live test
    interview taken through the published job, not from this script)

Interview questions are real: generated via the same Groq-backed
backend.services.question_generator.generate_questions the admin UI's own
"Generate Questions" button calls -- not hand-authored placeholders, so
content/shape matches exactly what the app produces normally.

Everything else per mock candidate (transcript, question_records,
technical_submission, Evaluation/Score) is hand-fabricated and flagged
final_result["is_mock"] = True -- surfaced by CandidateResultPage.tsx as
an explicit "this is mock data" note (see admin.py's get_candidate_result
and schemas/admin.py's EvaluationDetailResponse.is_mock_data) instead of
the generic "no recording available" message, so a reviewer never
mistakes fabricated data for a real, lost recording.

Score rows use whichever AssessmentCriterion rows _resolve_criteria_for_
job (internal.py) would actually resolve for these jobs today -- the 8
TEMPLATE rows, since none of the 3 jobs gets custom criteria here -- so a
mock result looks exactly like what a real evaluation of an unconfigured
job would produce.

Safe to re-run: skips creating a job whose title already exists.

Usage:
    python scripts/seed_demo_data.py
"""
import sys
import asyncio
import random
import uuid as uuid_mod
from datetime import datetime, timedelta, timezone

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, "./backend")

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select

from backend.db.session import engine  # reuses the same engine (and Windows DNS workaround) as the app
import backend.models.profile  # noqa: F401 -- must be imported before any query compiles, see backfill_evaluations.py's identical comment
from backend.models.interview import (
    Job, InterviewDefinition, InterviewSection, InterviewQuestion,
    InterviewSession, Evaluation, Score, AssessmentCriterion,
)
from backend.models.profile import CandidateProfile
from backend.services.question_generator import generate_questions


TIME_BUDGET_MINUTES = {"VERBAL": 20, "CODING": 30, "MCQ": 10}
NUM_QUESTIONS = {"VERBAL": 5, "CODING": 3, "MCQ": 5}

JOB_SPECS = [
    {
        "title": "IT Support Engineer",
        "description": "Provide first- and second-line technical support to internal staff, "
                        "keeping laptops, accounts, and internal systems running smoothly.",
        "seniority": "mid",
        "location": "Dubai, UAE",
        "required_skills": ["Windows/Linux administration", "Networking fundamentals", "Ticketing systems", "Active Directory"],
        "preferred_skills": ["PowerShell scripting", "ITIL"],
        "responsibilities": ["Triage and resolve incoming support tickets", "Maintain internal IT documentation", "Support onboarding/offboarding of staff devices"],
        "sections": ["VERBAL", "CODING"],
        "publish": False,
        "candidates": [
            ("Sarah Al-Mansoori", "sarah.almansoori.demo@example.com", "strong"),
            ("Omar Haddad", "omar.haddad.demo@example.com", "weak"),
        ],
    },
    {
        "title": "Sales Executive",
        "description": "Own the full B2B sales cycle for a portfolio of enterprise accounts, "
                        "from prospecting through close.",
        "seniority": "mid",
        "location": "Abu Dhabi, UAE",
        "required_skills": ["B2B sales", "Negotiation", "CRM tools", "Pipeline management"],
        "preferred_skills": ["Telecom or enterprise software sales experience"],
        "responsibilities": ["Own the full sales cycle from lead to close", "Build and maintain client relationships", "Meet or exceed quarterly targets"],
        "sections": ["VERBAL", "MCQ"],
        "publish": False,
        "candidates": [
            ("Layla Nasser", "layla.nasser.demo@example.com", "strong"),
            ("Yusuf Ibrahim", "yusuf.ibrahim.demo@example.com", "weak"),
        ],
    },
    {
        "title": "AI Engineer (Demo)",
        "description": "Design, train, and ship production ML/LLM systems, from prototyping "
                        "through deployment and monitoring.",
        "seniority": "senior",
        "location": "Remote",
        "required_skills": ["Python", "PyTorch or TensorFlow", "LLM fine-tuning", "MLOps"],
        "preferred_skills": ["RAG pipelines", "Vector databases"],
        "responsibilities": ["Design and train ML models", "Deploy and monitor models in production", "Collaborate with product on AI feature scoping"],
        "sections": ["VERBAL", "CODING", "MCQ"],
        "publish": True,
        "candidates": [
            ("Fatima Al-Zahra", "fatima.alzahra.demo@example.com", "strong"),
        ],
    },
]

TEMPLATE_CRITERION_KEYS = [
    "clarity_of_thought", "organization_structure", "communication",
    "confidence_composure", "professionalism", "problem_solving_approach",
    "adaptability_to_feedback", "collaboration_teamwork",
]

STRONG_SUMMARY = (
    "{name} gave clear, well-structured answers throughout, backing claims with concrete "
    "examples and checking in when a question was ambiguous. Handled follow-up probes "
    "and hints constructively rather than becoming defensive."
)
WEAK_SUMMARY = (
    "{name}'s answers were often unstructured and took time to get to the point. Relied "
    "heavily on hints for the more technical questions and struggled to recover cleanly "
    "when redirected."
)


async def _get_template_criteria(db: AsyncSession) -> list[AssessmentCriterion]:
    result = await db.execute(
        select(AssessmentCriterion).where(
            AssessmentCriterion.job_id.is_(None),
            AssessmentCriterion.section_id.is_(None),
            AssessmentCriterion.enabled.is_(True),
        )
    )
    return list(result.scalars().all())


def _fabricate_transcript(questions: list[InterviewQuestion], profile: str, job_title: str) -> list[dict]:
    turns = [{"speaker": "agent", "text": f"Thanks for joining today's interview for the {job_title} role. Let's get started."}]
    for q in questions:
        turns.append({"speaker": "agent", "text": q.text})
        if profile == "strong":
            turns.append({
                "speaker": "candidate",
                "text": f"Sure — for {q.competency or 'this'}, I'd start by breaking it down into the core requirements, "
                        "then walk through a concrete example from a project where I handled something similar, "
                        "checking assumptions as I go.",
            })
        else:
            turns.append({
                "speaker": "candidate",
                "text": "Hmm, let me think... I think the main thing is to just get it working first, "
                        "and I'd probably need to look up the specifics if this came up for real.",
            })
            turns.append({"speaker": "agent", "text": "Could you walk me through your reasoning a bit more concretely?"})
            turns.append({"speaker": "candidate", "text": "Sure — I'd say it depends on the situation, but generally I'd just try a few things and see what works."})
    turns.append({"speaker": "agent", "text": "That's all the questions I have. Thanks for your time today."})
    return turns


def _fabricate_question_records(questions: list[InterviewQuestion], profile: str) -> list[dict]:
    records = []
    for i, q in enumerate(questions):
        if profile == "strong":
            outcome, hints, followups = "COMPLETED", 0, (1 if i == 0 else 0)
        else:
            outcome = "PARTIALLY_COMPLETED" if i % 2 == 0 else "SKIPPED"
            hints, followups = 2, 1
        records.append({
            "question_id": str(q.id),
            "outcome": outcome,
            "hints_used": hints,
            "followups_used": followups,
            "clarifications_used": 1 if profile == "weak" else 0,
        })
    return records


def _fabricate_technical_submission(has_coding: bool, profile: str) -> dict:
    if not has_coding:
        return {}
    if profile == "strong":
        return {
            "code": "def solve(items):\n    # two-pointer approach, O(n) time / O(1) extra space\n    left, right = 0, len(items) - 1\n    result = []\n    while left < right:\n        result.append((items[left], items[right]))\n        left += 1\n        right -= 1\n    return result\n",
            "language": "python",
        }
    return {
        "code": "def solve(items):\n    # brute force, not fully finished\n    for i in range(len(items)):\n        for j in range(len(items)):\n            pass  # ran out of time here\n    return items\n",
        "language": "python",
    }


def _fabricate_scores(criteria: list[AssessmentCriterion], profile: str) -> list[Score]:
    scores = []
    for c in criteria:
        score_val = random.randint(78, 92) if profile == "strong" else random.randint(42, 60)
        if profile == "strong":
            overview = f"Consistently strong on {c.label.lower()} throughout the interview."
            strengths = ["Clear, structured reasoning", "Backed claims with concrete examples"]
            improvements = ["Could be slightly more concise in longer answers"]
        else:
            overview = f"Below expectations on {c.label.lower()} — needs development here."
            strengths = ["Engaged and willing to attempt every question"]
            improvements = ["Structure answers before diving in", "Reduce reliance on hints"]
        scores.append(Score(
            criterion_id=c.id,
            criterion_key=c.key,
            score=score_val,
            overview=overview,
            strengths=strengths,
            improvements=improvements,
            evidence_reference="Mock data — not derived from a real transcript excerpt.",
        ))
    return scores


async def seed():
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        template_criteria = await _get_template_criteria(db)
        if not template_criteria:
            print("WARNING: no TEMPLATE assessment_criteria found — Score rows will be empty.")

        for spec in JOB_SPECS:
            # .scalars().first() rather than scalar_one_or_none() -- this
            # DB has ~12 pre-existing test jobs with case-variant titles
            # like "ai engineer"/"AI Engineer" from earlier dev sessions
            # (confirmed 2026-09-03), so an exact-match query is not
            # guaranteed to find 0-or-1 rows even for a title that looks
            # like it should be unique.
            existing = await db.execute(select(Job).where(Job.title == spec["title"]))
            if existing.scalars().first() is not None:
                print(f"Skipping '{spec['title']}' — already exists.")
                continue

            print(f"\n=== Creating job: {spec['title']} ===")
            job = Job(
                title=spec["title"],
                description=spec["description"],
                seniority=spec["seniority"],
                location=spec["location"],
                required_skills=spec["required_skills"],
                preferred_skills=spec["preferred_skills"],
                responsibilities=spec["responsibilities"],
                status="DRAFT",
                language="en",
            )
            db.add(job)
            await db.flush()

            definition = InterviewDefinition(job_id=job.id, duration_minutes=15, is_public=False)
            db.add(definition)
            await db.flush()

            all_questions_by_type: dict[str, list[InterviewQuestion]] = {}
            for idx, section_type in enumerate(spec["sections"]):
                print(f"  Generating {NUM_QUESTIONS[section_type]} {section_type} questions via Groq...")
                generated = await generate_questions(
                    job_title=spec["title"],
                    job_description=spec["description"],
                    seniority=spec["seniority"],
                    required_skills=spec["required_skills"],
                    preferred_skills=spec["preferred_skills"],
                    responsibilities=spec["responsibilities"],
                    location=spec["location"],
                    candidate_instructions=None,
                    section_type=section_type,
                    section_config=None,
                    num_questions=NUM_QUESTIONS[section_type],
                )
                section = InterviewSection(
                    definition_id=definition.id,
                    section_type=section_type,
                    order_index=idx,
                    config={"time_budget_minutes": TIME_BUDGET_MINUTES[section_type]},
                )
                db.add(section)
                await db.flush()

                section_questions = []
                for q_idx, q in enumerate(generated):
                    question = InterviewQuestion(
                        section_id=section.id,
                        order_index=q_idx,
                        title=q["title"],
                        competency=q.get("competency"),
                        text=q["text"],
                        eval_criteria=q.get("eval_criteria"),
                        config=q.get("config"),
                    )
                    db.add(question)
                    section_questions.append(question)
                await db.flush()
                all_questions_by_type[section_type] = section_questions
                print(f"    -> {len(section_questions)} questions added.")

            if spec["publish"]:
                job.status = "PUBLISHED"
                print(f"  Published '{spec['title']}'.")

            # A representative sample of questions across all this job's
            # sections, for the fabricated transcript/question_records below
            # — VERBAL's questions if present, else whatever exists.
            sample_questions = all_questions_by_type.get("VERBAL") or next(iter(all_questions_by_type.values()))
            has_coding = "CODING" in all_questions_by_type

            for name, email, profile in spec["candidates"]:
                print(f"  Adding mock candidate: {name} ({profile})")
                candidate = CandidateProfile(
                    id=uuid_mod.uuid4(),
                    full_name=name,
                    email=email,
                    professional_title=spec["title"],
                )
                db.add(candidate)
                await db.flush()

                completed_at = datetime.now(timezone.utc) - timedelta(days=random.randint(1, 5))
                session = InterviewSession(
                    candidate_profile_id=candidate.id,
                    job_id=job.id,
                    definition_id=definition.id,
                    role=spec["title"],
                    level=spec["seniority"],
                    language="en",
                    status="COMPLETED",
                    created_at=completed_at - timedelta(minutes=45),
                    started_at=completed_at - timedelta(minutes=40),
                    completed_at=completed_at,
                    final_result={
                        "is_mock": True,
                        "transcript": _fabricate_transcript(sample_questions, profile, spec["title"]),
                        "question_records": _fabricate_question_records(sample_questions, profile),
                        "technical_submission": _fabricate_technical_submission(has_coding, profile),
                        "evaluation_status": "COMPLETED",
                    },
                )
                db.add(session)
                await db.flush()

                overall = random.randint(78, 90) if profile == "strong" else random.randint(45, 58)
                evaluation = Evaluation(
                    session_id=session.id,
                    overall_score=overall,
                    recommendation="Hire" if profile == "strong" else "No Hire",
                    evidence_sufficiency=1.0,
                    summary=(STRONG_SUMMARY if profile == "strong" else WEAK_SUMMARY).format(name=name),
                    detailed_overview=(STRONG_SUMMARY if profile == "strong" else WEAK_SUMMARY).format(name=name)
                        + " (Mock data, generated by scripts/seed_demo_data.py for demo purposes — not a real interview.)",
                    is_placeholder=False,
                )
                db.add(evaluation)
                await db.flush()

                scores = _fabricate_scores(template_criteria, profile)
                for score in scores:
                    score.evaluation_id = evaluation.id
                    db.add(score)

                # Mirror internal.py's submit_evaluation formula exactly:
                # weighted_score = sum(weight_i * score_i) / sum(weight_i)
                # over criteria with a non-null score. All TEMPLATE criteria
                # share weight=5 here, so this is just their plain average
                # -- still computed properly rather than left None, which
                # would otherwise show a confusing "No scored criteria to
                # compute a weighted score" next to a fully populated
                # criteria breakdown (CandidateResultPage.tsx).
                weight_by_key = {c.key: c.weight for c in template_criteria}
                weighted_sum = sum(weight_by_key.get(s.criterion_key, 5) * s.score for s in scores if s.score is not None)
                total_weight = sum(weight_by_key.get(s.criterion_key, 5) for s in scores if s.score is not None)
                evaluation.weighted_score = (weighted_sum / total_weight) if total_weight > 0 else None

                await db.commit()

        print("\nDone.")


if __name__ == "__main__":
    asyncio.run(seed())
