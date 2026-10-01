"""Phase 8's definition of done: the job results list is RANKED.

"HR dashboard can list and sort candidates for a given Job by score" was
the one half of Phase 8 never built -- the Evaluation/Score tables and both
result views shipped, but `get_job_results` ordered by `created_at` and no
sort control existed, so HR could open any one scorecard and never line
candidates up against each other.

Ranking is by the **weighted** score -- the code-computed aggregate of the
criteria and weights HR configured for this job (CURRENT_DECISIONS,
"Scoring mechanism upgrade") -- falling back to the LLM's holistic
`overall_score` when no criterion scored. Unscored candidates sort last
rather than to the top, because a null score is absent, not zero.

Real rows against the disposable test database, cleaned up after. The
ordering is the kind of rule that breaks silently under a later refactor
and costs nothing to pin, which is why it is tested even though this
phase's architecture doc leans on manual verification (raised and settled
with the user before writing this).
"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from backend.api.deps import get_current_user_token_data
from backend.db.session import AsyncSessionLocal
from backend.main import app
from backend.models.interview import Evaluation, InterviewSession, Job
from backend.models.profile import CandidateProfile, UserRole

ADMIN_UUID = uuid.uuid4()
_admin = lambda: {"sub": str(ADMIN_UUID), "email": "ranking@path2hire.test", "type": "supabase"}


@pytest_asyncio.fixture
async def ranked_job():
    """One job, six candidates covering every ordering case.

    Named by the position each should land in, so a failure reads as
    "expected weighted_high, got ..." rather than a bare uuid.
    """
    async with AsyncSessionLocal() as db:
        db.add(UserRole(user_id=ADMIN_UUID, role="admin"))
        await db.commit()

    app.dependency_overrides[get_current_user_token_data] = _admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        job = (await c.post("/api/v1/admin/jobs", json={"title": "Ranking Test Job", "seniority": "mid"})).json()
    job_id, definition_id = uuid.UUID(job["id"]), uuid.UUID(job["definition"]["id"])

    # (label, weighted_score, overall_score) -- deliberately inserted in an
    # order that is NOT the expected output order, so a passing test cannot
    # be insertion order in disguise.
    specs = [
        ("overall_only_3", None, 3),      # no criterion scored -> falls back to 3
        ("weighted_high", 4.8, 2),        # weighted beats overall: must outrank the 4
        ("no_evaluation", None, None),    # never evaluated -> last
        ("weighted_low", 1.2, 5),         # low weighted despite a high holistic
        ("overall_only_4", None, 4),
        ("in_progress", None, None),      # still running -> last
    ]
    created = {}
    async with AsyncSessionLocal() as db:
        for label, weighted, overall in specs:
            cid, sid = uuid.uuid4(), uuid.uuid4()
            db.add(CandidateProfile(id=cid, full_name=label, email=f"{label}-{cid.hex[:6]}@example.dev"))
            db.add(InterviewSession(
                id=sid, candidate_profile_id=cid, job_id=job_id, definition_id=definition_id,
                role="Engineer", level="mid", language="en",
                status="IN_PROGRESS" if label == "in_progress" else "COMPLETED",
            ))
            if label != "no_evaluation" and label != "in_progress":
                db.add(Evaluation(
                    session_id=sid, overall_score=overall, weighted_score=weighted,
                    recommendation="Hire", evidence_sufficiency=0.9, summary="s",
                ))
            created[label] = sid
        await db.commit()

    yield job_id, created

    async with AsyncSessionLocal() as db:
        sids = list(created.values())
        await db.execute(delete(Evaluation).where(Evaluation.session_id.in_(sids)))
        await db.execute(delete(InterviewSession).where(InterviewSession.id.in_(sids)))
        await db.execute(delete(CandidateProfile).where(CandidateProfile.full_name.in_(list(created))))
        await db.execute(delete(Job).where(Job.id == job_id))
        await db.execute(delete(UserRole).where(UserRole.user_id == ADMIN_UUID))
        await db.commit()
    app.dependency_overrides.clear()


async def _results(job_id):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.get(f"/api/v1/admin/jobs/{job_id}/results")
    assert response.status_code == 200, response.text
    return response.json()["candidates"]


@pytest.mark.asyncio
async def test_candidates_come_back_ranked_best_first(ranked_job):
    job_id, _ = ranked_job
    names = [c["candidate_name"] for c in await _results(job_id)]
    # 4.8 > 4 > 3 > 1.2, then the two with no score at all.
    assert names[:4] == ["weighted_high", "overall_only_4", "overall_only_3", "weighted_low"]


@pytest.mark.asyncio
async def test_the_weighted_score_outranks_the_holistic_one(ranked_job):
    job_id, _ = ranked_job
    names = [c["candidate_name"] for c in await _results(job_id)]
    # weighted_low holds overall_score 5 -- the highest holistic score in the
    # job -- and still sorts below everyone, because its criteria-weighted
    # result is 1.2. Ranking by overall_score would put it first.
    assert names.index("weighted_high") < names.index("weighted_low")
    assert names.index("overall_only_3") < names.index("weighted_low")


@pytest.mark.asyncio
async def test_unscored_candidates_sort_last_not_first(ranked_job):
    job_id, _ = ranked_job
    names = [c["candidate_name"] for c in await _results(job_id)]
    # A null score is absent, not zero -- and certainly not "best".
    assert set(names[-2:]) == {"no_evaluation", "in_progress"}


@pytest.mark.asyncio
async def test_the_row_carries_the_score_the_ranking_used(ranked_job):
    job_id, _ = ranked_job
    rows = {c["candidate_name"]: c for c in await _results(job_id)}
    # Showing an order without the number behind it reads as arbitrary.
    assert rows["weighted_high"]["weighted_score"] == pytest.approx(4.8)
    assert rows["weighted_high"]["overall_score"] == 2
    assert rows["overall_only_4"]["weighted_score"] is None
    assert rows["overall_only_4"]["overall_score"] == 4
    assert rows["no_evaluation"]["weighted_score"] is None
    assert rows["no_evaluation"]["overall_score"] is None


@pytest.mark.asyncio
async def test_ranking_does_not_drop_or_duplicate_anyone(ranked_job):
    job_id, created = ranked_job
    rows = await _results(job_id)
    # An ORDER BY with a join is an easy place to lose or fan out rows.
    assert len(rows) == len(created)
    assert {c["candidate_name"] for c in rows} == set(created)
