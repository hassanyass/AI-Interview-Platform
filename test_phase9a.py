"""
Phase 9A — Config validation tests for CODING and MCQ question types.

Tests the validate_question_config enforcement on all manual write paths.
"""
import pytest
import pytest_asyncio
import uuid
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.db.session import AsyncSessionLocal
from backend.models.profile import UserRole
from backend.api.deps import get_current_user_token_data

# ── Fixtures ───────────────────────────────────────────────────────────────

ADMIN_UUID = str(uuid.uuid4())

_admin_token_payload = {
    "sub": ADMIN_UUID,
    "email": "admin-9a@path2hire.test",
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
    app.dependency_overrides[get_current_user_token_data] = lambda: _admin_token_payload
    yield
    app.dependency_overrides.pop(get_current_user_token_data, None)


async def _create_job_and_section(client: AsyncClient, section_type: str) -> tuple[str, str]:
    """Helper: create a DRAFT job, then add a section of the given type. Returns (section_id, definition_id)."""
    resp = await client.post("/api/v1/admin/jobs", json={
        "title": f"9A Test Job ({section_type})",
        "required_skills": ["Python"],
    })
    assert resp.status_code == 201, resp.text
    job = resp.json()
    definition_id = job["definition"]["id"]

    resp = await client.post("/api/v1/admin/sections", json={
        "definition_id": definition_id,
        "section_type": section_type,
        "order_index": 0,
    })
    assert resp.status_code == 201, resp.text
    section = resp.json()
    return section["id"], definition_id


# ── Test: VERBAL regression (no config) ────────────────────────────────────

@pytest.mark.asyncio
async def test_verbal_no_config_unaffected():
    """VERBAL question without config persists exactly as before."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        section_id, _ = await _create_job_and_section(client, "VERBAL")

        resp = await client.post(f"/api/v1/admin/sections/{section_id}/questions", json={
            "title": "Tell me about yourself",
            "text": "Describe your background.",
        })
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["config"] is None


@pytest.mark.asyncio
async def test_verbal_with_config_rejected():
    """VERBAL question WITH a config payload is rejected with 422."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        section_id, _ = await _create_job_and_section(client, "VERBAL")

        resp = await client.post(f"/api/v1/admin/sections/{section_id}/questions", json={
            "title": "Bad verbal question",
            "text": "This should not have config.",
            "config": {"starter_code": "x = 1", "supported_languages": ["python"], "constraints": "none"},
        })
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


# ── Test: CODING missing field ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_coding_missing_field_rejected():
    """CODING question with config missing required fields is rejected with 422."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        section_id, _ = await _create_job_and_section(client, "CODING")

        # Missing supported_languages and constraints
        resp = await client.post(f"/api/v1/admin/sections/{section_id}/questions", json={
            "title": "Two Sum",
            "text": "Given an array...",
            "config": {"starter_code": "def two_sum(nums, target):"},
        })
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_coding_valid_config_persists():
    """CODING question with a valid config persists correctly."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        section_id, _ = await _create_job_and_section(client, "CODING")

        resp = await client.post(f"/api/v1/admin/sections/{section_id}/questions", json={
            "title": "Two Sum",
            "text": "Given an array of integers, return indices of the two numbers that add up to a target.",
            "config": {
                "starter_code": "def two_sum(nums, target):\n    pass",
                "supported_languages": ["python", "javascript"],
                "constraints": "2 <= nums.length <= 10^4",
            },
        })
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["config"] is not None
        assert data["config"]["starter_code"] == "def two_sum(nums, target):\n    pass"
        assert data["config"]["supported_languages"] == ["python", "javascript"]
        assert data["config"]["constraints"] == "2 <= nums.length <= 10^4"


# ── Test: MCQ dangling reference ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_mcq_dangling_reference_rejected():
    """MCQ question with correct_answers referencing non-existent option ID is rejected."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        section_id, _ = await _create_job_and_section(client, "MCQ")

        resp = await client.post(f"/api/v1/admin/sections/{section_id}/questions", json={
            "title": "What is Python?",
            "text": "Which of the following best describes Python?",
            "config": {
                "options": [
                    {"id": "A", "text": "A programming language"},
                    {"id": "B", "text": "A snake"},
                ],
                "correct_answers": ["Z"],  # Z does not exist in options
                "is_multi_select": False,
            },
        })
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
        assert "non-existent option IDs" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_mcq_valid_config_persists():
    """MCQ question with valid config persists correctly and preserves option IDs."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        section_id, _ = await _create_job_and_section(client, "MCQ")

        resp = await client.post(f"/api/v1/admin/sections/{section_id}/questions", json={
            "title": "What is Python?",
            "text": "Which of the following best describes Python?",
            "config": {
                "options": [
                    {"id": "A", "text": "A programming language"},
                    {"id": "B", "text": "A snake"},
                    {"id": "C", "text": "A car brand"},
                    {"id": "D", "text": "A food item"},
                ],
                "correct_answers": ["A"],
                "is_multi_select": False,
            },
        })
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["config"] is not None
        assert len(data["config"]["options"]) == 4
        assert data["config"]["correct_answers"] == ["A"]
        assert data["config"]["is_multi_select"] is False
