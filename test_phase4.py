"""
Phase 4 — Admin API tests.

Exercises the full admin CRUD flow: Jobs, Sections, Questions, plus
DRAFT/PUBLISHED enforcement and section-type uniqueness.  AI generation
is tested with a mock to avoid requiring a live GROQ_API_KEY.
"""
import pytest
import pytest_asyncio
import uuid
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.db.session import AsyncSessionLocal
from backend.models.profile import UserRole
from backend.api.deps import get_current_user_token_data

# ── Fixtures ───────────────────────────────────────────────────────────────

ADMIN_UUID = str(uuid.uuid4())

_admin_token_payload = {
    "sub": ADMIN_UUID,
    "email": "admin@path2hire.test",
    "type": "supabase",
}


@pytest_asyncio.fixture(autouse=True)
async def _seed_admin_role():
    """Ensure the admin UUID has a role row so get_current_admin passes."""
    async with AsyncSessionLocal() as session:
        from sqlalchemy.future import select
        stmt = select(UserRole).where(UserRole.user_id == uuid.UUID(ADMIN_UUID))
        result = await session.execute(stmt)
        if not result.scalar_one_or_none():
            session.add(UserRole(user_id=uuid.UUID(ADMIN_UUID), role="admin"))
            await session.commit()
    # Override the JWT dependency globally for all tests in this file
    app.dependency_overrides[get_current_user_token_data] = lambda: _admin_token_payload
    yield
    app.dependency_overrides.pop(get_current_user_token_data, None)


# ── Job CRUD ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_phase4_create_job():
    """POST /admin/jobs creates a Job + automatic InterviewDefinition."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/admin/jobs", json={
            "title": "Backend Engineer",
            "description": "Build APIs",
            "seniority": "mid",
            "required_skills": ["Python", "FastAPI"],
        })
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["title"] == "Backend Engineer"
        assert data["status"] == "DRAFT"
        # Definition must be auto-created
        assert data["definition"] is not None
        assert data["definition"]["duration_minutes"] == 15


@pytest.mark.asyncio
async def test_phase4_list_jobs():
    """GET /admin/jobs returns all jobs."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create a job first
        await client.post("/api/v1/admin/jobs", json={"title": "List Test Job"})
        resp = await client.get("/api/v1/admin/jobs")
        assert resp.status_code == 200
        jobs = resp.json()
        assert isinstance(jobs, list)
        assert any(j["title"] == "List Test Job" for j in jobs)


