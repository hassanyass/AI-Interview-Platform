"""H2-B: readiness vs liveness, replica-safe sweep and finalization, tracked
background tasks, storage transport retries, ingest ordering, pagination."""
import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, text

from backend.core import background
from backend.db.session import AsyncSessionLocal, engine
from backend.main import app
from backend.models.interview import Evaluation, InterviewSession, Job
from backend.models.profile import CandidateProfile, UserRole
from backend.providers.storage.base import StorageUnavailable
from backend.providers.storage.supabase import SupabaseStorage
from backend.services.sessions import finalization
from backend.services.sessions.finalization import SWEEP_LOCK_KEY, finalize_live_session


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as c:
        yield c


# ── liveness / readiness ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_is_liveness_only_and_ready_checks_the_database(client):
    h = await client.get("/health")
    assert h.status_code == 200 and h.json()["status"] == "ok" and "database" not in h.json()
    r = await client.get("/ready")
    assert r.status_code == 200 and r.json() == {"status": "ready", "checks": {"database": "ok"}, "version": app.version}


@pytest.mark.asyncio
async def test_ready_returns_503_when_the_database_fails(client):
    class Broken:
        def connect(self):
            raise RuntimeError("pool exhausted")

    with patch("backend.main.engine", Broken()):
        r = await client.get("/ready")
        h = await client.get("/health")
    assert r.status_code == 503 and r.json()["checks"]["database"] == "error"
    assert h.status_code == 200  # liveness unaffected by a DB outage


# ── sweep: advisory lock ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sweep_skips_the_iteration_while_another_connection_holds_the_lock(monkeypatch):
    from backend.core.config import settings
    monkeypatch.setattr(settings, "DISCONNECT_SWEEP_INTERVAL_SECONDS", 0)
    # hold the same advisory lock from a separate connection, as another replica would
    holder = await engine.connect()
    await holder.execute(text("SELECT pg_advisory_lock(:k)"), {"k": SWEEP_LOCK_KEY})
    selects = []
    real_execute = AsyncSessionLocal.class_.execute

    async def spy(self, statement, *a, **kw):
        if "interview_sessions.disconnected_at" in str(statement):
            selects.append(1)
        return await real_execute(self, statement, *a, **kw)

    try:
        with patch.object(AsyncSessionLocal.class_, "execute", spy):
            task = asyncio.create_task(finalization.disconnect_auto_finalize_sweep_loop())
            await asyncio.sleep(0.5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert selects == []           # never queried for stale sessions: lock held elsewhere
    finally:
        await holder.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": SWEEP_LOCK_KEY})
        await holder.close()

    # lock released -> the next iteration does the real query
    with patch.object(AsyncSessionLocal.class_, "execute", spy):
        task = asyncio.create_task(finalization.disconnect_auto_finalize_sweep_loop())
        await asyncio.sleep(0.5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert len(selects) >= 1


# ── finalize under concurrency ─────────────────────────────────────────────

@pytest_asyncio.fixture
async def in_progress_session():
    async with AsyncSessionLocal() as db:
        profile = CandidateProfile(full_name="Resilience Test", email=f"res-{uuid.uuid4().hex[:8]}@path2hire.test")
        db.add(profile)
        await db.flush()
        s = InterviewSession(candidate_profile_id=profile.id, role="r", level="mid", language="en",
                             status="IN_PROGRESS", recording_egress_id="EG_r")
        db.add(s)
        await db.flush()
        sid = s.id
        await db.commit()
    yield sid
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Evaluation).where(Evaluation.session_id == sid))
        await db.execute(delete(InterviewSession).where(InterviewSession.id == sid))
        await db.execute(delete(CandidateProfile).where(CandidateProfile.full_name == "Resilience Test"))
        await db.commit()


@pytest.mark.asyncio
async def test_two_concurrent_finalizers_finalize_exactly_once(in_progress_session):
    sid = in_progress_session
    with patch("backend.services.sessions.finalization.get_realtime") as rt:
        rt.return_value.stop_recording = AsyncMock()
        rt.return_value.delete_room = AsyncMock()

        async def one():
            async with AsyncSessionLocal() as db:
                s = (await db.execute(select(InterviewSession).where(InterviewSession.id == sid))).scalar_one()
                return await finalize_live_session(db, s, target_status="TERMINATED")

        results = await asyncio.gather(one(), one())
        assert sorted(results) == [False, True]
        assert rt.return_value.stop_recording.await_count == 1
    async with AsyncSessionLocal() as db:
        evs = (await db.execute(select(Evaluation).where(Evaluation.session_id == sid))).scalars().all()
        assert len(evs) == 1 and evs[0].is_placeholder is True
        assert (await db.execute(select(InterviewSession.status).where(InterviewSession.id == sid))).scalar_one() == "TERMINATED"


