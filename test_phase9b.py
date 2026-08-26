"""
Transition Phase 9, Sub-phase 9B — closing verification items + Phase 9A
hints addendum tests.

Item 1: proves InterviewSection.order_index (admin-configurable via the
Phase 5 reorder UI, PATCH /admin/sections/{id}) is what /load's `sections`
order and _active_core_section()'s walk actually follow -- not creation
order or query order -- when MULTIPLE section types exist on one
definition.

Deliberately bypasses the still-active Phase 7 CODING/MCQ publish stopgap
(see admin.py's publish_job) and the public-apply job-status gate by
inserting the CandidateProfile/InterviewSession rows directly via the DB
session, rather than going through publish_job/register. That stopgap is
an orthogonal, still-intentional guard for candidate-facing registration
(per Phase 9 standing rule 6, it stays in place per-type until that
type's own 9F sub-phase explicitly closes it) -- unrelated to what this
test verifies, which is purely /load + build_core_sections() +
_active_core_section() ordering. Sections are still authored through the
REAL admin API (create + reorder), and /load is exercised through the
REAL internal endpoint.

Item 2 (multi-section-type ordered walk, mirroring 7F's pattern) lives in
agent/test_skip_regressions.py -- a controller-only concern, not a
backend/DB one.

Also covers the Phase 9A addendum: CodingConfig.hints round-trips through
all four config write paths (manual create, manual update, AI generate,
regenerate) -- Phase 9 standing rule 1.
"""
import uuid
import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.db.session import AsyncSessionLocal
from backend.models.profile import UserRole, CandidateProfile
from backend.models.interview import InterviewSession
from backend.api.deps import get_current_user_token_data
from backend.core.config import settings

ADMIN_UUID = str(uuid.uuid4())
_admin_payload = {"sub": ADMIN_UUID, "email": "admin-9b@path2hire.test", "type": "supabase"}
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
    app.dependency_overrides[get_current_user_token_data] = lambda: _admin_payload
    yield
    app.dependency_overrides.pop(get_current_user_token_data, None)