@pytest.mark.asyncio
async def test_phase4_get_job_detail():
    """GET /admin/jobs/{id} returns nested sections and questions."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post("/api/v1/admin/jobs", json={"title": "Detail Test"})
        job_id = create_resp.json()["id"]
        resp = await client.get(f"/api/v1/admin/jobs/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["definition"] is not None
        assert "sections" in data["definition"]


@pytest.mark.asyncio
async def test_phase4_update_job():
    """PATCH /admin/jobs/{id} updates a DRAFT job."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post("/api/v1/admin/jobs", json={"title": "Old Title"})
        job_id = create_resp.json()["id"]
        resp = await client.patch(f"/api/v1/admin/jobs/{job_id}", json={"title": "New Title"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "New Title"


@pytest.mark.asyncio
async def test_phase4_delete_draft_job():
    """DELETE /admin/jobs/{id} succeeds for DRAFT jobs."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post("/api/v1/admin/jobs", json={"title": "Delete Me"})
        job_id = create_resp.json()["id"]
        resp = await client.delete(f"/api/v1/admin/jobs/{job_id}")
        assert resp.status_code == 204
        # Confirm it's gone
        resp2 = await client.get(f"/api/v1/admin/jobs/{job_id}")
        assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_phase4_delete_published_job_blocked():
    """DELETE /admin/jobs/{id} returns 409 for PUBLISHED jobs."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post("/api/v1/admin/jobs", json={"title": "Published Job"})
        job_id = create_resp.json()["id"]
        # Publish it
        await client.post(f"/api/v1/admin/jobs/{job_id}/publish")
        # Try to delete
        resp = await client.delete(f"/api/v1/admin/jobs/{job_id}")
        assert resp.status_code == 409


# ── Publish / DRAFT enforcement ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_phase4_publish_job():
    """POST /admin/jobs/{id}/publish transitions DRAFT → PUBLISHED."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post("/api/v1/admin/jobs", json={"title": "Publishable"})
        job_id = create_resp.json()["id"]
        resp = await client.post(f"/api/v1/admin/jobs/{job_id}/publish")
        assert resp.status_code == 200
        assert resp.json()["status"] == "PUBLISHED"


@pytest.mark.asyncio
async def test_phase4_published_job_edit_blocked():
    """PATCH on a PUBLISHED job returns 409."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post("/api/v1/admin/jobs", json={"title": "Frozen"})
        job_id = create_resp.json()["id"]
        await client.post(f"/api/v1/admin/jobs/{job_id}/publish")
        resp = await client.patch(f"/api/v1/admin/jobs/{job_id}", json={"title": "Edited"})
        assert resp.status_code == 409


# ── Section CRUD + uniqueness ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_phase4_create_section():
    """POST /admin/sections creates a section on a DRAFT definition."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post("/api/v1/admin/jobs", json={"title": "Section Job"})
        def_id = create_resp.json()["definition"]["id"]
        resp = await client.post("/api/v1/admin/sections", json={
            "definition_id": def_id,
            "section_type": "VERBAL",
            "order_index": 0,
        })
        assert resp.status_code == 201
        assert resp.json()["section_type"] == "VERBAL"


@pytest.mark.asyncio
async def test_phase4_section_type_uniqueness():
    """Creating a duplicate section type on the same definition returns 409."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post("/api/v1/admin/jobs", json={"title": "Unique Job"})
        def_id = create_resp.json()["definition"]["id"]
        # First VERBAL — ok
        resp1 = await client.post("/api/v1/admin/sections", json={
            "definition_id": def_id,
            "section_type": "VERBAL",
            "order_index": 0,
        })
        assert resp1.status_code == 201
        # Second VERBAL — conflict
        resp2 = await client.post("/api/v1/admin/sections", json={
            "definition_id": def_id,
            "section_type": "VERBAL",
            "order_index": 1,
        })
        assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_phase4_section_on_published_blocked():
    """Creating a section on a PUBLISHED job returns 409."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post("/api/v1/admin/jobs", json={"title": "Pub Section"})
        job_id = create_resp.json()["id"]
        def_id = create_resp.json()["definition"]["id"]
        await client.post(f"/api/v1/admin/jobs/{job_id}/publish")
        resp = await client.post("/api/v1/admin/sections", json={
            "definition_id": def_id,
            "section_type": "CODING",
            "order_index": 0,
        })
        assert resp.status_code == 409


@pytest.mark.asyncio
async def test_phase4_delete_section():
    """DELETE /admin/sections/{id} removes a section from a DRAFT job."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post("/api/v1/admin/jobs", json={"title": "Del Section"})
        def_id = create_resp.json()["definition"]["id"]
        sec_resp = await client.post("/api/v1/admin/sections", json={
            "definition_id": def_id,
            "section_type": "MCQ",
            "order_index": 0,
        })
        section_id = sec_resp.json()["id"]
        resp = await client.delete(f"/api/v1/admin/sections/{section_id}")
        assert resp.status_code == 204


# ── Question CRUD ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_phase4_add_manual_question():
    """POST /admin/sections/{id}/questions adds a question manually."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post("/api/v1/admin/jobs", json={"title": "Q Job"})
        def_id = create_resp.json()["definition"]["id"]
        sec_resp = await client.post("/api/v1/admin/sections", json={
            "definition_id": def_id,
            "section_type": "VERBAL",
            "order_index": 0,
        })
        section_id = sec_resp.json()["id"]
        resp = await client.post(f"/api/v1/admin/sections/{section_id}/questions", json={
            "title": "Explain REST",
            "text": "What are the key principles of RESTful API design?",
            "competency": "API Design",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Explain REST"
        assert data["order_index"] == 0


@pytest.mark.asyncio
async def test_phase4_edit_question():
    """PATCH /admin/questions/{id} edits a question on a DRAFT job."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post("/api/v1/admin/jobs", json={"title": "Edit Q Job"})
        def_id = create_resp.json()["definition"]["id"]
        sec_resp = await client.post("/api/v1/admin/sections", json={
            "definition_id": def_id,
            "section_type": "VERBAL",
            "order_index": 0,
        })
        section_id = sec_resp.json()["id"]
        q_resp = await client.post(f"/api/v1/admin/sections/{section_id}/questions", json={
            "title": "Original",
            "text": "Original text",
        })
        question_id = q_resp.json()["id"]
        resp = await client.patch(f"/api/v1/admin/questions/{question_id}", json={
            "title": "Updated Title",
        })
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated Title"


@pytest.mark.asyncio
async def test_phase4_delete_question():
    """DELETE /admin/questions/{id} removes a question from a DRAFT job."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post("/api/v1/admin/jobs", json={"title": "Del Q Job"})
        def_id = create_resp.json()["definition"]["id"]
        sec_resp = await client.post("/api/v1/admin/sections", json={
            "definition_id": def_id,
            "section_type": "VERBAL",
            "order_index": 0,
        })
        section_id = sec_resp.json()["id"]
        q_resp = await client.post(f"/api/v1/admin/sections/{section_id}/questions", json={
            "title": "Deletable",
            "text": "Will be deleted",
        })
        question_id = q_resp.json()["id"]
        resp = await client.delete(f"/api/v1/admin/questions/{question_id}")
        assert resp.status_code == 204


@pytest.mark.asyncio
async def test_phase4_question_edit_on_published_blocked():
    """Editing a question on a PUBLISHED job returns 409."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post("/api/v1/admin/jobs", json={"title": "Pub Q Job"})
        job_id = create_resp.json()["id"]
        def_id = create_resp.json()["definition"]["id"]
        sec_resp = await client.post("/api/v1/admin/sections", json={
            "definition_id": def_id,
            "section_type": "VERBAL",
            "order_index": 0,
            # WR-A: time_budget_minutes is required at publish time —
            # without it, publish itself would 409 and this test would
            # actually be exercising "publish failed", not "question edit
            # blocked once published".
            "config": {"time_budget_minutes": 10},
        })
        section_id = sec_resp.json()["id"]
        q_resp = await client.post(f"/api/v1/admin/sections/{section_id}/questions", json={
            "title": "Frozen Q",
            "text": "Cannot be edited after publish",
        })
        question_id = q_resp.json()["id"]
        publish_resp = await client.post(f"/api/v1/admin/jobs/{job_id}/publish")
        assert publish_resp.status_code == 200, publish_resp.text
        resp = await client.patch(f"/api/v1/admin/questions/{question_id}", json={
            "title": "Should Fail",
        })
        assert resp.status_code == 409


# ── AI Generation (mocked) ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_phase4_generate_questions_mocked():
    """POST /admin/sections/{id}/generate-questions uses AI (mocked)."""
    mock_result = [
        {
            "title": "AI Generated Q1",
            "competency": "Python",
            "text": "Explain list comprehensions in Python.",
            "eval_criteria": {"excellent": "Clear, with examples", "poor": "Cannot explain"},
        },
        {
            "title": "AI Generated Q2",
            "competency": "FastAPI",
            "text": "How does dependency injection work in FastAPI?",
            "eval_criteria": {"excellent": "Deep understanding", "poor": "No awareness"},
        },
    ]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post("/api/v1/admin/jobs", json={
            "title": "AI Gen Job",
            "seniority": "mid",
            "required_skills": ["Python", "FastAPI"],
        })
        def_id = create_resp.json()["definition"]["id"]
        sec_resp = await client.post("/api/v1/admin/sections", json={
            "definition_id": def_id,
            "section_type": "VERBAL",
            "order_index": 0,
        })
        section_id = sec_resp.json()["id"]

        with patch(
            "backend.services.question_generator.generate_questions",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = await client.post(
                f"/api/v1/admin/sections/{section_id}/generate-questions",
                json={"num_questions": 2},
            )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert len(data) == 2
        assert data[0]["title"] == "AI Generated Q1"
        assert data[1]["order_index"] == 1


@pytest.mark.asyncio
async def test_phase4_regenerate_single_question_mocked():
    """POST /admin/questions/{id}/regenerate replaces question content via AI."""
    mock_result = [
        {
            "title": "Regenerated Title",
            "competency": "System Design",
            "text": "Design a rate limiter.",
            "eval_criteria": {"excellent": "Scalable solution"},
        },
    ]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post("/api/v1/admin/jobs", json={"title": "Regen Job"})
        def_id = create_resp.json()["definition"]["id"]
        sec_resp = await client.post("/api/v1/admin/sections", json={
            "definition_id": def_id,
            "section_type": "VERBAL",
            "order_index": 0,
        })
        section_id = sec_resp.json()["id"]
        q_resp = await client.post(f"/api/v1/admin/sections/{section_id}/questions", json={
            "title": "Old Title",
            "text": "Old text",
        })
        question_id = q_resp.json()["id"]

        with patch(
            "backend.services.question_generator.generate_questions",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = await client.post(f"/api/v1/admin/questions/{question_id}/regenerate")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Regenerated Title"
        assert resp.json()["text"] == "Design a rate limiter."


# ── Non-admin access blocked ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_phase4_non_admin_blocked():
    """Admin endpoints reject non-admin users."""
    non_admin_payload = {
        "sub": str(uuid.uuid4()),
        "email": "candidate@example.com",
        "type": "supabase",
    }
    app.dependency_overrides[get_current_user_token_data] = lambda: non_admin_payload
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/admin/jobs")
        assert resp.status_code == 403
    app.dependency_overrides[get_current_user_token_data] = lambda: _admin_token_payload
