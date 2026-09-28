"""H2-A1: one error body for every failure, a request id on every response,
and the DRAFT-status 500 fixed.

The problem-shaped body keeps `detail` exactly as raised (frontend, agent
and the legacy suites read it) and stays `application/json` (the agent's
aiohttp `resp.json()` would reject problem+json).
"""
import uuid

import pytest
import pytest_asyncio
from fastapi import APIRouter, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from backend.api.deps import get_current_user_token_data
from backend.core.errors import Conflict, NotFound, UpstreamError
from backend.db.session import AsyncSessionLocal
from backend.main import app
from backend.models.interview import InterviewSession, Job
from backend.models.profile import CandidateProfile, UserRole

# ── a throwaway router exercising each error path ─────────────────────────
_probe = APIRouter(prefix="/__probe")


@_probe.get("/app-error")
async def _app_error():
    raise Conflict("state clash", code="probe_conflict")


@_probe.get("/not-found")
async def _not_found():
    raise NotFound()


@_probe.get("/upstream")
async def _upstream():
    raise UpstreamError("provider said no")


@_probe.get("/legacy")
async def _legacy():
    raise HTTPException(status_code=409, detail="CV_REQUIRED: upload your CV first", headers={"X-Probe": "1"})


@_probe.get("/legacy-list")
async def _legacy_list():
    raise HTTPException(status_code=422, detail=[{"msg": "a"}, {"msg": "b"}])


@_probe.get("/boom")
async def _boom():
    raise RuntimeError("secret internal state")


@_probe.get("/validated")
async def _validated(n: int):
    return {"n": n}


app.include_router(_probe)
app.router.routes  # noqa: B018 -- router mounted for the tests in this module


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_app_error_becomes_a_problem_body_with_request_id(client):
    r = await client.get("/__probe/app-error")
    assert r.status_code == 409
    assert r.headers["content-type"].startswith("application/json")
    body = r.json()
    assert body["title"] == "Conflict" and body["status"] == 409
    assert body["detail"] == "state clash" and body["code"] == "probe_conflict"
    assert body["instance"] == "/__probe/app-error"
    assert body["request_id"] and body["request_id"] == r.headers["x-request-id"]


@pytest.mark.asyncio
async def test_default_detail_is_the_status_phrase(client):
    r = await client.get("/__probe/not-found")
    assert r.status_code == 404 and r.json()["detail"] == "Not Found"
    r = await client.get("/__probe/upstream")
    assert r.status_code == 502 and r.json()["title"] == "Bad Gateway"


@pytest.mark.asyncio
async def test_legacy_http_exception_keeps_detail_and_headers(client):
    r = await client.get("/__probe/legacy")
    assert r.status_code == 409
    assert r.json()["detail"] == "CV_REQUIRED: upload your CV first"   # byte-identical
    assert r.headers["x-probe"] == "1"
    r = await client.get("/__probe/legacy-list")
    assert r.json()["detail"] == [{"msg": "a"}, {"msg": "b"}]          # lists pass through (lib/api.ts joins msg)


@pytest.mark.asyncio
async def test_request_validation_keeps_fastapis_list_detail(client):
    r = await client.get("/__probe/validated", params={"n": "x"})
    assert r.status_code == 422
    body = r.json()
    assert isinstance(body["detail"], list) and body["detail"][0]["loc"][-1] == "n"
    assert body["request_id"]


@pytest.mark.asyncio
async def test_unhandled_exception_is_a_500_problem_without_leaking(client):
    r = await client.get("/__probe/boom")
    assert r.status_code == 500
    body = r.json()
    assert body["code"] == "internal_error" and "secret internal state" not in r.text
    assert body["request_id"] == r.headers["x-request-id"]


@pytest.mark.asyncio
async def test_inbound_request_id_is_honoured_and_unsafe_ones_replaced(client):
    r = await client.get("/__probe/not-found", headers={"X-Request-ID": "agent-abc.123"})
    assert r.headers["x-request-id"] == "agent-abc.123" and r.json()["request_id"] == "agent-abc.123"
    r = await client.get("/__probe/not-found", headers={"X-Request-ID": "bad value\nwith newline"})
    assert r.headers["x-request-id"] != "bad value\nwith newline"


@pytest.mark.asyncio
async def test_successful_responses_carry_the_request_id_too(client):
    r = await client.get("/__probe/validated", params={"n": 3})
    assert r.status_code == 200 and len(r.headers["x-request-id"]) == 32


# ── the DRAFT 500 ──────────────────────────────────────────────────────────

ADMIN_UUID = uuid.uuid4()
_admin = lambda: {"sub": str(ADMIN_UUID), "email": "errors@path2hire.test", "type": "supabase"}  # noqa: E731


@pytest_asyncio.fixture
async def admin_client():
    async with AsyncSessionLocal() as db:
        db.add(UserRole(user_id=ADMIN_UUID, role="admin"))
        await db.commit()
    app.dependency_overrides[get_current_user_token_data] = _admin
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_current_user_token_data, None)
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Job).where(Job.title == "Unpublish Test Job"))
        await db.execute(delete(UserRole).where(UserRole.user_id == ADMIN_UUID))
        await db.commit()


@pytest.mark.asyncio
async def test_unpublish_to_draft_no_longer_500s(admin_client):
    job = (await admin_client.post("/api/v1/admin/jobs", json={"title": "Unpublish Test Job", "seniority": "mid"})).json()
    job_id, definition_id = job["id"], job["definition"]["id"]
    sec = (await admin_client.post("/api/v1/admin/sections", json={"definition_id": definition_id, "section_type": "VERBAL", "order_index": 0})).json()
    await admin_client.patch(f"/api/v1/admin/sections/{sec['id']}", json={"config": {**sec["config"], "time_budget_minutes": 10}})
    await admin_client.post(f"/api/v1/admin/sections/{sec['id']}/questions", json={"title": "Q", "text": "Tell me."})
    assert (await admin_client.post(f"/api/v1/admin/jobs/{job_id}/publish")).status_code == 200

    # No sessions yet -> back to DRAFT is allowed (used to be ModuleNotFoundError -> 500).
    r = await admin_client.patch(f"/api/v1/admin/jobs/{job_id}/status", json={"status": "DRAFT"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "DRAFT"

    # With a session on the job -> 409 with the intended message.
    assert (await admin_client.post(f"/api/v1/admin/jobs/{job_id}/publish")).status_code == 200
    async with AsyncSessionLocal() as db:
        profile = CandidateProfile(full_name="Errors Test", email=f"errors-{uuid.uuid4().hex[:8]}@path2hire.test")
        db.add(profile)
        await db.flush()
        db.add(InterviewSession(job_id=uuid.UUID(job_id), definition_id=uuid.UUID(definition_id),
                                candidate_profile_id=profile.id, role="Errors Test Role", level="mid",
                                language="en", status="CREATED"))
        await db.commit()
    r = await admin_client.patch(f"/api/v1/admin/jobs/{job_id}/status", json={"status": "DRAFT"})
    assert r.status_code == 409
    assert "Pause it instead" in r.json()["detail"]
    async with AsyncSessionLocal() as db:
        await db.execute(delete(InterviewSession).where(InterviewSession.job_id == uuid.UUID(job_id)))
        await db.execute(delete(CandidateProfile).where(CandidateProfile.full_name == "Errors Test"))
        await db.commit()
