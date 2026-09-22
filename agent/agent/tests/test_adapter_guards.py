"""H2-D: the voice adapter transcribes only the candidate, survives an STT
crash, validates ui_command packets, tracks its tasks and can be closed."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.interview.voice_adapter import VoiceInterviewAdapter
from livekit import rtc


def bare_adapter(restart_max=2, max_bytes=16384):
    a = object.__new__(VoiceInterviewAdapter)
    a._stt_tasks = []
    a._command_tasks = set()
    a._stt_track = None
    a._stt_restarts = 0
    a._closed = False
    a._stt_stream = None
    a._stt_restart_max = restart_max
    a._ui_command_max_bytes = max_bytes
    a.stt_plugin = MagicMock()
    a.vad_plugin = MagicMock()
    a._playback_task = None
    a._candidate_endpoint_task = None
    a._waiting_room_timeout_task = None
    a._current_synthesis_task = None
    return a


def audio_track():
    t = MagicMock()
    t.kind = rtc.TrackKind.KIND_AUDIO
    return t


# ── STT ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_only_candidate_audio_is_transcribed():
    a = bare_adapter()
    with patch.object(a, "_start_stt_pipeline") as start:
        a._on_track_subscribed(audio_track(), MagicMock(), SimpleNamespace(identity="observer-hr"))
        start.assert_not_called()
        a._on_track_subscribed(audio_track(), MagicMock(), SimpleNamespace(identity="candidate-abc"))
        start.assert_called_once()


@pytest.mark.asyncio
async def test_stt_crash_restarts_the_pipeline_then_gives_up():
    a = bare_adapter(restart_max=1)
    a._stt_track = audio_track()
    starts = []
    a._start_stt_pipeline = lambda track: starts.append(track)

    async def boom():
        raise RuntimeError("stt exploded")

    await a._guarded_stt_loop(boom(), "read")          # 1st crash -> restart
    assert len(starts) == 1 and a._stt_restarts == 1
    await a._guarded_stt_loop(boom(), "read")          # 2nd crash -> over the limit, no restart
    assert len(starts) == 1


@pytest.mark.asyncio
async def test_cancelled_loops_are_not_treated_as_crashes():
    a = bare_adapter()
    starts = []
    a._start_stt_pipeline = lambda track: starts.append(track)

    async def cancelled():
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await a._guarded_stt_loop(cancelled(), "push")
    assert starts == []


@pytest.mark.asyncio
async def test_aclose_cancels_tracked_tasks_and_closes_the_stream():
    a = bare_adapter()
    stream = MagicMock()
    stream.aclose = AsyncMock()
    a._stt_stream = stream

    async def forever():
        await asyncio.sleep(3600)

    t1, t2 = asyncio.create_task(forever()), asyncio.create_task(forever())
    a._stt_tasks = [t1, t2]
    cmd = asyncio.create_task(forever())
    a._command_tasks.add(cmd)
    await a.aclose()
    await asyncio.sleep(0)
    assert t1.cancelled() and t2.cancelled() and cmd.cancelled()
    stream.aclose.assert_awaited_once()
    assert a._closed and a._stt_stream is None


# ── ui_command ─────────────────────────────────────────────────────────────

def packet(data: bytes, identity="candidate-abc", topic="ui_command"):
    return SimpleNamespace(data=data, topic=topic, participant=SimpleNamespace(identity=identity))


@pytest.mark.asyncio
async def test_ui_command_from_non_candidate_is_dropped():
    a = bare_adapter()
    a._handle_ui_command = AsyncMock()
    a._on_data_received(packet(json.dumps({"command": "END_INTERVIEW"}).encode(), identity="observer-1"))
    await asyncio.sleep(0)
    a._handle_ui_command.assert_not_called()


@pytest.mark.asyncio
async def test_ui_command_shape_and_size_are_enforced():
    a = bare_adapter(max_bytes=64)
    a._handle_ui_command = AsyncMock()
    a._on_data_received(packet(b"not json"))
    a._on_data_received(packet(json.dumps({"command": 42}).encode()))
    a._on_data_received(packet(json.dumps({"command": "drop table"}).encode()))
    a._on_data_received(packet(json.dumps(["END_INTERVIEW"]).encode()))
    a._on_data_received(packet(json.dumps({"command": "END_INTERVIEW", "pad": "x" * 200}).encode()))
    await asyncio.sleep(0)
    a._handle_ui_command.assert_not_called()


@pytest.mark.asyncio
async def test_valid_ui_command_is_dispatched_and_tracked():
    a = bare_adapter()
    started = asyncio.Event()

    async def handler(command, payload):
        started.set()
        await asyncio.sleep(0.01)

    a._handle_ui_command = handler
    a._on_data_received(packet(json.dumps({"command": "REQUEST_HINT", "x": 1}).encode()))
    await started.wait()
    assert len(a._command_tasks) == 1
    await asyncio.sleep(0.05)
    assert len(a._command_tasks) == 0          # discarded when done
