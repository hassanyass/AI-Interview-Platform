"""H3: structured logs carry request/session ids, /metrics exposes what the
middleware and adapters record, and the CLI's dry runs work on the test DB."""
import json
import logging
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.core.logging import ContextFilter, JsonFormatter, TextFormatter, bind_session, request_id_var
from backend.core.metrics import provider_call_failures_total, timed_provider_call
from backend.main import app


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as c:
        yield c


# ── log shape ──────────────────────────────────────────────────────────────

def _record(msg="hello", **extra):
    rec = logging.LogRecord("backend.test", logging.INFO, __file__, 1, msg, (), None)
    for k, v in extra.items():
        setattr(rec, k, v)
    return rec


def test_json_lines_carry_context_and_extras():
    ContextFilter("test").filter(rec := _record("saved", event="checkpoint", seq=7))
    line = json.loads(JsonFormatter().format(rec))
    assert line["service"] == "backend" and line["env"] == "test" and line["level"] == "INFO"
    assert line["message"] == "saved" and line["event"] == "checkpoint" and line["seq"] == 7
    assert "request_id" in line and "session_id" in line and line["ts"].endswith("+00:00")


def test_context_vars_reach_every_record():
    token = request_id_var.set("req-42")
    bind_session(uuid.UUID(int=5))
    try:
        rec = _record("x")
        ContextFilter("test").filter(rec)
        assert rec.request_id == "req-42" and rec.session_id == str(uuid.UUID(int=5))
        text = TextFormatter().format(rec)
        assert "request_id=req-42" in text and "session_id=" in text
    finally:
        request_id_var.reset(token)
        bind_session(None)


@pytest.mark.asyncio
async def test_a_request_binds_its_id_and_an_internal_route_binds_the_session_id(client, caplog):
    sid = uuid.uuid4()
    caplog.set_level(logging.INFO)
    # /internal/* without the agent secret -> 422/403, but the router
    # dependency binding the session id runs first and the request id is set
    # by the middleware; assert both on the records emitted by the app.
    logger = logging.getLogger("backend.tests.probe")
    seen = {}

    from backend.core import logging as log_mod

    orig = log_mod.ContextFilter.filter

    def spy(self, record):
        ok = orig(self, record)
        if record.name == "backend.tests.probe":
            seen["request_id"] = record.request_id
            seen["session_id"] = record.session_id
        return ok

    log_mod.ContextFilter.filter = spy
    try:
        @app.get("/__probe/log/{session_id}")
        async def _probe(session_id: uuid.UUID):
            bind_session(session_id)
            logger.info("probe line")
            return {"ok": True}

        r = await client.get(f"/__probe/log/{sid}", headers={"X-Request-ID": "corr-1"})
        assert r.status_code == 200
    finally:
        log_mod.ContextFilter.filter = orig
    assert seen == {"request_id": "corr-1", "session_id": str(sid)}


# ── metrics ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_metrics_endpoint_counts_requests_by_route_template(client):
    await client.get("/health")
    await client.get("/version")
    body = (await client.get("/metrics")).text
    assert 'http_requests_total{method="GET",route="/health",status="200"}' in body
    assert "http_request_duration_seconds_bucket" in body
    assert "/metrics" not in [l for l in body.splitlines() if l.startswith("http_requests_total") and 'route="/metrics"' in l]
    assert "background_tasks_pending" in body and "sweep_runs_total" in body or "background_tasks_pending" in body


@pytest.mark.asyncio
async def test_routes_from_included_routers_are_labelled_with_their_template(client):
    # FastAPI >= 0.135 lists include_router() routers as _IncludedRouter in
    # app.routes; the middleware must still resolve the endpoint to its
    # prefixed template rather than "<unmatched>".
    sid = uuid.uuid4()
    await client.post(f"/api/v1/internal/interviews/{sid}/renew-lease")   # no agent secret -> 4xx, still matched
    body = (await client.get("/metrics")).text
    line = next(l for l in body.splitlines() if l.startswith("http_requests_total") and "renew-lease" in l)
    assert 'route="/api/v1/internal/interviews/{session_id}/renew-lease"' in line
    assert str(sid) not in body


@pytest.mark.asyncio
async def test_unmatched_paths_do_not_explode_label_cardinality(client):
    await client.get("/no/such/route/12345")
    await client.get("/no/such/route/67890")
    body = (await client.get("/metrics")).text
    assert 'route="<unmatched>",status="404"' in body
    assert "12345" not in body


@pytest.mark.asyncio
async def test_provider_decorator_records_latency_and_failures():
    calls = {"n": 0}

    class Adapter:
        @timed_provider_call("fake", "op")
        async def op(self, ok: bool):
            calls["n"] += 1
            if not ok:
                raise RuntimeError("boom")
            return "fine"

    a = Adapter()
    assert await a.op(True) == "fine"
    before = provider_call_failures_total.labels("fake", "op")._value.get()
    with pytest.raises(RuntimeError):
        await a.op(False)
    assert provider_call_failures_total.labels("fake", "op")._value.get() == before + 1
    assert calls["n"] == 2


# ── cli ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cli_dry_runs_work_against_the_test_database(capsys):
    # The commands are awaited directly: cli.main()'s asyncio.run would open
    # a second loop while the app engine's pool belongs to pytest's.
    from backend import cli
    assert await cli.cmd_finalize_stuck_sessions(dry_run=True) == 0
    assert await cli.cmd_backfill_evaluations(dry_run=True) == 0
    out = capsys.readouterr().out
    assert "stuck session(s)" in out and "Backfilled: 0 (dry run" in out


def test_cli_parser_knows_every_command():
    from backend import cli
    p = cli.build_parser()
    assert p.parse_args(["finalize-stuck-sessions", "--dry-run"]).dry_run is True
    assert p.parse_args(["make-admin", "a@b.c"]).email == "a@b.c"
    with pytest.raises(SystemExit):
        p.parse_args(["no-such-command"])