# ── background task registry ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_spawned_tasks_are_tracked_until_done_and_drain_waits():
    started = asyncio.Event()

    async def work():
        started.set()
        await asyncio.sleep(0.05)
        return "done"

    t = background.spawn(work(), name="probe")
    await started.wait()
    assert background.pending() == 1
    await background.drain(timeout=1.0)
    assert t.result() == "done" and background.pending() == 0


# ── storage: transport retry ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_supabase_storage_retries_transport_errors_then_gives_up():
    calls = {"n": 0}

    class FlakyClient:
        def __init__(self, *a, **kw): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def request(self, *a, **kw):
            calls["n"] += 1
            if calls["n"] < 3:
                raise httpx.ConnectError("reset")
            return httpx.Response(200)

    s = SupabaseStorage(project_url="https://p.supabase.co", service_key="k", bucket="b", retry_attempts=2)
    with patch("backend.providers.storage.supabase.httpx.AsyncClient", FlakyClient), \
         patch("backend.providers.storage.supabase.asyncio.sleep", new=AsyncMock()):
        await s.put("k1", b"x", content_type="application/pdf")     # succeeds on the 3rd try
        assert calls["n"] == 3
        calls["n"] = -10                                            # never recovers
        with pytest.raises(StorageUnavailable):
            await s.delete("k1")


# ── ingest ordering ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ingest_writes_the_row_before_uploading_and_marks_failed_on_upload_error():
    from io import BytesIO

    from starlette.datastructures import UploadFile

    from backend.models.profile import Resume
    from backend.services.resume_ingest import ingest_resume

    async with AsyncSessionLocal() as db:
        profile = CandidateProfile(full_name="Ingest Test", email=f"ing-{uuid.uuid4().hex[:8]}@path2hire.test")
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
        pid = profile.id
        f = UploadFile(filename="cv.pdf", file=BytesIO(b"%PDF-1.4 x"), headers={"content-type": "application/pdf"})
        seen = {}

        async def failing_upload(file, user_id, resume_id, storage=None):
            # the row must already exist when the upload runs
            async with AsyncSessionLocal() as db2:
                row = (await db2.execute(select(Resume).where(Resume.id == resume_id))).scalar_one_or_none()
                seen["status_at_upload"] = row.extraction_status if row else None
            raise RuntimeError("storage down")

        with patch("backend.services.resume_ingest.ResumeService.upload", new=failing_upload):
            with pytest.raises(RuntimeError):
                await ingest_resume(db, f, profile)
        assert seen["status_at_upload"] == "PROCESSING"
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(Resume).where(Resume.profile_id == pid))).scalars().all()
        assert len(rows) == 1 and rows[0].extraction_status == "FAILED"
        await db.execute(delete(Resume).where(Resume.profile_id == pid))
        await db.execute(delete(CandidateProfile).where(CandidateProfile.id == pid))
        await db.commit()


# ── pagination defaults ────────────────────────────────────────────────────

ADMIN_UUID = uuid.uuid4()
_admin = lambda: {"sub": str(ADMIN_UUID), "email": "res@path2hire.test", "type": "supabase"}  # noqa: E731


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
        await db.execute(delete(Job).where(Job.title.like("Pagination Test Job %")))
        await db.execute(delete(UserRole).where(UserRole.user_id == ADMIN_UUID))
        await db.commit()


@pytest.mark.asyncio
async def test_job_list_is_unbounded_by_default_and_pages_when_asked(admin_client):
    for i in range(3):
        assert (await admin_client.post("/api/v1/admin/jobs", json={"title": f"Pagination Test Job {i}", "seniority": "mid"})).status_code == 201
    all_jobs = (await admin_client.get("/api/v1/admin/jobs")).json()
    mine = [j for j in all_jobs if j["title"].startswith("Pagination Test Job")]
    assert len(mine) == 3
    page = (await admin_client.get("/api/v1/admin/jobs", params={"limit": 2})).json()
    assert len(page) == 2
    assert (await admin_client.get("/api/v1/admin/jobs", params={"limit": 0})).status_code == 422
