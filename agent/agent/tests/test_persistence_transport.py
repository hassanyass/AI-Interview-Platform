"""H2-D: APIPersistence retries transport errors and 5xx (never 4xx), parks
failed writes in an outbox and replays them in order, and reports lease
state as a tri-state. Uses a fake aiohttp session; no network."""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

from agent.interview.models import InterviewPhase, InterviewRuntimeContext
from agent.interview.persistence import APIPersistence, LeaseState


class FakeResponse:
    def __init__(self, status, body=None):
        self.status = status
        self._body = body if body is not None else {}
        self.headers = {"Content-Type": "application/json"}

    async def json(self):
        return self._body

    async def text(self):
        return str(self._body)


class FakeSession:
    """Scripted responses per (method, path-suffix); an entry may be an
    exception instance (raised) or a FakeResponse."""

    def __init__(self, script):
        self.script = script          # list of FakeResponse | Exception, consumed in order
        self.requests = []
        self.closed = False

    def request(self, method, url, **kwargs):
        self.requests.append((method, url.rsplit("/", 1)[-1], kwargs))
        item = self.script.pop(0)

        @asynccontextmanager
        async def _cm():
            if isinstance(item, BaseException):
                raise item
            yield item

        return _cm()

    async def close(self):
        self.closed = True


def make(script, attempts=2):
    p = APIPersistence("http://b", "secret", "agent-1", timeout_seconds=1, retry_attempts=attempts)
    fake = FakeSession(script)
    p._session = fake
    return p, fake


@pytest.fixture(autouse=True)
def _no_sleep():
    with patch("asyncio.sleep", new=AsyncMock()):
        yield


@pytest.mark.asyncio
async def test_retries_transport_errors_and_5xx_then_succeeds():
    p, fake = make([aiohttp.ClientConnectionError("reset"), FakeResponse(503), FakeResponse(201)])
    await p.save_message("s1", 1, "candidate", "hi")
    assert [r[0] for r in fake.requests] == ["POST", "POST", "POST"]
    assert p.outbox_size == 0


@pytest.mark.asyncio
async def test_4xx_is_not_retried():
    p, fake = make([FakeResponse(409, {"detail": "dup"})])
    ok = await p.update_status("s1", "COMPLETED")
    assert ok is False and len(fake.requests) == 1


@pytest.mark.asyncio
async def test_failed_write_is_parked_and_replayed_in_order_before_the_next_write():
    # message 1 fails every attempt -> parked; message 2 arrives: outbox is
    # flushed first (delivers 1), then 2 is sent.
    p, fake = make([FakeResponse(503), FakeResponse(503), FakeResponse(503),   # msg1: 3 attempts, parked
                    FakeResponse(201),                                          # flush: msg1 delivered
                    FakeResponse(201)])                                         # msg2
    await p.save_message("s1", 1, "candidate", "one")
    assert p.outbox_size == 1
    await p.save_message("s1", 2, "agent", "two")
    assert p.outbox_size == 0
    sent = [r[2]["data"] for r in fake.requests if r[0] == "POST"]
    assert '"sequence_number": 1' in sent[-2] and '"sequence_number": 2' in sent[-1]


@pytest.mark.asyncio
async def test_outbox_keeps_order_when_the_replay_still_fails():
    p, fake = make([FakeResponse(503), FakeResponse(503), FakeResponse(503),   # msg1 parked
                    FakeResponse(503), FakeResponse(503), FakeResponse(503),   # flush attempt for msg1 fails
                    FakeResponse(503), FakeResponse(503), FakeResponse(503)])  # msg2 itself fails -> parked behind msg1
    await p.save_message("s1", 1, "candidate", "one")
    await p.save_message("s1", 2, "agent", "two")
    assert p.outbox_size == 2
    assert '"sequence_number": 1' in p._outbox[0][2]["data"]


@pytest.mark.asyncio
async def test_evaluation_is_not_parked_and_status_returns_bool():
    p, fake = make([FakeResponse(503), FakeResponse(503), FakeResponse(503)])
    ctx = InterviewRuntimeContext(session_id="s1", candidate_id="c", role="r", confirmed_level="mid",
                                  language="en", current_phase=InterviewPhase.COMPLETED, time_remaining_seconds=0)
    ctx.final_evaluation = None
    assert await p.submit_evaluation(ctx) is True          # nothing to submit
    ok = await p.update_status("s1", "DISCONNECTED")
    assert ok is False and p.outbox_size == 0


@pytest.mark.asyncio
async def test_renew_lease_tristate_and_flushes_outbox_first():
    p, fake = make([FakeResponse(200, {"status": "renewed"}), FakeResponse(409, {"detail": "not yours"}),
                    aiohttp.ClientConnectionError("x"), aiohttp.ClientConnectionError("x"), aiohttp.ClientConnectionError("x")])
    assert await p.renew_lease("s1") == LeaseState.RENEWED
    assert await p.renew_lease("s1") == LeaseState.LOST
    assert await p.renew_lease("s1") == LeaseState.ERROR
    p._outbox.append(("POST", "http://b/api/v1/internal/interviews/s1/messages", {"data": "{}", "headers": {}}))
    fake.script.extend([FakeResponse(201), FakeResponse(200)])
    assert await p.renew_lease("s1") == LeaseState.RENEWED
    assert p.outbox_size == 0 and fake.requests[-2][1] == "messages"


@pytest.mark.asyncio
async def test_close_tries_to_flush_then_closes_the_session():
    p, fake = make([FakeResponse(201)])
    p._outbox.append(("POST", "http://b/api/v1/internal/interviews/s1/events", {"data": "{}", "headers": {}}))
    await p.close()
    assert p.outbox_size == 0 and fake.closed


@pytest.mark.asyncio
async def test_load_session_maps_statuses():
    p, _ = make([FakeResponse(200, {"id": "s1"}), FakeResponse(409, {"detail": "leased"}), FakeResponse(404), FakeResponse(500), FakeResponse(500), FakeResponse(500)])
    assert (await p.load_session("s1")) == {"id": "s1"}
    assert (await p.load_session("s1")) is None
    assert (await p.load_session("s1")) is None
    assert (await p.load_session("s1")) is None
