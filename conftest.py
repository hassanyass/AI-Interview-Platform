"""Repo-wide pytest hygiene for the DB-backed suites (test_phase*.py,
backend/tests).

These suites author real Jobs through the real admin API against the
shared database and, historically, never deleted them: by 2026-09-16 the
database held 721 fixture jobs ("6B Test Job" x213, "9B Hints Test Job"
x114, "6C Repeat Job" x40 -- published AND public, so a stray link could
start a real session on one...) plus ~257 sessions on them. This fixture
removes, at the end of every pytest session, any job created DURING the
run whose title looks like a test fixture -- sessions first (jobs.id is
ondelete=SET NULL on interview_sessions, so deleting a job would only
orphan them), then applications, then the jobs (their definitions,
sections, questions and criteria cascade).

Deliberately narrow: only jobs created after this run started, and only
title patterns the suites actually use. Real/demo jobs are never matched.
"""
import asyncio
import re
import sys
from datetime import datetime, timezone

import pytest

FIXTURE_TITLE = re.compile(
    r"(?i)(\btest\b|test job|never published|repeat job|detail test|verification job|throwaway)"
)


@pytest.fixture(scope="session", autouse=True)
def _delete_fixture_jobs_created_this_run():
    started_at = datetime.now(timezone.utc)
    yield
    try:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(_cleanup(started_at))
    except Exception as e:  # noqa: BLE001 -- never fail the run over cleanup
        print(f"\n[conftest] fixture-job cleanup skipped: {e}")


async def _cleanup(started_at: datetime) -> None:
    sys.path.insert(0, "backend")
    from sqlalchemy import select, delete
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from backend.db.session import engine as app_engine
    from backend.models.interview import Job, InterviewSession, JobApplication

    # A fresh engine: the app's pooled connections belong to the tests'
    # (now closed) event loop and cannot be reused from this one.
    engine = create_async_engine(app_engine.url, pool_pre_ping=True)
    async with AsyncSession(engine) as db:
        rows = (await db.execute(select(Job.id, Job.title).where(Job.created_at >= started_at))).all()
        job_ids = [jid for jid, title in rows if FIXTURE_TITLE.search(title or "")]
        if not job_ids:
            return
        sessions = (await db.execute(delete(InterviewSession).where(InterviewSession.job_id.in_(job_ids)))).rowcount
        apps = (await db.execute(delete(JobApplication).where(JobApplication.job_id.in_(job_ids)))).rowcount
        jobs = (await db.execute(delete(Job).where(Job.id.in_(job_ids)))).rowcount
        await db.commit()
    print(f"\n[conftest] removed fixture data created by this run: jobs={jobs} sessions={sessions} applications={apps}")
