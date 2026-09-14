"""
Phase 6, Sub-phase 6B — Personalized redemption flow tests.

Mirrors Phase 3's OTP-mock test pattern exactly (test_phase3.py's
test_phase3_otp_flow_mock): does not mock signInWithOtp/verifyOtp (those
are frontend-only Supabase calls), it mocks the *end result* by overriding
the get_current_user_token_data FastAPI dependency with a plain
{sub, email, type} payload, simulating an already-verified Supabase JWT.
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


async def _create_job_and_invitation(client: AsyncClient, email: str, language: str | None = None) -> dict:
    """Admin creates a job (optionally with a given language) and invites
    `email`. Returns the invitation dict."""
    app.dependency_overrides[get_current_user_token_data] = lambda: _admin_payload

    job_payload = {"title": "6B Test Job"}
    if language is not None:
        job_payload["language"] = language
    job_resp = await client.post("/api/v1/admin/jobs", json=job_payload)
    assert job_resp.status_code == 201, job_resp.text
    job = job_resp.json()
    definition_id = job["definition"]["id"]

    inv_resp = await client.post(
        f"/api/v1/admin/definitions/{definition_id}/invitations",
        json={"candidate_email": email},
    )
    assert inv_resp.status_code == 201, inv_resp.text
    return inv_resp.json()


@pytest.mark.asyncio
async def test_phase6b_happy_path_redeem():
    """Full flow: invite -> GET opens it -> POST redeems it -> session + LiveKit token."""
    transport = ASGITransport(app=app)
    email = "phase6b.happy@example.test"
    candidate_supabase_id = str(uuid.uuid4())

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        invitation = await _create_job_and_invitation(client, email)
        assert invitation["status"] == "INVITED"
        token = invitation["token"]
        application_id = invitation["application_id"]

        # GET as an anonymous candidate — no auth override needed, it's public.
        app.dependency_overrides.pop(get_current_user_token_data, None)
        get_resp = await client.get(f"/api/v1/invitations/{token}")
        assert get_resp.status_code == 200, get_resp.text
        assert get_resp.json()["invitation_status"] == "OPENED"
        assert get_resp.json()["job_title"] == "6B Test Job"

        # Redeem as the correctly-identified candidate.
        app.dependency_overrides[get_current_user_token_data] = lambda: {
            "sub": candidate_supabase_id,
            "email": email,
            "type": "supabase",
        }
        redeem_resp = await client.post(f"/api/v1/invitations/{token}/redeem")
        assert redeem_resp.status_code == 200, redeem_resp.text
        body = redeem_resp.json()
        assert body["session"]["status"] == "CREATED"
        assert body["livekit_token"]
        assert body["livekit_url"]
        session_id = body["session"]["id"]

        # Confirm the JobApplication reused is the SAME one 6A created.
        async with AsyncSessionLocal() as db:
            from sqlalchemy.future import select
            from backend.models.interview import InterviewInvitation, InterviewSession, JobApplication

            inv_row = (
                await db.execute(select(InterviewInvitation).where(InterviewInvitation.token == token))
            ).scalar_one()
            assert inv_row.status == "STARTED"

            session_row = (
                await db.execute(select(InterviewSession).where(InterviewSession.id == uuid.UUID(session_id)))
            ).scalar_one()
            assert str(session_row.application_id) == application_id

            app_count = (
                await db.execute(select(JobApplication).where(JobApplication.id == uuid.UUID(application_id)))
            ).scalars().all()
            assert len(app_count) == 1


@pytest.mark.asyncio
async def test_phase6b_email_mismatch_is_hard_rejected():
    """A JWT for a different email than the invitation must be rejected with 403,
    and must not touch the invitation's status at all."""
    transport = ASGITransport(app=app)
    email = "phase6b.owner@example.test"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        invitation = await _create_job_and_invitation(client, email)
        token = invitation["token"]

        app.dependency_overrides[get_current_user_token_data] = lambda: {
            "sub": str(uuid.uuid4()),
            "email": "someone.else@example.test",
            "type": "supabase",
        }
        resp = await client.post(f"/api/v1/invitations/{token}/redeem")
        assert resp.status_code == 403, resp.text

        async with AsyncSessionLocal() as db:
            from sqlalchemy.future import select
            from backend.models.interview import InterviewInvitation

            inv_row = (
                await db.execute(select(InterviewInvitation).where(InterviewInvitation.token == token))
            ).scalar_one()
            # Never opened via GET in this test, so it must still be INVITED —
            # the rejected redeem attempt must not have advanced it at all.
            assert inv_row.status == "INVITED"


