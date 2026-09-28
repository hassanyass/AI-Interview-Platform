"""H2-F: the four AI endpoints queue work instead of holding the request
open, and the worker drains the queue exactly once per row."""
import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from backend.db.session import AsyncSessionLocal
from backend.main import app
from backend.models.interview import InterviewQuestion, Job
from backend.models.profile import UserRole
from backend.models.task import FAILED, QUEUED, RUNNING, SUCCEEDED, Task
from backend.providers.queue.postgres import PostgresTaskQueue
from backend.services.tasks import handlers
from backend.services.tasks.worker import run_pending_once, run_task

ADMIN_UUID = uuid.uuid4()
_admin = lambda: {"sub": str(ADMIN_UUID), "email": "tasks@path2hire.test", "type": "supabase"}  # noqa: E731

GENERATED = [{
    "title": "Task Queue Q1",
    "competency": "Python",
    "text": "Explain generators.",
    "eval_criteria": {"excellent": "clear", "poor": "none"},
}]


@pytest.fixture
def queue():
    return PostgresTaskQueue(AsyncSessionLocal)


@pytest_asyncio.fixture
async def admin_client():
    from backend.api.deps import get_current_user_token_data
    async with AsyncSessionLocal() as db:
        db.add(UserRole(user_id=ADMIN_UUID, role="admin"))
        await db.commit()
    app.dependency_overrides[get_current_user_token_data] = _admin
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_current_user_token_data, None)
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Job).where(Job.title.like("Task Queue Test Job%")))
        await db.execute(delete(UserRole).where(UserRole.user_id == ADMIN_UUID))
        await db.commit()


async def _draft_section(client) -> str:
    job = (await client.post("/api/v1/admin/jobs", json={
        "title": "Task Queue Test Job", "seniority": "mid", "required_skills": ["Python"],
    })).json()
    section = await client.post("/api/v1/admin/sections", json={
        "definition_id": job["definition"]["id"], "section_type": "VERBAL", "order_index": 0,
    })
    return section.json()["id"]


# ── the endpoint no longer waits ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_questions_answers_202_without_calling_the_llm(admin_client):
    section_id = await _draft_section(admin_client)
    with patch("backend.services.question_generator.generate_questions", new_callable=AsyncMock) as gen:
        resp = await admin_client.post(
            f"/api/v1/admin/sections/{section_id}/generate-questions", json={"num_questions": 1}
        )
        assert resp.status_code == 202, resp.text
        # The whole point: the request returned before any provider call.
        gen.assert_not_awaited()
    body = resp.json()
    assert body["kind"] == handlers.GENERATE_QUESTIONS and body["status"] == QUEUED
    async with AsyncSessionLocal() as db:
        task = (await db.execute(select(Task).where(Task.id == uuid.UUID(body["task_id"])))).scalar_one()
        assert task.payload["section_id"] == section_id and task.requested_by == str(ADMIN_UUID)


@pytest.mark.asyncio
async def test_a_missing_section_still_fails_immediately_not_as_a_task(admin_client):
    resp = await admin_client.post(
        f"/api/v1/admin/sections/{uuid.uuid4()}/generate-questions", json={"num_questions": 1}
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_the_worker_runs_the_queued_generation_and_the_questions_land(admin_client, queue):
    section_id = await _draft_section(admin_client)
    task_id = (await admin_client.post(
        f"/api/v1/admin/sections/{section_id}/generate-questions", json={"num_questions": 1}
    )).json()["task_id"]

    with patch("backend.services.question_generator.generate_questions",
               new_callable=AsyncMock, return_value=GENERATED):
        assert await run_pending_once(queue=queue) >= 1

    polled = (await admin_client.get(f"/api/v1/admin/tasks/{task_id}")).json()
    assert polled["status"] == SUCCEEDED and polled["result"]["count"] == 1
    async with AsyncSessionLocal() as db:
        questions = (await db.execute(
            select(InterviewQuestion).where(InterviewQuestion.section_id == uuid.UUID(section_id))
        )).scalars().all()
    assert [q.title for q in questions] == ["Task Queue Q1"]


# ── claiming ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_two_workers_never_claim_the_same_task(queue):
    ids = [(await queue.enqueue("noop", {"n": i})).id for i in range(4)]
    try:
        claimed = await asyncio.gather(*[queue.claim() for _ in range(6)])
        got = [c.id for c in claimed if c is not None]
        assert sorted(got) == sorted(ids)          # each row claimed exactly once
        assert len(set(got)) == len(got)
        assert all(c.status == RUNNING and c.attempts == 1 for c in claimed if c)
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Task).where(Task.id.in_(ids)))
            await db.commit()


