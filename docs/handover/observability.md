# Observability (H3)

## Logs

Both services write one line per record to stdout. Format is chosen by
`LOG_FORMAT`:

| value | backend | agent |
|---|---|---|
| `json` | `core/logging.py::JsonFormatter` | `logging_setup.py::JsonFormatter` |
| `text` | human line + ` request_id=… session_id=…` suffix | the SDK's coloured dev formatter + ` session_id=… agent_id=…` suffix |
| `auto` (default) | `text` when `ENVIRONMENT` is `local`/`test`, else `json` | `text` under `python -m agent.main dev` or `ENVIRONMENT` local/test, else `json` |

`docker-compose.yml` sets `LOG_FORMAT=json` for both. `LOG_LEVEL` (default
`INFO`) applies to the root logger.

### JSON shape

```json
{"ts":"2026-09-22T10:15:02.113+00:00","level":"INFO","logger":"backend.api.endpoints.internal",
 "message":"lease renewed","service":"backend","env":"production",
 "request_id":"5d0c…-agent-demo.17","session_id":"11111111-2222-3333-4444-555555555555", "...extras": "…"}
```

Agent lines have `service: "agent"` and `session_id`, `agent_id`, `job_id`
(the LiveKit job id). Anything passed as `extra=` to a logging call is
merged at the top level — e.g. the agent's `[LLM-METRICS]` line carries
`event`, `llm_model`, `duration_ms`, `prompt_tokens`, `completion_tokens`.

### Correlation

- The backend's `RequestIdMiddleware` accepts an incoming `X-Request-ID`
  (`^[A-Za-z0-9._:-]{1,128}$`) or generates a UUID, echoes it on the
  response and binds it to a contextvar for the request's lifetime.
- Every route under `/api/v1/interviews/*` and `/api/v1/internal/interviews/*`
  binds `session_id` from the path (router dependency
  `deps.bind_session_id_from_path`) before the handler runs, so even a 403
  from a bad agent secret is attributed to the session.
- The agent stamps every backend call with
  `X-Request-ID: <session_id>.<agent_id>.<n>` (`APIPersistence.request_id_for`),
  `n` increasing per call. Grep the agent log for the same value to line up
  the two sides. Recipe: `runbooks/follow-one-interview.md`.
- Frontend `ApiError.requestId` shows the id for a failed browser call
  (from the JSON body or the response header).

## Metrics

`GET /metrics` on the backend (Prometheus text exposition, via
`prometheus_client`). Enabled by `METRICS_ENABLED=true` (default).

| metric | labels | source |
|---|---|---|
| `http_requests_total` | `method`, `route`, `status` | `MetricsMiddleware` — `route` is the path **template** (`/api/v1/admin/jobs/{job_id}`), `<unmatched>` for 404s; `/metrics` itself is excluded |
| `http_request_duration_seconds` (histogram) | `method`, `route` | same |
| `provider_call_duration_seconds` (histogram) | `provider`, `op` | `@timed_provider_call` on the adapters: `groq.complete_json`, `s3.put/delete`, `supabase.put/delete`, `livekit.start_room_recording/stop_recording/delete_room` |
| `provider_call_failures_total` | `provider`, `op` | same, incremented when the adapter raises |
| `sweep_runs_total` | `outcome` = `ran` / `skipped_locked` / `failed` | idle-disconnect sweep (`services/sessions/finalization.py`) |
| `sweep_finalized_total` | — | sessions the sweep finalized |
| `ready_check_failures_total` | `check` (`database`) | `/ready` |
| `background_tasks_pending` (gauge) | — | tracked fire-and-forget tasks (`core/background.py`), sampled on scrape |

Plus the default Python process/GC collectors.

**Exposure**: `/metrics` is unauthenticated by design (Prometheus scrapes
it). Keep it off the public ingress — allow it only from the scrape
network, or set `METRICS_ENABLED=false` on internet-facing replicas and
scrape a dedicated one.

The agent has no HTTP endpoint; its STT/TTS/LLM latencies are the
`[STT-METRICS]`, `[TTS-METRICS]`, `[LLM-METRICS]` log lines (the LiveKit
SDK's `metrics_collected` events, re-attached after a TTS rebuild).

## Health

- `GET /health` — liveness; never touches the DB. Use it for restart decisions.
- `GET /ready` — readiness; `200` when `SELECT 1` succeeds, `503` with
  `{"checks": {"database": "error"}}` otherwise. The compose healthcheck and
  any load balancer should probe this one.
- `GET /version` — the running backend version.

## Local dev

`LOG_FORMAT=auto` gives readable text in a terminal. To see the JSON shape
locally: `LOG_FORMAT=json uvicorn backend.main:app …`. Tests assert on the
formatters directly (`backend/tests/test_observability.py`,
`agent/agent/tests/test_observability.py`).
