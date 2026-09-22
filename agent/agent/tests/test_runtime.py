"""H2-D: the worker never strands a session, bounds its calls, and stops when
it no longer owns the session. Fault injection only -- no LiveKit, no
backend."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.interview.models import ActionEnum, InterviewPhase, InterviewRuntimeContext, StructuredAction
from agent.interview.persistence import InterviewPersistence, LeaseState
from agent.runtime.teardown import finalize_session, mark_disconnected_after_failure


class RecordingPersistence(InterviewPersistence):
    def __init__(self, lease_states=None):
        self.calls = []
        self.lease_states = list(lease_states or [])
        self.closed = False

    async def load_session(self, session_id):
        self.calls.append(("load", session_id)); return {"id": session_id}

    async def save_checkpoint(self, context):
        self.calls.append(("checkpoint", context.current_phase.value))

    async def save_completion(self, context):
        self.calls.append(("completion", context.current_phase.value)); return True

    async def save_message(self, session_id, sequence, speaker, text, phase=None, metadata=None):
        self.calls.append(("message", sequence, speaker))

    async def save_event(self, session_id, sequence, event_type, phase=None, metadata=None):
        self.calls.append(("event", sequence, event_type, metadata))

    async def update_status(self, session_id, status, final_result=None):
        self.calls.append(("status", status)); return True

    async def submit_evaluation(self, context):
        self.calls.append(("evaluation",)); return True

    async def renew_lease(self, session_id):
        return self.lease_states.pop(0) if self.lease_states else LeaseState.RENEWED

    async def close(self):
        self.closed = True


def make_context(phase):
    return InterviewRuntimeContext(session_id="s1", candidate_id="c", role="r", confirmed_level="mid",
                                   language="en", current_phase=phase, time_remaining_seconds=600)


# ── teardown ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_failure_after_in_progress_marks_the_session_disconnected_with_checkpoint():
    p = RecordingPersistence()
    ctx = make_context(InterviewPhase.TECHNICAL)
    ctx.event_sequence = 4
    await mark_disconnected_after_failure(p, ctx, "s1")
    assert p.calls[0][:3] == ("event", 5, "SESSION_DISCONNECTED") and p.calls[0][3] == {"reason": "agent_failure"}
    assert ("checkpoint", "TECHNICAL") in p.calls
    assert p.calls[-1] == ("status", "DISCONNECTED")
    assert ctx.event_sequence == 5


@pytest.mark.asyncio
async def test_failure_path_never_raises_even_when_persistence_is_broken():
    p = RecordingPersistence()
    p.save_event = AsyncMock(side_effect=RuntimeError("backend down"))
    p.update_status = AsyncMock(side_effect=RuntimeError("backend down"))
    await mark_disconnected_after_failure(p, make_context(InterviewPhase.WELCOME), "s1")  # no exception


@pytest.mark.asyncio
async def test_finalize_completed_session_persists_completion_and_evaluation():
    p = RecordingPersistence()
    ctx = make_context(InterviewPhase.COMPLETED)
    controller = SimpleNamespace(generate_final_evaluation=AsyncMock())
    outcome = await finalize_session(p, controller, ctx, "s1")
    assert outcome == "completed"
    assert ("completion", "COMPLETED") in p.calls and ("evaluation",) in p.calls
    assert not any(c[0] == "status" and c[1] == "DISCONNECTED" for c in p.calls)


@pytest.mark.asyncio
async def test_finalize_unfinished_session_marks_disconnected():
    p = RecordingPersistence()
    ctx = make_context(InterviewPhase.TECHNICAL)
    controller = SimpleNamespace(generate_final_evaluation=AsyncMock())
    outcome = await finalize_session(p, controller, ctx, "s1")
    assert outcome == "disconnected"
    assert ("status", "DISCONNECTED") in p.calls


# ── entrypoint lifecycle (main._run_session wrapped by entrypoint) ─────────

def _fake_ctx():
    room = MagicMock()
    room.name = "interview-s1"
    ctx = MagicMock()
    ctx.room = room
    ctx.connect = AsyncMock()
    ctx.shutdown = MagicMock()
    ctx.proc = SimpleNamespace(userdata={})
    return ctx


@pytest.mark.asyncio
async def test_entrypoint_marks_disconnected_and_shuts_down_when_the_session_crashes(monkeypatch):
    import agent.main as main
    p = RecordingPersistence()
    ctx = _fake_ctx()
    settings = SimpleNamespace(missing_for_job=lambda: [], GROQ_API_KEY="k", BACKEND_INTERNAL_URL="http://b",
                               AGENT_API_SECRET="s", BACKEND_TIMEOUT_SECONDS=1, BACKEND_RETRY_ATTEMPTS=0,
                               LEASE_RENEWAL_INTERVAL_SECONDS=0.01, LEASE_ERROR_SHUTDOWN_AFTER=3)
    monkeypatch.setattr(main, "_load_env", lambda: None)
    monkeypatch.setattr(main, "reset_settings", lambda: None)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "APIPersistence", lambda **kw: p)

    async def fake_build_context(session_data, persistence, session_id):
        await persistence.update_status(session_id, "IN_PROGRESS")
        return make_context(InterviewPhase.WELCOME), False

    monkeypatch.setattr(main, "build_context", fake_build_context)
    monkeypatch.setattr(main, "build_llm", lambda s: (_ for _ in ()).throw(RuntimeError("LLM init exploded")))

    await main.entrypoint(ctx)

    assert ("status", "IN_PROGRESS") in p.calls
    assert p.calls[-1] == ("status", "DISCONNECTED")          # never left IN_PROGRESS
    assert p.closed
    ctx.shutdown.assert_called_once_with(reason="agent_failure")


@pytest.mark.asyncio
async def test_entrypoint_stops_driving_the_session_when_the_lease_is_lost(monkeypatch):
    import agent.main as main
    p = RecordingPersistence(lease_states=[LeaseState.LOST])
    ctx = _fake_ctx()
    settings = SimpleNamespace(missing_for_job=lambda: [], GROQ_API_KEY="k", BACKEND_INTERNAL_URL="http://b",
                               AGENT_API_SECRET="s", BACKEND_TIMEOUT_SECONDS=1, BACKEND_RETRY_ATTEMPTS=0,
                               LEASE_RENEWAL_INTERVAL_SECONDS=0.01, LEASE_ERROR_SHUTDOWN_AFTER=3)
    monkeypatch.setattr(main, "_load_env", lambda: None)
    monkeypatch.setattr(main, "reset_settings", lambda: None)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "APIPersistence", lambda **kw: p)

    async def fake_build_context(session_data, persistence, session_id):
        await persistence.update_status(session_id, "IN_PROGRESS")
        return make_context(InterviewPhase.WELCOME), False

    adapter = MagicMock()
    adapter.start = AsyncMock()
    adapter.aclose = AsyncMock()
    monkeypatch.setattr(main, "build_context", fake_build_context)
    monkeypatch.setattr(main, "build_llm", lambda s: MagicMock())
    monkeypatch.setattr(main, "InterviewController", lambda llm, persistence, context: MagicMock())
    monkeypatch.setattr(main, "build_stt", lambda lang, s: MagicMock())
    monkeypatch.setattr(main, "build_tts", lambda lang, s: (MagicMock(), None))
    monkeypatch.setattr(main, "vad_for", lambda proc: MagicMock())
    monkeypatch.setattr(main, "VoiceInterviewAdapter", lambda *a, **kw: adapter)

    await asyncio.wait_for(main.entrypoint(ctx), timeout=5)

    statuses = [c for c in p.calls if c[0] == "status"]
    assert statuses == [("status", "IN_PROGRESS")]              # no DISCONNECTED write: the other worker owns it
    adapter.aclose.assert_awaited_once()
    assert p.closed
    ctx.shutdown.assert_called_once_with(reason="lease_lost")


@pytest.mark.asyncio
async def test_entrypoint_normal_completion_finalizes_and_shuts_down(monkeypatch):
    import agent.main as main
    p = RecordingPersistence()
    ctx = _fake_ctx()
    handlers = {}
    ctx.room.on = lambda name, fn=None: handlers.__setitem__(name, fn) if fn else (lambda f: handlers.__setitem__(name, f))
    settings = SimpleNamespace(missing_for_job=lambda: [], GROQ_API_KEY="k", BACKEND_INTERNAL_URL="http://b",
                               AGENT_API_SECRET="s", BACKEND_TIMEOUT_SECONDS=1, BACKEND_RETRY_ATTEMPTS=0,
                               LEASE_RENEWAL_INTERVAL_SECONDS=10, LEASE_ERROR_SHUTDOWN_AFTER=3)
    monkeypatch.setattr(main, "_load_env", lambda: None)
    monkeypatch.setattr(main, "reset_settings", lambda: None)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "APIPersistence", lambda **kw: p)
    context = make_context(InterviewPhase.COMPLETED)

    async def fake_build_context(session_data, persistence, session_id):
        await persistence.update_status(session_id, "IN_PROGRESS")
        return context, False

    adapter = MagicMock()
    adapter.start = AsyncMock()
    adapter.aclose = AsyncMock()
    controller = MagicMock()
    controller.generate_final_evaluation = AsyncMock()
    monkeypatch.setattr(main, "build_context", fake_build_context)
    monkeypatch.setattr(main, "build_llm", lambda s: MagicMock())
    monkeypatch.setattr(main, "InterviewController", lambda llm, persistence, context: controller)
    monkeypatch.setattr(main, "build_stt", lambda lang, s: MagicMock())
    monkeypatch.setattr(main, "build_tts", lambda lang, s: (MagicMock(), None))
    monkeypatch.setattr(main, "vad_for", lambda proc: MagicMock())
    monkeypatch.setattr(main, "VoiceInterviewAdapter", lambda *a, **kw: adapter)

    task = asyncio.create_task(main.entrypoint(ctx))
    for _ in range(50):
        await asyncio.sleep(0.01)
        if "disconnected" in handlers:
            break
    handlers["disconnected"]()                                    # the room ends
    await asyncio.wait_for(task, timeout=5)

    assert ("completion", "COMPLETED") in p.calls and ("evaluation",) in p.calls
    ctx.shutdown.assert_called_once_with(reason="completed")
