"""
Phase 6, Sub-phase 6C — Public link flow (Flow B) tests.

No JWT mocking needed here at all — that's the whole point of the guest
flow: this endpoint MINTS the guest JWT, it doesn't consume one. Real HTTP
calls throughout.
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


async def _create_published_public_job(client: AsyncClient, title: str) -> tuple[str, str]:
    """Admin creates a job, makes it public, and publishes it.
    Returns (public_access_token, job_id)."""
    app.dependency_overrides[get_current_user_token_data] = lambda: _admin_payload

    job_resp = await client.post("/api/v1/admin/jobs", json={"title": title})
    assert job_resp.status_code == 201, job_resp.text
    job = job_resp.json()
    definition_id = job["definition"]["id"]

    patch_resp = await client.patch(
        f"/api/v1/admin/definitions/{definition_id}", json={"is_public": True}
    )
    assert patch_resp.status_code == 200, patch_resp.text
    public_token = patch_resp.json()["definition"]["public_access_token"]
    assert public_token

    publish_resp = await client.post(f"/api/v1/admin/jobs/{job['id']}/publish")
    assert publish_resp.status_code == 200, publish_resp.text

    app.dependency_overrides.pop(get_current_user_token_data, None)
    return public_token, job["id"]


@pytest.mark.asyncio
async def test_phase6c_get_apply_context():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        public_token, _job_id = await _create_published_public_job(client, "6C Test Job")
        resp = await client.get(f"/api/v1/apply/{public_token}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["job_title"] == "6C Test Job"


@pytest.mark.asyncio
async def test_phase6c_rejects_non_public_or_unpublished():
    """A definition that's public but whose job isn't PUBLISHED yet must be
    rejected — the stricter check 6C adds beyond the legacy endpoint."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        app.dependency_overrides[get_current_user_token_data] = lambda: _admin_payload

        # Public, but never published.
        job_resp = await client.post("/api/v1/admin/jobs", json={"title": "Never Published"})
        job = job_resp.json()
        definition_id = job["definition"]["id"]
        patch_resp = await client.patch(
            f"/api/v1/admin/definitions/{definition_id}", json={"is_public": True}
        )
        public_token = patch_resp.json()["definition"]["public_access_token"]
        app.dependency_overrides.pop(get_current_user_token_data, None)

        resp = await client.get(f"/api/v1/apply/{public_token}")
        assert resp.status_code == 403, resp.text

        reg_resp = await client.post(
            f"/api/v1/apply/{public_token}/register",
            json={"name": "Someone", "email": "someone@example.dev"},
        )
        assert reg_resp.status_code == 403, reg_resp.text


@pytest.mark.asyncio
async def test_phase6c_rejects_not_public():
    """A PUBLISHED job that was never made public must also be rejected."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        app.dependency_overrides[get_current_user_token_data] = lambda: _admin_payload
        job_resp = await client.post("/api/v1/admin/jobs", json={"title": "Not Public"})
        job = job_resp.json()
        await client.post(f"/api/v1/admin/jobs/{job['id']}/publish")
        app.dependency_overrides.pop(get_current_user_token_data, None)

        # No public_access_token exists at all for this definition (never
        # toggled is_public) — use a nonsense token, must 404/403, not 200.
        resp = await client.get("/api/v1/apply/not-a-real-token")
        assert resp.status_code in (403, 404), resp.text


@pytest.mark.asyncio
async def test_phase6c_stop_condition_repeat_registration():
    """The actual 6C stop condition: registering twice with the same email
    resolves to the SAME CandidateProfile and the SAME JobApplication, but
    produces two DISTINCT InterviewSession ids."""
    transport = ASGITransport(app=app)
    email = "phase6c.repeat@example.dev"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        public_token, job_id = await _create_published_public_job(client, "6C Repeat Job")

        first = await client.post(
            f"/api/v1/apply/{public_token}/register",
            json={"name": "Repeat Candidate", "email": email},
        )
        assert first.status_code == 200, first.text
        first_body = first.json()
        assert first_body["access_token"]
        assert first_body["livekit_token"]

        second = await client.post(
            f"/api/v1/apply/{public_token}/register",
            json={"name": "Repeat Candidate", "email": email},
        )
        assert second.status_code == 200, second.text
        second_body = second.json()

        # Distinct sessions.
        assert first_body["session"]["id"] != second_body["session"]["id"]

        async with AsyncSessionLocal() as db:
            from sqlalchemy.future import select
            from backend.models.profile import CandidateProfile
            from backend.models.interview import JobApplication, InterviewSession

            profiles = (
                await db.execute(select(CandidateProfile).where(CandidateProfile.email == email))
            ).scalars().all()
            assert len(profiles) == 1, "must resolve to exactly one CandidateProfile"
            profile = profiles[0]

            # Scoped by job_id, not just candidate_profile_id: this suite
            # runs against the shared dev DB (not a fresh DB per test), and
            # a prior run of this same test file (fixed email, different
            # job id each run) can leave other JobApplication rows for this
            # same profile against DIFFERENT jobs. The stop condition is
            # "same JobApplication for THIS job", not "only one
            # JobApplication ever, for any job" — the unscoped query was a
            # test bug, not a product bug (confirmed via a real full-suite
            # failure this pass caught).
            applications = (
                await db.execute(
                    select(JobApplication).where(
                        JobApplication.candidate_profile_id == profile.id,
                        JobApplication.job_id == uuid.UUID(job_id),
                    )
                )
            ).scalars().all()
            assert len(applications) == 1, "must resolve to exactly one JobApplication for this job"

            sessions = (
                await db.execute(
                    select(InterviewSession).where(InterviewSession.application_id == applications[0].id)
                )
            ).scalars().all()
            assert len(sessions) == 2, "each registration must produce its own new session"
