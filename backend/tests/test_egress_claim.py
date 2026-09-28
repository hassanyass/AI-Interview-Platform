"""H5-B: a session can only ever start one recording.

`POST /livekit/token` schedules `start_recording_egress`, and a candidate
legitimately asks for a token more than once -- a reconnect, a resume, a
double-click on Start. The old guard read `recording_egress_id` and then
acted on what it read, so two of those in flight together could each see
NULL and each start an egress: two recordings billed, and only one id
stored, leaving the other running until LiveKit's own timeout because
finalization only knows about the one it can see.
"""
import asyncio
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

import backend.db.base  # noqa: F401 -- registers every model before the mapper configures
from backend.db.session import AsyncSessionLocal
from backend.models.interview import InterviewSession
from backend.models.profile import CandidateProfile
from backend.services.sessions import room_token as room_token_module


class FakeRealtime:
    """Counts starts and takes long enough to overlap its callers."""

    def __init__(self, delay=0.05, fail=False):
        self.started = []
        self._delay = delay
        self._fail = fail

    async def start_room_recording(self, *, room, output_path, destination):
        self.started.append(room)
        await asyncio.sleep(self._delay)
        if self._fail:
            raise RuntimeError("livekit said no")
        return type("Started", (), {
            "failed": False, "status": "EGRESS_STARTING",
            "error": None, "egress_id": f"EG_{len(self.started)}",
        })()


class FakeStorage:
    configured = True

    def egress_destination(self):
        return {"bucket": "test"}


@pytest_asyncio.fixture
async def session_id():
    async with AsyncSessionLocal() as db:
        profile = CandidateProfile(email=f"egress-{uuid.uuid4().hex[:8]}@example.dev", full_name="Egress Check")
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
        profile_id = profile.id
        session = InterviewSession(
            candidate_profile_id=profile_id, role="Backend Engineer", level="mid",
            language="en", status="IN_PROGRESS",
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        sid = session.id
    yield str(sid)
    async with AsyncSessionLocal() as db:
        await db.execute(delete(InterviewSession).where(InterviewSession.id == sid))
        await db.execute(delete(CandidateProfile).where(CandidateProfile.id == profile_id))
        await db.commit()


async def row(session_id):
    async with AsyncSessionLocal() as db:
        return (await db.execute(
            select(InterviewSession.recording_egress_id, InterviewSession.recording_egress_started_at)
            .where(InterviewSession.id == uuid.UUID(session_id))
        )).first()


@pytest.fixture
def realtime(monkeypatch):
    fake = FakeRealtime()
    monkeypatch.setattr(room_token_module, "get_realtime", lambda: fake)
    monkeypatch.setattr(room_token_module, "get_recordings_storage", lambda: FakeStorage())
    return fake


@pytest.mark.asyncio
async def test_a_single_start_records_the_egress_and_the_claim(session_id, realtime):
    await room_token_module.start_recording_egress(session_id, f"interview-{session_id}")

    egress_id, started_at = await row(session_id)
    assert realtime.started == [f"interview-{session_id}"]
    assert egress_id == "EG_1"
    assert started_at is not None


@pytest.mark.asyncio
async def test_five_concurrent_starts_produce_exactly_one_recording(session_id, realtime):
    """The race this phase exists to close. The fake's delay guarantees the
    calls overlap, which is what a double-clicked Start button does."""
    room = f"interview-{session_id}"
    await asyncio.gather(*[room_token_module.start_recording_egress(session_id, room) for _ in range(5)])

    assert len(realtime.started) == 1, f"started {len(realtime.started)} recordings"
    egress_id, started_at = await row(session_id)
    assert egress_id == "EG_1" and started_at is not None


@pytest.mark.asyncio
async def test_a_later_reconnect_does_not_start_a_second_recording(session_id, realtime):
    room = f"interview-{session_id}"
    await room_token_module.start_recording_egress(session_id, room)
    await room_token_module.start_recording_egress(session_id, room)
    assert len(realtime.started) == 1


@pytest.mark.asyncio
async def test_a_failed_start_hands_the_claim_back_so_a_retry_is_possible(session_id, monkeypatch):
    """A provider failure must not leave the session permanently unable to
    record -- the candidate may reconnect a minute later and succeed."""
    failing = FakeRealtime(fail=True)
    monkeypatch.setattr(room_token_module, "get_realtime", lambda: failing)
    monkeypatch.setattr(room_token_module, "get_recordings_storage", lambda: FakeStorage())

    await room_token_module.start_recording_egress(session_id, f"interview-{session_id}")

    egress_id, started_at = await row(session_id)
    assert egress_id is None
    assert started_at is None, "the claim must be released when nothing was started"

    working = FakeRealtime()
    monkeypatch.setattr(room_token_module, "get_realtime", lambda: working)
    await room_token_module.start_recording_egress(session_id, f"interview-{session_id}")
    assert len(working.started) == 1
    assert (await row(session_id))[0] == "EG_1"


@pytest.mark.asyncio
async def test_an_immediate_provider_rejection_also_releases_the_claim(session_id, monkeypatch):
    class RejectingRealtime(FakeRealtime):
        async def start_room_recording(self, *, room, output_path, destination):
            self.started.append(room)
            return type("Started", (), {
                "failed": True, "status": "EGRESS_FAILED", "error": "bad request", "egress_id": None,
            })()

    monkeypatch.setattr(room_token_module, "get_realtime", lambda: RejectingRealtime())
    monkeypatch.setattr(room_token_module, "get_recordings_storage", lambda: FakeStorage())

    await room_token_module.start_recording_egress(session_id, f"interview-{session_id}")
    assert await row(session_id) == (None, None)


@pytest.mark.asyncio
async def test_unconfigured_storage_skips_without_claiming(session_id, monkeypatch):
    class NoStorage:
        configured = False

    monkeypatch.setattr(room_token_module, "get_recordings_storage", lambda: NoStorage())
    await room_token_module.start_recording_egress(session_id, f"interview-{session_id}")
    assert await row(session_id) == (None, None)
