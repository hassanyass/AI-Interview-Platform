"""H3: one root handler (no doubled lines), session context on every record,
and every backend call carries a correlating X-Request-ID."""
import json
import logging
from unittest.mock import AsyncMock

import pytest

from agent.interview.persistence import APIPersistence
from agent.logging_setup import ContextFilter, JsonFormatter, bind_session, configure_worker_logging, session_id_var


@pytest.fixture
def clean_root():
    root = logging.getLogger()
    saved = list(root.handlers), root.level
    for h in list(root.handlers):
        root.removeHandler(h)
    yield root
    for h in list(root.handlers):
        root.removeHandler(h)
    for h in saved[0]:
        root.addHandler(h)
    root.setLevel(saved[1])


def test_configure_keeps_exactly_one_stream_handler_even_after_the_sdk_added_one(clean_root):
    # simulate the SDK's handler plus the old basicConfig one
    clean_root.addHandler(logging.StreamHandler())
    clean_root.addHandler(logging.StreamHandler())
    configure_worker_logging(log_format="json", level="INFO", environment="test")
    configure_worker_logging(log_format="json", level="INFO", environment="test")   # idempotent
    handlers = [h for h in clean_root.handlers if type(h) is logging.StreamHandler]   # pytest's capture handlers are subclasses and must be left alone
    assert len(handlers) == 1
    assert isinstance(handlers[0].formatter, JsonFormatter)
    assert any(isinstance(f, ContextFilter) for f in handlers[0].filters)


def test_text_mode_wraps_the_existing_formatter_and_appends_context(clean_root):
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    clean_root.addHandler(h)
    configure_worker_logging(log_format="text", level="INFO", environment="test")
    bind_session("sess-1", agent_id="agent-abc")
    rec = logging.LogRecord("agent", logging.INFO, __file__, 1, "hello", (), None)
    for f in h.filters:
        f.filter(rec)
    assert h.format(rec) == "INFO hello  session_id=sess-1 agent_id=agent-abc"
    bind_session(None)


def test_json_lines_carry_session_context_and_unpack_sdk_extras():
    bind_session("sess-9", agent_id="agent-x", job_id="AJ_1")
    rec = logging.LogRecord("agent", logging.INFO, __file__, 1, "llm done", (), None)
    rec.extra = {"duration_ms": 12.5}     # the SDK's JsonFormatter packs extras like this
    rec.event = "llm_call"
    ContextFilter("production").filter(rec)
    line = json.loads(JsonFormatter().format(rec))
    assert line["service"] == "agent" and line["env"] == "production"
    assert line["session_id"] == "sess-9" and line["agent_id"] == "agent-x" and line["job_id"] == "AJ_1"
    assert line["event"] == "llm_call" and line["duration_ms"] == 12.5
    bind_session(None)
    assert session_id_var.get() is None


@pytest.mark.asyncio
async def test_every_backend_call_carries_a_correlating_request_id():
    p = APIPersistence("http://b", "secret", "agent-7", timeout_seconds=1, retry_attempts=0)
    seen = []

    class FakeResp:
        status = 200
        headers = {"Content-Type": "application/json"}
        async def json(self): return {}
        async def text(self): return ""

    class FakeSession:
        closed = False
        def request(self, method, url, **kwargs):
            seen.append((url, kwargs["headers"].get("X-Request-ID")))
            class CM:
                async def __aenter__(self_inner): return FakeResp()
                async def __aexit__(self_inner, *a): return False
            return CM()
        async def close(self): ...

    p._session = FakeSession()
    await p.save_event("11111111-2222-3333-4444-555555555555", 1, "SESSION_STARTED")
    await p.renew_lease("11111111-2222-3333-4444-555555555555")
    ids = [rid for _, rid in seen]
    assert ids == ["11111111-2222-3333-4444-555555555555.agent-7.1", "11111111-2222-3333-4444-555555555555.agent-7.2"]
    import re
    assert all(re.match(r"^[A-Za-z0-9._:-]{1,128}$", i) for i in ids)   # what the backend accepts