# ═══════════════════════════════════════════════════════════════════════════
# Item 1 — admin-configured order_index survives /load + _active_core_section()
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_9b_reordered_multi_type_sections_walk_in_admin_configured_order():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_resp = await client.post("/api/v1/admin/jobs", json={
            "title": "9B Reorder Test Engineer",
            "seniority": "mid",
        })
        assert job_resp.status_code == 201, job_resp.text
        job = job_resp.json()
        job_id = job["id"]
        definition_id = job["definition"]["id"]

        # Created in this order: VERBAL(0), CODING(1), MCQ(2) -- the default,
        # creation-order sequence this test must NOT rely on.
        verbal_resp = await client.post("/api/v1/admin/sections", json={
            "definition_id": definition_id, "section_type": "VERBAL", "order_index": 0,
        })
        assert verbal_resp.status_code == 201, verbal_resp.text
        coding_resp = await client.post("/api/v1/admin/sections", json={
            "definition_id": definition_id, "section_type": "CODING", "order_index": 1,
        })
        assert coding_resp.status_code == 201, coding_resp.text
        mcq_resp = await client.post("/api/v1/admin/sections", json={
            "definition_id": definition_id, "section_type": "MCQ", "order_index": 2,
        })
        assert mcq_resp.status_code == 201, mcq_resp.text
        verbal_id = verbal_resp.json()["id"]
        coding_id = coding_resp.json()["id"]
        mcq_id = mcq_resp.json()["id"]

        q1 = await client.post(f"/api/v1/admin/sections/{verbal_id}/questions", json={
            "title": "Tell me about yourself", "text": "Describe your background.",
        })
        assert q1.status_code == 201, q1.text
        q2 = await client.post(f"/api/v1/admin/sections/{coding_id}/questions", json={
            "title": "Two Sum", "text": "Given an array, return indices that sum to target.",
            "config": {
                "starter_code": "def two_sum(nums, target):\n    pass",
                "supported_languages": ["python"],
                "constraints": "2 <= nums.length <= 10^4",
            },
        })
        assert q2.status_code == 201, q2.text
        q3 = await client.post(f"/api/v1/admin/sections/{mcq_id}/questions", json={
            "title": "What is Python?", "text": "Which best describes Python?",
            "config": {
                "options": [{"id": "A", "text": "A language"}, {"id": "B", "text": "A snake"}],
                "correct_answers": ["A"], "is_multi_select": False,
            },
        })
        assert q3.status_code == 201, q3.text

        # Reorder to a deliberately NON-creation-order sequence: MCQ, CODING, VERBAL.
        r1 = await client.patch(f"/api/v1/admin/sections/{mcq_id}", json={"order_index": 0})
        assert r1.status_code == 200, r1.text
        r2 = await client.patch(f"/api/v1/admin/sections/{coding_id}", json={"order_index": 1})
        assert r2.status_code == 200, r2.text
        r3 = await client.patch(f"/api/v1/admin/sections/{verbal_id}", json={"order_index": 2})
        assert r3.status_code == 200, r3.text

        # NOTE: deliberately does NOT call POST /jobs/{id}/publish. That
        # endpoint's Phase-7 stopgap guard still (per Phase 9 standing rule
        # 6) rejects publishing any CODING/MCQ section -- an unrelated,
        # still-active guard this test must not exercise or route around.
        # Instead, seed a resumable InterviewSession directly, exactly as
        # publish_job + the public-apply flow would leave one, so /load
        # (the real endpoint under test) runs completely unmodified.
        candidate_id = uuid.uuid4()
        session_id = uuid.uuid4()
        async with AsyncSessionLocal() as db:
            db.add(CandidateProfile(
                id=candidate_id, full_name="9B Candidate",
                email=f"9b-{uuid.uuid4().hex[:8]}@example.com",
            ))
            db.add(InterviewSession(
                id=session_id, candidate_profile_id=candidate_id,
                job_id=uuid.UUID(job_id), definition_id=uuid.UUID(definition_id),
                role="Backend Engineer", level="mid", language="en", status="CREATED",
            ))
            await db.commit()

        load_resp = await client.get(
            f"/api/v1/internal/interviews/{session_id}/load?agent_id=agent-9b-test",
            headers=AGENT_HEADERS,
        )
        assert load_resp.status_code == 200, load_resp.text
        payload = load_resp.json()

        # The actual admin-configured order, not creation order (VERBAL,
        # CODING, MCQ) and not alphabetical order (CODING, MCQ, VERBAL).
        assert [s["section_type"] for s in payload["sections"]] == ["MCQ", "CODING", "VERBAL"]

        from agent.main import build_core_sections
        built = build_core_sections(payload)
        assert list(built.keys()) == ["MCQ", "CODING", "VERBAL"]

        from agent.interview.controller import InterviewController
        from agent.interview.models import InterviewRuntimeContext, InterviewPhase
        from agent.interview.persistence import MockPersistence

        context = InterviewRuntimeContext(
            session_id=str(session_id), candidate_id=str(candidate_id),
            role="Backend Engineer", confirmed_level="mid", language="en",
            current_phase=InterviewPhase.BACKGROUND, time_remaining_seconds=1800,
            sections=built,
        )
        controller = InterviewController(object(), MockPersistence(), context)

        # Walk _active_core_section() exactly as the controller does in
        # production, completing each section to reveal the next -- this
        # proves the WALK ORDER itself, not just the payload/dict order.
        walked = []
        section = controller._active_core_section()
        while section is not None:
            walked.append(section.section_type)
            section.completed = True
            section = controller._active_core_section()

        assert walked == ["MCQ", "CODING", "VERBAL"]


# ═══════════════════════════════════════════════════════════════════════════
# Phase 9A addendum — CodingConfig.hints round-trips at all 4 write paths
# ═══════════════════════════════════════════════════════════════════════════

async def _create_coding_section(client: AsyncClient) -> tuple[str, str]:
    resp = await client.post("/api/v1/admin/jobs", json={
        "title": "9B Hints Test Job", "seniority": "mid",
    })
    assert resp.status_code == 201, resp.text
    job = resp.json()
    definition_id = job["definition"]["id"]
    sec_resp = await client.post("/api/v1/admin/sections", json={
        "definition_id": definition_id, "section_type": "CODING", "order_index": 0,
    })
    assert sec_resp.status_code == 201, sec_resp.text
    return sec_resp.json()["id"], definition_id


_VALID_CODING_CONFIG = {
    "starter_code": "def two_sum(nums, target):\n    pass",
    "supported_languages": ["python"],
    "constraints": "2 <= nums.length <= 10^4",
    "hints": [
        "Consider a hash map of values you've already seen.",
        "What's the complement of the current number relative to the target?",
    ],
}


