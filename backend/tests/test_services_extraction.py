"""H2-A2: the helpers moved out of the routers behave as before, and the
router coupling they replaced is gone."""
import ast
import pathlib
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from backend.core.errors import Conflict
from backend.db.session import AsyncSessionLocal
from backend.models.interview import Evaluation, InterviewSession, Job
from backend.models.profile import CandidateProfile
from backend.services.publish_rules import assert_sections_publishable
from backend.services.sessions.finalization import ensure_evaluation_placeholder, finalize_live_session
from backend.services.sessions.room_token import issue_candidate_room_token

ENDPOINTS = pathlib.Path(__file__).resolve().parents[1] / "backend" / "api" / "endpoints"


# ── publish rules ──────────────────────────────────────────────────────────

def _section(section_type, questions, budget):
    return SimpleNamespace(section_type=section_type, questions=questions, config={"time_budget_minutes": budget} if budget else {})


def test_publish_rules_messages_are_unchanged():
    with pytest.raises(Conflict) as exc:
        assert_sections_publishable([_section("VERBAL", [], 10), _section("MCQ", ["q"], 5)])
    assert str(exc.value) == "Cannot publish: section(s) with no questions: VERBAL"
    with pytest.raises(Conflict) as exc:
        assert_sections_publishable([_section("VERBAL", ["q"], None)])
    assert str(exc.value) == "Cannot publish: section(s) with no time budget set: VERBAL"
    assert_sections_publishable([])                         # no sections at all is allowed
    assert_sections_publishable([_section("VERBAL", ["q"], 10)])


# ── router coupling ────────────────────────────────────────────────────────

def test_no_router_imports_another_router_or_uses_in_function_service_imports():
    for path in ENDPOINTS.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("backend.api.endpoints"):
                raise AssertionError(f"{path.name} imports {node.module}")
        # in-function imports of backend.services / backend.api are the cycle workaround this phase removed
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)]:
            for node in ast.walk(fn):
                if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(("backend.services", "backend.api")):
                    raise AssertionError(f"{path.name}:{node.lineno} in-function import of {node.module}")


# ── finalization (real test DB) ────────────────────────────────────────────

@pytest_asyncio.fixture
async def session_row():
    async with AsyncSessionLocal() as db:
        profile = CandidateProfile(full_name="Finalize Test", email=f"fin-{uuid.uuid4().hex[:8]}@path2hire.test")
        db.add(profile)
        await db.flush()
        session = InterviewSession(candidate_profile_id=profile.id, role="r", level="mid", language="en",
                                   status="IN_PROGRESS", recording_egress_id="EG_test")
        db.add(session)
        await db.flush()
        sid = session.id          # before commit() expires the instance
        await db.commit()
    yield sid
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Evaluation).where(Evaluation.session_id == sid))
        await db.execute(delete(InterviewSession).where(InterviewSession.id == sid))
        await db.execute(delete(CandidateProfile).where(CandidateProfile.full_name == "Finalize Test"))
        await db.commit()


@pytest.mark.asyncio
async def test_finalize_live_session_is_idempotent_and_stops_recording_once(session_row):
    with patch("backend.services.sessions.finalization.get_realtime") as rt:
        rt.return_value.stop_recording = AsyncMock()
        rt.return_value.delete_room = AsyncMock()
        async with AsyncSessionLocal() as db:
            session = (await db.execute(select(InterviewSession).where(InterviewSession.id == session_row))).scalar_one()
            assert await finalize_live_session(db, session, target_status="TERMINATED") is True
            await db.refresh(session)   # finalize commits, which expires the instance
            assert session.status == "TERMINATED" and session.completed_at is not None
            # second call: already terminal -> no-op, no second side effects
            assert await finalize_live_session(db, session, target_status="TERMINATED") is False
        rt.return_value.stop_recording.assert_awaited_once_with("EG_test")
        rt.return_value.delete_room.assert_awaited_once_with(f"interview-{session_row}")

    async with AsyncSessionLocal() as db:
        ev = (await db.execute(select(Evaluation).where(Evaluation.session_id == session_row))).scalar_one()
        assert ev.is_placeholder is True
        # the placeholder never overwrites a real evaluation
        ev.is_placeholder = False
        ev.summary = "real"
        await db.commit()
        await ensure_evaluation_placeholder(db, session_row)
        await db.commit()
        ev = (await db.execute(select(Evaluation).where(Evaluation.session_id == session_row))).scalar_one()
        assert ev.summary == "real" and ev.is_placeholder is False


# ── room token service ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_issue_candidate_room_token_mints_and_schedules_recording_once(monkeypatch):
    from backend.core.config import settings
    monkeypatch.setattr(settings, "LIVEKIT_URL", "wss://lk.test")
    monkeypatch.setattr(settings, "LIVEKIT_API_KEY", "k")
    monkeypatch.setattr(settings, "LIVEKIT_API_SECRET", "s")
    started = []

    async def fake_start(session_id, room):
        started.append((session_id, room))

    with patch("backend.services.sessions.room_token.start_recording_egress", new=fake_start), \
         patch("backend.services.sessions.room_token.get_realtime") as rt:
        rt.return_value.mint_participant_token.return_value = "jwt-1"
        sid = uuid.uuid4()
        issued = await issue_candidate_room_token(SimpleNamespace(id=sid, recording_egress_id=None), "cand-1")
        import asyncio
        await asyncio.sleep(0)  # let the scheduled task run
        assert issued.token == "jwt-1" and issued.url == "wss://lk.test" and issued.room_name == f"interview-{sid}"
        assert started == [(str(sid), f"interview-{sid}")]
        rt.return_value.mint_participant_token.assert_called_once()
        # an already-recording session gets a token but no second egress
        await issue_candidate_room_token(SimpleNamespace(id=sid, recording_egress_id="EG_1"), "cand-1")
        await asyncio.sleep(0)
        assert len(started) == 1


@pytest.mark.asyncio
async def test_issue_candidate_room_token_refuses_when_livekit_is_unconfigured(monkeypatch):
    from backend.core.config import settings
    from backend.core.errors import AppError
    monkeypatch.setattr(settings, "LIVEKIT_API_SECRET", "")
    with pytest.raises(AppError) as exc:
        await issue_candidate_room_token(SimpleNamespace(id=uuid.uuid4(), recording_egress_id=None), "c")
    assert exc.value.status == 500 and exc.value.code == "livekit_unconfigured"
