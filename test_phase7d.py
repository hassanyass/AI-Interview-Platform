"""
Transition Phase 7, Sub-phase 7D — /load pipeline tests.

Verifies the new B2B path end-to-end against the real backend/DB: a Job ->
InterviewDefinition -> VERBAL InterviewSection -> ordered InterviewQuestion
rows, registered via the public-apply flow (which, per Phase 6, creates the
InterviewSession with job_id/definition_id set and NO InterviewConfiguration
row at all), comes back correctly through /internal/interviews/{id}/load as
ordered `sections`, with job_description/duration_minutes sourced from
Job/InterviewDefinition instead of the legacy InterviewConfiguration-era
defaults.
"""
import pytest
import pytest_asyncio
import uuid
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.db.session import AsyncSessionLocal
from backend.models.profile import UserRole
from backend.api.deps import get_current_user_token_data
from backend.core.config import settings

ADMIN_UUID = str(uuid.uuid4())
_admin_payload = {"sub": ADMIN_UUID, "email": "admin@path2hire.test", "type": "supabase"}
AGENT_HEADERS = {"x-agent-secret": settings.AGENT_API_SECRET}


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
async def test_phase7d_load_returns_ordered_verbal_sections_for_b2b_session():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        app.dependency_overrides[get_current_user_token_data] = lambda: _admin_payload

        job_resp = await client.post("/api/v1/admin/jobs", json={
            "title": "7D Test Backend Engineer",
            "description": "Build and operate our core payments API.",
            "seniority": "mid",
        })
        assert job_resp.status_code == 201, job_resp.text
        job = job_resp.json()
        job_id = job["id"]
        definition_id = job["definition"]["id"]

        patch_resp = await client.patch(f"/api/v1/admin/definitions/{definition_id}", json={
            "is_public": True,
        })
        assert patch_resp.status_code == 200, patch_resp.text
        public_token = patch_resp.json()["definition"]["public_access_token"]
        assert public_token

        # WR-A: duration_minutes is now DERIVED from section time budgets,
        # not admin-set directly — 42 here (deliberately differing from the
        # legacy 15-minute fallback) comes from this section's own config,
        # not a manual PATCH to InterviewDefinition.duration_minutes.
        section_resp = await client.post("/api/v1/admin/sections", json={
            "definition_id": definition_id, "section_type": "VERBAL", "order_index": 0,
            "config": {"time_budget_minutes": 42},
        })
        assert section_resp.status_code == 201, section_resp.text
        section_id = section_resp.json()["id"]

        q1_resp = await client.post(f"/api/v1/admin/sections/{section_id}/questions", json={
            "title": "Q1", "competency": "debugging",
            "text": "Tell me about a challenging bug you fixed.",
        })
        assert q1_resp.status_code == 201, q1_resp.text
        # Deliberately no competency on Q2 — exercises the null-competency
        # passthrough end to end (7A/7B/7C's null-competency handling).
        q2_resp = await client.post(f"/api/v1/admin/sections/{section_id}/questions", json={
            "title": "Q2", "text": "Explain REST API design principles.",
        })
        assert q2_resp.status_code == 201, q2_resp.text
        q1_id, q2_id = q1_resp.json()["id"], q2_resp.json()["id"]

        publish_resp = await client.post(f"/api/v1/admin/jobs/{job_id}/publish")
        assert publish_resp.status_code == 200, publish_resp.text

        app.dependency_overrides.pop(get_current_user_token_data, None)

        register_resp = await client.post(f"/api/v1/apply/{public_token}/register", json={
            "name": "Phase 7D Candidate",
            "email": f"7d-{uuid.uuid4().hex[:8]}@example.com",
        })
        assert register_resp.status_code == 200, register_resp.text
        session_id = register_resp.json()["session"]["id"]

        load_resp = await client.get(
            f"/api/v1/internal/interviews/{session_id}/load?agent_id=agent-7d-test",
            headers=AGENT_HEADERS,
        )
        assert load_resp.status_code == 200, load_resp.text
        payload = load_resp.json()

        # The core fix this sub-phase makes: B2B sessions have no
        # InterviewConfiguration row, so these must come from Job/
        # InterviewDefinition now, not the legacy 15-minute/no-JD fallback.
        assert payload["job_description"] == "Build and operate our core payments API."
        assert payload["duration_minutes"] == 42

        assert len(payload["sections"]) == 1
        section = payload["sections"][0]
        assert section["section_type"] == "VERBAL"
        # WR-A: the section's own time_budget_minutes round-trips through
        # /load's SectionPayload, sourced from InterviewSection.config.
        assert section["time_budget_minutes"] == 42
        assert [q["id"] for q in section["questions"]] == [q1_id, q2_id]
        assert section["questions"][0]["competency"] == "debugging"
        assert section["questions"][0]["text"] == "Tell me about a challenging bug you fixed."
        assert section["questions"][1]["competency"] is None

        # Legacy-session coverage (empty `sections`, InterviewConfiguration-
        # sourced job_description/duration_minutes) is already exercised by
        # test_phase3a.py's existing /load assertions — not duplicated here.
