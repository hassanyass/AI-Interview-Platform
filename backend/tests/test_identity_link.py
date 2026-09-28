"""H5-A: when a sign-in may adopt a profile that already exists.

`api/deps.py` resolves a Supabase identity to a CandidateProfile. When no
profile carries that `supabase_user_id` yet but one carries the same email,
it links them -- and that link hands over whatever the profile holds.

Two cases share that code path and they are not the same risk:

- HR creates an invitation, which creates a profile for the invited
  address; the candidate signs in to redeem it. The profile holds nothing.
  Refusing here would break personalized invitations outright.
- Someone applied through a public link as a guest, did an interview, and
  now a Supabase account appears with the same address. Linking hands over
  a stranger's transcript, CV and evaluation.

So the rule follows the data, not just the address, and
IDENTITY_AUTOLINK can override it in either direction.
"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from backend.api.deps import get_current_user_token_data
from backend.core.config import settings
from backend.db.session import AsyncSessionLocal
from backend.main import app
from backend.models.interview import InterviewSession
from backend.models.profile import CandidateProfile

PROBE = "/api/v1/profiles/me"


def token(email: str, *, verified=None, sub=None) -> dict:
    data = {"sub": sub or str(uuid.uuid4()), "email": email, "type": "supabase"}
    if verified is not None:
        data["email_verified"] = verified
    return data


@pytest_asyncio.fixture
async def make_profile():
    """Creates profiles (optionally with interview history) and removes
    everything it created."""
    created_profiles, created_sessions = [], []

    async def _make(*, email: str, with_history: bool = False):
        """Returns the profile's id -- a plain UUID, not an ORM instance,
        which would be detached once this session closes."""
        async with AsyncSessionLocal() as db:
            profile = CandidateProfile(email=email, full_name="Prior Candidate", supabase_user_id=None)
            db.add(profile)
            await db.commit()
            await db.refresh(profile)
            profile_id = profile.id
            created_profiles.append(profile_id)
            if with_history:
                session = InterviewSession(
                    candidate_profile_id=profile_id, role="Backend Engineer",
                    level="mid", language="en", status="COMPLETED",
                )
                db.add(session)
                await db.commit()
                await db.refresh(session)
                created_sessions.append(session.id)
            return profile_id

    yield _make

    async with AsyncSessionLocal() as db:
        if created_sessions:
            await db.execute(delete(InterviewSession).where(InterviewSession.id.in_(created_sessions)))
        if created_profiles:
            await db.execute(delete(CandidateProfile).where(CandidateProfile.id.in_(created_profiles)))
        await db.commit()


@pytest_asyncio.fixture
async def as_identity():
    """Signs in as a given token payload, without going through the real
    verifier (which test_token_verification.py covers)."""
    clients = []

    async def _as(token_data: dict) -> AsyncClient:
        app.dependency_overrides[get_current_user_token_data] = lambda: token_data
        c = AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test")
        clients.append(c)
        return c

    yield _as
    for c in clients:
        await c.aclose()
    app.dependency_overrides.pop(get_current_user_token_data, None)


async def linked_profile_id(profile_id) -> str | None:
    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(CandidateProfile.supabase_user_id).where(CandidateProfile.id == profile_id)
        )).scalar_one_or_none()
    return str(row) if row else None


# ── the flows the product depends on ──────────────────────────────────────

@pytest.mark.asyncio
async def test_an_invited_candidate_adopts_the_profile_hr_created_for_them(make_profile, as_identity):
    """The profile holds nothing yet, so there is nothing to hand over.
    This is the personalized-invitation path."""
    email = f"invited-{uuid.uuid4().hex[:8]}@example.dev"
    profile_id = await make_profile(email=email)
    identity = token(email)                      # no verification claim at all

    client = await as_identity(identity)
    response = await client.get(PROBE)

    assert response.status_code == 200
    assert response.json()["id"] == str(profile_id)
    assert await linked_profile_id(profile_id) == identity["sub"]


@pytest.mark.asyncio
async def test_a_verified_address_adopts_its_profile_even_with_history(make_profile, as_identity):
    email = f"verified-{uuid.uuid4().hex[:8]}@example.dev"
    profile_id = await make_profile(email=email, with_history=True)

    client = await as_identity(token(email, verified=True))
    response = await client.get(PROBE)

    assert response.status_code == 200 and response.json()["id"] == str(profile_id)


# ── the case this phase exists to stop ────────────────────────────────────

@pytest.mark.asyncio
async def test_an_unproven_address_cannot_adopt_a_profile_that_did_an_interview(make_profile, as_identity):
    email = f"stranger-{uuid.uuid4().hex[:8]}@example.dev"
    profile_id = await make_profile(email=email, with_history=True)

    client = await as_identity(token(email))     # token says nothing about verification
    response = await client.get(PROBE)

    assert response.status_code == 403
    assert "already has interview history" in response.json()["detail"]
    assert await linked_profile_id(profile_id) is None, "the profile must be left untouched"


@pytest.mark.asyncio
async def test_an_address_the_token_says_is_unverified_is_refused_too(make_profile, as_identity):
    email = f"unverified-{uuid.uuid4().hex[:8]}@example.dev"
    profile_id = await make_profile(email=email, with_history=True)

    client = await as_identity(token(email, verified=False))
    assert (await client.get(PROBE)).status_code == 403
    assert await linked_profile_id(profile_id) is None


# ── the policy switch ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_always_restores_the_pre_h5a_behaviour(make_profile, as_identity, monkeypatch):
    monkeypatch.setattr(settings, "IDENTITY_AUTOLINK", "always")
    email = f"always-{uuid.uuid4().hex[:8]}@example.dev"
    profile_id = await make_profile(email=email, with_history=True)

    client = await as_identity(token(email))
    assert (await client.get(PROBE)).status_code == 200
    assert await linked_profile_id(profile_id) is not None


@pytest.mark.asyncio
async def test_never_refuses_even_an_empty_profile(make_profile, as_identity, monkeypatch):
    monkeypatch.setattr(settings, "IDENTITY_AUTOLINK", "never")
    email = f"never-{uuid.uuid4().hex[:8]}@example.dev"
    profile_id = await make_profile(email=email)

    client = await as_identity(token(email))
    # Nothing to adopt and nothing may be created under this address either:
    # the insert collides with the existing row's unique email.
    assert (await client.get(PROBE)).status_code in (403, 500)
    assert await linked_profile_id(profile_id) is None


# ── unrelated identities are unaffected ───────────────────────────────────

@pytest.mark.asyncio
async def test_a_guest_token_resolves_to_its_own_subject_and_links_nothing(make_profile, as_identity):
    email = f"guest-{uuid.uuid4().hex[:8]}@example.dev"
    profile_id = await make_profile(email=email, with_history=True)

    client = await as_identity({"sub": str(profile_id), "email": email, "type": "guest", "email_verified": False})
    response = await client.get(PROBE)

    assert response.status_code == 200 and response.json()["id"] == str(profile_id)
    assert await linked_profile_id(profile_id) is None, "a guest token must not write a supabase_user_id"


@pytest.mark.asyncio
async def test_a_new_address_still_gets_its_own_profile(as_identity):
    email = f"brand-new-{uuid.uuid4().hex[:8]}@example.dev"
    client = await as_identity(token(email))
    response = await client.get(PROBE)
    assert response.status_code == 200

    async with AsyncSessionLocal() as db:
        await db.execute(delete(CandidateProfile).where(CandidateProfile.email == email))
        await db.commit()
