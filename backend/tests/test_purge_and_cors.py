"""H5-C: the purge job is built and switched off, and CORS has to be said
out loud in production.

The purge is the mechanism for a retention policy that does not exist yet
(U1). Shipping it enabled would mean deploying the code silently starts
erasing candidate data on a timer, which is precisely the decision that
was deferred -- so the refusal to run is itself a tested behaviour.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

import backend.db.base  # noqa: F401 -- registers every model
from backend.core.config import Settings, settings
from backend.db.session import AsyncSessionLocal
from backend.models import audit as audit_actions
from backend.models.audit import AdminAuditLog
from backend.models.interview import InterviewSession
from backend.models.profile import CandidateProfile, Resume
from backend.services import data_deletion
from backend.services.tasks import handlers

PRODUCTION = {
    "ENVIRONMENT": "production",
    "SUPABASE_URL": "https://p.supabase.co",
    "SUPABASE_SECRET_KEY": "k",
    "SUPABASE_JWKS_URL": "https://p.supabase.co/jwks",
    "DATABASE_URL": "postgresql+asyncpg://u:p@h:5432/d",
    "SECRET_KEY": "x" * 40,
    "AGENT_API_SECRET": "s",
    "LIVEKIT_URL": "wss://lk",
    "LIVEKIT_API_KEY": "k",
    "LIVEKIT_API_SECRET": "s",
}


def production(**overrides) -> Settings:
    return Settings(**{**PRODUCTION, **overrides})


# ── CORS is explicit per environment ──────────────────────────────────────

def test_production_refuses_to_boot_with_the_development_origins():
    with pytest.raises(ValueError, match="development origin"):
        production()      # the shipped default is a localhost list


@pytest.mark.parametrize("origins, expected", [
    ('["*"]', "'\\*'"),
    ("[]", "empty"),
    ('["https://hire.example.com", "http://localhost:5174"]', "development origin"),
    ("not json", "not a JSON list"),
])
def test_an_unsafe_cors_configuration_is_named_not_guessed(origins, expected):
    with pytest.raises(ValueError, match=expected):
        production(BACKEND_CORS_ORIGINS=origins)


def test_a_real_origin_list_boots():
    s = production(BACKEND_CORS_ORIGINS='["https://hire.example.com"]')
    assert s.cors_origins == ["https://hire.example.com"]


def test_local_development_keeps_its_localhost_defaults():
    """The check exists to stop a production deployment shipping dev
    origins, not to make development annoying."""
    assert "localhost" in Settings(**{**PRODUCTION, "ENVIRONMENT": "local"}).BACKEND_CORS_ORIGINS


# ── the purge refuses to run ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_purge_refuses_while_the_retention_policy_is_unset(monkeypatch):
    from backend.core.errors import Conflict

    assert settings.DATA_PURGE_ENABLED is False, "the purge must ship disabled"
    async with AsyncSessionLocal() as db:
        with pytest.raises(Conflict) as refused:
            await handlers.purge_expired_data(db, {"dry_run": True})
    assert refused.value.code == "purge_disabled"
    assert "U1" in refused.value.detail or "retention policy" in refused.value.detail


@pytest.mark.asyncio
async def test_enabling_it_without_a_threshold_is_still_refused(monkeypatch):
    from backend.core.errors import ValidationFailed

    monkeypatch.setattr(settings, "DATA_PURGE_ENABLED", True)
    monkeypatch.setattr(settings, "DATA_PURGE_AFTER_DAYS", 0)
    async with AsyncSessionLocal() as db:
        with pytest.raises(ValidationFailed) as refused:
            await handlers.purge_expired_data(db, {})
    assert refused.value.code == "purge_threshold_unset"


# ── what it would do ──────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def old_and_recent_candidates():
    """One candidate whose only interview is ancient, one who interviewed
    long ago *and* last week -- the second must not be in scope."""
    created = []
    async with AsyncSessionLocal() as db:
        for name, ages in (("ancient", [400]), ("returning", [400, 2])):
            profile = CandidateProfile(email=f"{name}-{uuid.uuid4().hex[:8]}@example.dev", full_name=name)
            db.add(profile)
            await db.commit()
            await db.refresh(profile)
            created.append(profile.id)
            db.add(Resume(profile_id=profile.id, original_filename="cv.pdf",
                          storage_path=f"users/{profile.id}/cv.pdf", extraction_status="COMPLETED"))
            for age in ages:
                db.add(InterviewSession(
                    candidate_profile_id=profile.id, role="Backend", level="mid", language="en",
                    status="COMPLETED",
                    completed_at=datetime.now(timezone.utc) - timedelta(days=age),
                    recording_storage_path=f"interviews/{profile.id}/{age}.mp4",
                ))
            await db.commit()
    yield created
    async with AsyncSessionLocal() as db:
        await db.execute(delete(CandidateProfile).where(CandidateProfile.id.in_(created)))
        await db.execute(delete(AdminAuditLog).where(AdminAuditLog.actor_id == "system:purge"))
        await db.commit()


@pytest.mark.asyncio
async def test_a_dry_run_reports_without_deleting(old_and_recent_candidates, monkeypatch):
    monkeypatch.setattr(settings, "DATA_PURGE_ENABLED", True)
    monkeypatch.setattr(settings, "DATA_PURGE_AFTER_DAYS", 365)
    ancient, returning = old_and_recent_candidates

    async with AsyncSessionLocal() as db:
        report = await handlers.purge_expired_data(db, {"dry_run": True})

    assert report["dry_run"] is True and report["candidates"] >= 1
    async with AsyncSessionLocal() as db:
        still_there = (await db.execute(
            select(CandidateProfile.id).where(CandidateProfile.id.in_([ancient, returning]))
        )).all()
    assert len(still_there) == 2, "a dry run deleted something"


@pytest.mark.asyncio
async def test_it_removes_the_expired_candidate_and_leaves_the_returning_one(
    old_and_recent_candidates, monkeypatch
):
    class FakeStorage:
        configured = True

        def __init__(self):
            self.deleted = []

        async def delete(self, key):
            self.deleted.append(key)

    recordings, resumes = FakeStorage(), FakeStorage()
    monkeypatch.setattr(data_deletion, "get_recordings_storage", lambda: recordings)
    monkeypatch.setattr(data_deletion, "get_resumes_storage", lambda: resumes)
    monkeypatch.setattr(settings, "DATA_PURGE_ENABLED", True)
    monkeypatch.setattr(settings, "DATA_PURGE_AFTER_DAYS", 365)
    ancient, returning = old_and_recent_candidates

    async with AsyncSessionLocal() as db:
        await handlers.purge_expired_data(db, {"dry_run": False})

    async with AsyncSessionLocal() as db:
        remaining = {r[0] for r in (await db.execute(
            select(CandidateProfile.id).where(CandidateProfile.id.in_([ancient, returning]))
        )).all()}
    assert ancient not in remaining, "the expired candidate was not purged"
    assert returning in remaining, "a candidate who interviewed recently was purged"
    assert any(str(ancient) in key for key in resumes.deleted), "the CV object survived the purge"


@pytest.mark.asyncio
async def test_the_purge_records_what_it_erased(old_and_recent_candidates, monkeypatch):
    """The record that data was deleted has to outlive the data."""
    class FakeStorage:
        configured = True

        async def delete(self, key):
            return None

    monkeypatch.setattr(data_deletion, "get_recordings_storage", lambda: FakeStorage())
    monkeypatch.setattr(data_deletion, "get_resumes_storage", lambda: FakeStorage())
    monkeypatch.setattr(settings, "DATA_PURGE_ENABLED", True)
    monkeypatch.setattr(settings, "DATA_PURGE_AFTER_DAYS", 365)
    ancient, _ = old_and_recent_candidates

    async with AsyncSessionLocal() as db:
        await handlers.purge_expired_data(db, {"dry_run": False})

    async with AsyncSessionLocal() as db:
        entries = list((await db.execute(
            select(AdminAuditLog).where(AdminAuditLog.target_id == str(ancient))
        )).scalars().all())
    assert len(entries) == 1
    assert entries[0].action == audit_actions.DATA_PURGED
    assert entries[0].actor_id == "system:purge"
    assert entries[0].details["after_days"] == 365
