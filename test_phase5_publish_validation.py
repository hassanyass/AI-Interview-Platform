"""
Phase 5 admin publish-flow validation — found and fixed during Transition
Phase 7's 7F scoping, not originally covered by any Phase 5 test (Phase 5
was verified manually/via browser per docs/PROJECT_STATUS.md, no automated
coverage existed for this endpoint before now).

Confirms publish_job (backend/backend/api/endpoints/admin.py) rejects
publishing an InterviewDefinition that has a section with zero questions,
and still allows publishing once every existing section has at least one.
"""
import pytest
import pytest_asyncio
import uuid
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.db.session import AsyncSessionLocal
from backend.models.profile import UserRole
from backend.api.deps import get_current_user_token_data

ADMIN_UUID = str(uuid.uuid4())
_admin_payload = {"sub": ADMIN_UUID, "email": "admin@path2hire.test", "type": "supabase"}


@pytest_asyncio.fixture(autouse=True)
async def _seed_admin_role():
    async with AsyncSessionLocal() as session:
        from sqlalchemy.future import select
        stmt = select(UserRole).where(UserRole.user_id == uuid.UUID(ADMIN_UUID))
        result = await session.execute(stmt)
        if not result.scalar_one_or_none():
            session.add(UserRole(user_id=uuid.UUID(ADMIN_UUID), role="admin"))
            await session.commit()
    yield
    app.dependency_overrides.pop(get_current_user_token_data, None)


@pytest.mark.asyncio
async def test_publish_rejects_a_verbal_section_with_zero_questions():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        app.dependency_overrides[get_current_user_token_data] = lambda: _admin_payload

        job_resp = await client.post("/api/v1/admin/jobs", json={"title": "Empty Section Job"})
        assert job_resp.status_code == 201, job_resp.text
        job = job_resp.json()
        job_id = job["id"]
        definition_id = job["definition"]["id"]

        section_resp = await client.post("/api/v1/admin/sections", json={
            "definition_id": definition_id, "section_type": "VERBAL", "order_index": 0,
        })
        assert section_resp.status_code == 201, section_resp.text
        # Deliberately no questions added.

        publish_resp = await client.post(f"/api/v1/admin/jobs/{job_id}/publish")
        assert publish_resp.status_code == 409, publish_resp.text
        assert "VERBAL" in publish_resp.json()["detail"]

        # And the job must genuinely still be DRAFT, not partially published.
        get_resp = await client.get(f"/api/v1/admin/jobs/{job_id}")
        assert get_resp.status_code == 200, get_resp.text
        assert get_resp.json()["status"] == "DRAFT"


@pytest.mark.asyncio
async def test_publish_rejects_a_coding_section_even_with_real_questions():
    """STOPGAP guard, not a real fix — see docs/CURRENT_DECISIONS.md. The
    runtime (controller.py) only reads context.sections["VERBAL"]; a CODING
    section with real, non-empty content would otherwise publish and either
    get silently ignored or substituted with unrelated legacy content once
    a candidate reaches the interview. This must be removed as part of
    Phase 9's own work, not carried forward once CODING is genuinely
    supported."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        app.dependency_overrides[get_current_user_token_data] = lambda: _admin_payload

        job_resp = await client.post("/api/v1/admin/jobs", json={"title": "Coding Section Job"})
        assert job_resp.status_code == 201, job_resp.text
        job = job_resp.json()
        job_id = job["id"]
        definition_id = job["definition"]["id"]

        section_resp = await client.post("/api/v1/admin/sections", json={
            "definition_id": definition_id, "section_type": "CODING", "order_index": 0,
            # WR-A: also give it a time budget — this test's whole point is
            # isolating the CODING-type stopgap rejection specifically, so
            # the time-budget check (a different, legitimate 409) must not
            # be what actually fires here.
            "config": {"time_budget_minutes": 20},
        })
        assert section_resp.status_code == 201, section_resp.text
        section_id = section_resp.json()["id"]

        # Real content, not an empty section -- proves this is a type-based
        # rejection, not a rediscovery of the empty-question check.
        question_resp = await client.post(f"/api/v1/admin/sections/{section_id}/questions", json={
            "title": "Q1", "text": "Implement a rate limiter.",
            "config": {
                "starter_code": "def rate_limiter():\n    pass",
                "supported_languages": ["python"],
                "constraints": "Handle up to 1000 requests/sec",
            },
        })
        assert question_resp.status_code == 201, question_resp.text

        publish_resp = await client.post(f"/api/v1/admin/jobs/{job_id}/publish")
        assert publish_resp.status_code == 409, publish_resp.text
        assert "not yet supported" in publish_resp.json()["detail"]

        get_resp = await client.get(f"/api/v1/admin/jobs/{job_id}")
        assert get_resp.status_code == 200, get_resp.text
        assert get_resp.json()["status"] == "DRAFT"


@pytest.mark.asyncio
async def test_publish_succeeds_once_every_section_has_a_question():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        app.dependency_overrides[get_current_user_token_data] = lambda: _admin_payload

        job_resp = await client.post("/api/v1/admin/jobs", json={"title": "Populated Section Job"})
        assert job_resp.status_code == 201, job_resp.text
        job = job_resp.json()
        job_id = job["id"]
        definition_id = job["definition"]["id"]

        section_resp = await client.post("/api/v1/admin/sections", json={
            "definition_id": definition_id, "section_type": "VERBAL", "order_index": 0,
            # WR-A: time_budget_minutes is now required at publish time —
            # see test_publish_rejects_a_section_with_no_time_budget_set.
            "config": {"time_budget_minutes": 10},
        })
        assert section_resp.status_code == 201, section_resp.text
        section_id = section_resp.json()["id"]

        question_resp = await client.post(f"/api/v1/admin/sections/{section_id}/questions", json={
            "title": "Q1", "competency": "debugging", "text": "Tell me about a bug you fixed.",
        })
        assert question_resp.status_code == 201, question_resp.text

        publish_resp = await client.post(f"/api/v1/admin/jobs/{job_id}/publish")
        assert publish_resp.status_code == 200, publish_resp.text
        assert publish_resp.json()["status"] == "PUBLISHED"


@pytest.mark.asyncio
async def test_publish_rejects_a_section_with_no_time_budget_set():
    """WR-A (docs/section-pacing-architecture.md): time_budget_minutes is
    optional while a section is being built (mirrors questions being
    addable after section creation) but required once it actually goes
    live — same enforcement point/shape as the empty-questions check
    above, deliberately not a live-runtime concern."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        app.dependency_overrides[get_current_user_token_data] = lambda: _admin_payload

        job_resp = await client.post("/api/v1/admin/jobs", json={"title": "No Time Budget Job"})
        assert job_resp.status_code == 201, job_resp.text
        job = job_resp.json()
        job_id = job["id"]
        definition_id = job["definition"]["id"]

        section_resp = await client.post("/api/v1/admin/sections", json={
            "definition_id": definition_id, "section_type": "VERBAL", "order_index": 0,
        })
        assert section_resp.status_code == 201, section_resp.text
        section_id = section_resp.json()["id"]
        # Config genuinely absent — proves this is a distinct check from
        # the empty-questions one, not a rediscovery of it.
        assert section_resp.json()["config"] is None

        question_resp = await client.post(f"/api/v1/admin/sections/{section_id}/questions", json={
            "title": "Q1", "competency": "debugging", "text": "Tell me about a bug you fixed.",
        })
        assert question_resp.status_code == 201, question_resp.text

        publish_resp = await client.post(f"/api/v1/admin/jobs/{job_id}/publish")
        assert publish_resp.status_code == 409, publish_resp.text
        assert "time budget" in publish_resp.json()["detail"]
        assert "VERBAL" in publish_resp.json()["detail"]

        get_resp = await client.get(f"/api/v1/admin/jobs/{job_id}")
        assert get_resp.status_code == 200, get_resp.text
        assert get_resp.json()["status"] == "DRAFT"