@pytest.mark.asyncio
async def test_9a_addendum_manual_create_round_trips_hints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        section_id, _ = await _create_coding_section(client)
        resp = await client.post(f"/api/v1/admin/sections/{section_id}/questions", json={
            "title": "Two Sum", "text": "Given an array...", "config": _VALID_CODING_CONFIG,
        })
        assert resp.status_code == 201, resp.text
        assert resp.json()["config"]["hints"] == _VALID_CODING_CONFIG["hints"]


@pytest.mark.asyncio
async def test_9a_addendum_manual_update_round_trips_hints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        section_id, _ = await _create_coding_section(client)
        create_resp = await client.post(f"/api/v1/admin/sections/{section_id}/questions", json={
            "title": "Two Sum", "text": "Given an array...",
            "config": {**_VALID_CODING_CONFIG, "hints": []},
        })
        assert create_resp.status_code == 201, create_resp.text
        question_id = create_resp.json()["id"]

        update_resp = await client.patch(f"/api/v1/admin/questions/{question_id}", json={
            "config": _VALID_CODING_CONFIG,
        })
        assert update_resp.status_code == 200, update_resp.text
        assert update_resp.json()["config"]["hints"] == _VALID_CODING_CONFIG["hints"]


@pytest.mark.asyncio
async def test_9a_addendum_ai_generate_round_trips_hints():
    mock_result = [{
        "title": "AI Two Sum", "competency": "algorithms",
        "text": "Given an array of integers, return indices of the two numbers that add up to a target.",
        "eval_criteria": {
            "time_complexity": "O(n)", "space_complexity": "O(n)",
            "edge_cases": [], "rubric": "Award credit for a correct hash-map approach.",
        },
        "config": _VALID_CODING_CONFIG,
    }]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        section_id, _ = await _create_coding_section(client)
        with patch(
            "backend.services.question_generator.generate_questions",
            new_callable=AsyncMock, return_value=mock_result,
        ):
            resp = await client.post(
                f"/api/v1/admin/sections/{section_id}/generate-questions",
                json={"num_questions": 1},
            )
        assert resp.status_code == 201, resp.text
        assert resp.json()[0]["config"]["hints"] == _VALID_CODING_CONFIG["hints"]


@pytest.mark.asyncio
async def test_9a_addendum_regenerate_round_trips_hints():
    mock_result = [{
        "title": "Regenerated Two Sum", "competency": "algorithms",
        "text": "Design a rate limiter.",
        "eval_criteria": {
            "time_complexity": "O(1)", "space_complexity": "O(n)",
            "edge_cases": [], "rubric": "Award credit for correct bucket sizing.",
        },
        "config": _VALID_CODING_CONFIG,
    }]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        section_id, _ = await _create_coding_section(client)
        create_resp = await client.post(f"/api/v1/admin/sections/{section_id}/questions", json={
            "title": "Old", "text": "Old text", "config": {**_VALID_CODING_CONFIG, "hints": []},
        })
        assert create_resp.status_code == 201, create_resp.text
        question_id = create_resp.json()["id"]

        with patch(
            "backend.services.question_generator.generate_questions",
            new_callable=AsyncMock, return_value=mock_result,
        ):
            resp = await client.post(f"/api/v1/admin/questions/{question_id}/regenerate")
        assert resp.status_code == 200, resp.text
        assert resp.json()["config"]["hints"] == _VALID_CODING_CONFIG["hints"]


@pytest.mark.asyncio
async def test_9a_addendum_omitted_hints_defaults_to_empty_list_additive():
    """Additive-only requirement: existing CODING configs authored before
    this addendum (no `hints` key at all) must keep validating exactly as
    9A originally shipped them -- not start requiring hints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        section_id, _ = await _create_coding_section(client)
        resp = await client.post(f"/api/v1/admin/sections/{section_id}/questions", json={
            "title": "No Hints Question", "text": "Given an array...",
            "config": {
                "starter_code": "def f(): pass",
                "supported_languages": ["python"],
                "constraints": "n <= 100",
            },
        })
        assert resp.status_code == 201, resp.text
        assert resp.json()["config"]["hints"] == []


@pytest.mark.asyncio
async def test_9a_addendum_malformed_hints_rejected():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        section_id, _ = await _create_coding_section(client)
        resp = await client.post(f"/api/v1/admin/sections/{section_id}/questions", json={
            "title": "Bad Hints", "text": "Given an array...",
            "config": {
                "starter_code": "def f(): pass",
                "supported_languages": ["python"],
                "constraints": "n <= 100",
                "hints": [123, "ok hint"],  # not all strings
            },
        })
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