@pytest.mark.asyncio
async def test_an_unknown_kind_fails_the_task_instead_of_the_worker(queue):
    task = await queue.enqueue("no_such_kind", {})
    try:
        claimed = await queue.claim()
        assert await run_task(claimed, queue=queue) == FAILED
        row = await queue.get(task.id)
        assert row.status == FAILED and row.error_code == "unknown_task_kind"
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Task).where(Task.id == task.id))
            await db.commit()


@pytest.mark.asyncio
async def test_a_handler_failure_is_recorded_with_its_own_message(admin_client, queue):
    section_id = await _draft_section(admin_client)
    task_id = (await admin_client.post(
        f"/api/v1/admin/sections/{section_id}/generate-questions", json={"num_questions": 1}
    )).json()["task_id"]

    with patch("backend.services.question_generator.generate_questions",
               new_callable=AsyncMock, side_effect=RuntimeError("groq exploded")):
        await run_pending_once(queue=queue)

    polled = (await admin_client.get(f"/api/v1/admin/tasks/{task_id}")).json()
    assert polled["status"] == FAILED
    assert polled["error_code"] == "task_failed" and "try again" in polled["error"]


@pytest.mark.asyncio
async def test_a_row_deleted_between_queueing_and_running_fails_with_the_handlers_message(queue):
    # The endpoint validated the session at 202 time; minutes later the
    # handler must cope with it being gone, and say so.
    task = await queue.enqueue(handlers.REGENERATE_EVALUATION, {"session_id": str(uuid.uuid4())})
    try:
        await run_pending_once(queue=queue)
        row = await queue.get(task.id)
        assert row.status == FAILED
        assert row.error == "Interview session not found."
        assert row.error_code == "task_failed"      # NotFound carries no code of its own
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Task).where(Task.id == task.id))
            await db.commit()


@pytest.mark.asyncio
async def test_a_task_abandoned_by_a_dead_process_is_reported_not_left_hanging(queue):
    task = await queue.enqueue("noop", {})
    try:
        await queue.claim()                                   # now RUNNING
        assert await queue.reap_stale(older_than_minutes=0) >= 1
        row = await queue.get(task.id)
        assert row.status == FAILED and row.error_code == "task_interrupted"
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Task).where(Task.id == task.id))
            await db.commit()


# ── polling endpoint ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_polling_an_unknown_task_is_404(admin_client):
    assert (await admin_client.get(f"/api/v1/admin/tasks/{uuid.uuid4()}")).status_code == 404


@pytest.mark.asyncio
async def test_polling_a_task_requires_an_admin():
    # No admin_client fixture here: its dependency override is installed on
    # the shared app object, so an "anonymous" client would inherit it.
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as anon:
        assert (await anon.get(f"/api/v1/admin/tasks/{uuid.uuid4()}")).status_code in (401, 403)


@pytest.mark.asyncio
async def test_queue_depth_and_age_are_reported(queue):
    task = await queue.enqueue("noop", {})
    try:
        stats = await queue.stats()
        assert stats.queued >= 1 and stats.oldest_queued_age_seconds >= 0
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Task).where(Task.id == task.id))
            await db.commit()