@pytest.mark.asyncio
async def test_phase6b_guest_token_is_hard_rejected():
    """A guest-type JWT (self-asserted, no OTP) must be rejected even if the
    email matches exactly — only a real Supabase-verified token is accepted."""
    transport = ASGITransport(app=app)
    email = "phase6b.guest@example.test"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        invitation = await _create_job_and_invitation(client, email)
        token = invitation["token"]

        app.dependency_overrides[get_current_user_token_data] = lambda: {
            "sub": str(uuid.uuid4()),
            "email": email,  # matches exactly
            "type": "guest",  # but not Supabase-verified
        }
        resp = await client.post(f"/api/v1/invitations/{token}/redeem")
        assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_phase6b_redeem_is_idempotent_once_started():
    """Calling /redeem again on an already-STARTED invitation must return the
    SAME session (a fresh LiveKit token is fine), not create a duplicate."""
    transport = ASGITransport(app=app)
    email = "phase6b.idempotent@example.test"
    candidate_supabase_id = str(uuid.uuid4())

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        invitation = await _create_job_and_invitation(client, email)
        token = invitation["token"]

        app.dependency_overrides[get_current_user_token_data] = lambda: {
            "sub": candidate_supabase_id,
            "email": email,
            "type": "supabase",
        }
        first = await client.post(f"/api/v1/invitations/{token}/redeem")
        assert first.status_code == 200, first.text
        first_session_id = first.json()["session"]["id"]

        second = await client.post(f"/api/v1/invitations/{token}/redeem")
        assert second.status_code == 200, second.text
        second_session_id = second.json()["session"]["id"]

        assert first_session_id == second_session_id

        async with AsyncSessionLocal() as db:
            from sqlalchemy.future import select
            from backend.models.interview import InterviewSession

            sessions = (
                await db.execute(
                    select(InterviewSession).where(InterviewSession.id == uuid.UUID(first_session_id))
                )
            ).scalars().all()
            assert len(sessions) == 1


@pytest.mark.asyncio
async def test_phase6b_redeem_uses_job_language_not_hardcoded_en():
    """A job created with language='ar' must produce an InterviewSession
    with language='ar' on redeem — not the old hardcoded 'en' placeholder."""
    transport = ASGITransport(app=app)
    email = "phase6b.arabic@example.test"
    candidate_supabase_id = str(uuid.uuid4())

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        invitation = await _create_job_and_invitation(client, email, language="ar")

        app.dependency_overrides[get_current_user_token_data] = lambda: {
            "sub": candidate_supabase_id,
            "email": email,
            "type": "supabase",
        }
        redeem_resp = await client.post(f"/api/v1/invitations/{invitation['token']}/redeem")
        assert redeem_resp.status_code == 200, redeem_resp.text
        session_id = redeem_resp.json()["session"]["id"]

        async with AsyncSessionLocal() as db:
            from sqlalchemy.future import select
            from backend.models.interview import InterviewSession

            session_row = (
                await db.execute(select(InterviewSession).where(InterviewSession.id == uuid.UUID(session_id)))
            ).scalar_one()
            assert session_row.language == "ar", f"expected 'ar', got {session_row.language!r}"
