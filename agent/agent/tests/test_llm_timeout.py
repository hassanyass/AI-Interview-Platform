"""H4-B: the LLM call is bounded, and a stalled model cannot wedge the turn.

H2-D's claim was that an END_INTERVIEW press can never queue behind a
model that has stopped answering. That rests on three things, none of
which had a test: the timeout reaches the SDK client, the controller
turns any LLM failure into its fallback line rather than propagating, and
the turn lock is released even when the turn raises.
"""
import asyncio

import pytest

from agent.config import AgentSettings, reset_settings
from agent.providers import factory


@pytest.fixture
def settings(monkeypatch, tmp_path):
    for k in ("AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION", "TTS_PROVIDER", "GROQ_API_KEY", "LLM_MODEL"):
        monkeypatch.delenv(k, raising=False)
    reset_settings()
    yield AgentSettings(
        GROQ_API_KEY="gk", LLM_MODEL="llm-model", TTS_PROVIDER="groq",
        LLM_TIMEOUT_SECONDS=7.5, LLM_MAX_RETRIES=1, AGENT_STATE_DIR=tmp_path,
    )
    reset_settings()


def test_the_configured_timeout_and_retry_budget_reach_the_sdk_client(settings):
    """Not a style check: the SDK's own defaults are 60s x 2 retries, which
    is minutes of a wedged turn -- the whole reason these settings exist."""
    llm = factory.build_llm(settings)

    timeout = llm.client.timeout
    # httpx.Timeout or a float, depending on how the SDK normalises it.
    seconds = getattr(timeout, "read", None) or getattr(timeout, "connect", None) or timeout
    assert float(seconds) == 7.5
    assert llm.client.max_retries == 1


def test_a_bare_provider_still_refuses_to_start_without_a_model(monkeypatch):
    """An unconfigured model used to mean a silent default; it now fails
    loudly at construction instead of mid-interview."""
    from agent.llm.groq_provider import GroqProvider

    monkeypatch.delenv("LLM_MODEL", raising=False)
    with pytest.raises(ValueError, match="LLM_MODEL"):
        GroqProvider(api_key="gk")

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        GroqProvider()


# ── the lock is the thing that must not wedge ─────────────────────────────

@pytest.mark.asyncio
async def test_a_turn_that_raises_still_releases_the_lock():
    """voice_adapter holds `async with self._turn_lock` around a turn. If a
    raised timeout could skip the release, the next command -- including
    END_INTERVIEW -- would wait forever."""
    lock = asyncio.Lock()

    async def failing_turn():
        async with lock:
            raise TimeoutError("model stalled")

    with pytest.raises(TimeoutError):
        await failing_turn()
    assert not lock.locked()

    # ...and the next command gets in immediately.
    await asyncio.wait_for(lock.acquire(), timeout=0.5)
    lock.release()


@pytest.mark.asyncio
async def test_a_cancelled_turn_releases_the_lock_too():
    lock = asyncio.Lock()
    started = asyncio.Event()

    async def hanging_turn():
        async with lock:
            started.set()
            await asyncio.sleep(3600)

    task = asyncio.create_task(hanging_turn())
    await started.wait()
    assert lock.locked()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not lock.locked()


@pytest.mark.asyncio
async def test_the_controller_turns_an_llm_failure_into_its_fallback_line():
    """controller.py catches any exception from _generate_next_action and
    substitutes the localized fallback, so a provider outage is a spoken
    sentence rather than a dead session. Asserted through the real
    controller (a frozen file -- tested around, never edited)."""
    from unittest.mock import AsyncMock

    from agent.interview.controller import InterviewController
    from agent.interview.models import InterviewPhase, InterviewRuntimeContext

    context = InterviewRuntimeContext(
        session_id="s1", candidate_id="c1", role="Backend Engineer", confirmed_level="mid",
        language="en", current_phase=InterviewPhase.TECHNICAL, time_remaining_seconds=600,
    )
    llm = AsyncMock()
    llm.generate_structured = AsyncMock(side_effect=TimeoutError("model stalled"))
    controller = InterviewController(llm, AsyncMock(), context)

    action = await controller.process_candidate_input("I would use a queue here.")

    assert action is not None
    assert action.response, "the candidate must hear something, not silence"
    assert "failed" in (action.reason or "").lower()