@pytest.mark.asyncio
async def test_section_config_rejects_a_non_positive_time_budget():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        app.dependency_overrides[get_current_user_token_data] = lambda: _admin_payload

        job_resp = await client.post("/api/v1/admin/jobs", json={"title": "Invalid Budget Job"})
        job = job_resp.json()
        definition_id = job["definition"]["id"]

        section_resp = await client.post("/api/v1/admin/sections", json={
            "definition_id": definition_id, "section_type": "VERBAL", "order_index": 0,
            "config": {"time_budget_minutes": 0},
        })
        assert section_resp.status_code == 422, section_resp.text


@pytest.mark.asyncio
async def test_definition_duration_is_derived_from_section_time_budgets():
    """WR-A: Job/InterviewDefinition.duration_minutes is no longer an
    admin-set input — it's the SUM of each section's config.
    time_budget_minutes, recomputed on every section create/update/delete.
    Exercises the full recompute path live against the real DB, not a unit
    test of _recompute_duration in isolation."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        app.dependency_overrides[get_current_user_token_data] = lambda: _admin_payload

        job_resp = await client.post("/api/v1/admin/jobs", json={"title": "Derived Duration Job"})
        job = job_resp.json()
        job_id = job["id"]
        definition_id = job["definition"]["id"]
        # Deliberately not asserting duration_minutes before any section
        # exists — job/definition creation itself is out of WR-A's scope
        # (it only recomputes on section create/update/delete), so that
        # value is still whatever InterviewDefinition's DB column default
        # is, not yet a meaningful derived figure.

        verbal_resp = await client.post("/api/v1/admin/sections", json={
            "definition_id": definition_id, "section_type": "VERBAL", "order_index": 0,
            "config": {"time_budget_minutes": 10},
        })
        assert verbal_resp.status_code == 201, verbal_resp.text
        verbal_id = verbal_resp.json()["id"]

        get_resp = await client.get(f"/api/v1/admin/jobs/{job_id}")
        assert get_resp.json()["definition"]["duration_minutes"] == 10

        coding_resp = await client.post("/api/v1/admin/sections", json={
            "definition_id": definition_id, "section_type": "CODING", "order_index": 1,
            "config": {"time_budget_minutes": 20},
        })
        assert coding_resp.status_code == 201, coding_resp.text
        coding_id = coding_resp.json()["id"]

        get_resp = await client.get(f"/api/v1/admin/jobs/{job_id}")
        assert get_resp.json()["definition"]["duration_minutes"] == 30

        # Updating a budget recomputes too, not just create/delete.
        update_resp = await client.patch(f"/api/v1/admin/sections/{verbal_id}", json={
            "config": {"time_budget_minutes": 15},
        })
        assert update_resp.status_code == 200, update_resp.text
        get_resp = await client.get(f"/api/v1/admin/jobs/{job_id}")
        assert get_resp.json()["definition"]["duration_minutes"] == 35

        delete_resp = await client.delete(f"/api/v1/admin/sections/{coding_id}")
        assert delete_resp.status_code == 204, delete_resp.text
        get_resp = await client.get(f"/api/v1/admin/jobs/{job_id}")
        assert get_resp.json()["definition"]["duration_minutes"] == 15
