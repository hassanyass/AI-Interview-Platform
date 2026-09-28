# Runbook — follow one interview through the logs

Goal: given a session id, reconstruct what happened across the frontend
call, the backend and the agent worker.

## Inputs

- `session_id` — from the admin dashboard, the candidate's URL
  (`/interviews/<id>`), or the `request_id` a user pasted from an error
  screen (`ApiError.requestId`; the id is also in the response header).

## Backend side

```bash
docker compose logs --no-log-prefix backend | grep '"session_id": "<session_id>"' > sess-backend.jsonl
```

Every line under `/api/v1/interviews/*` and `/api/v1/internal/interviews/*`
for that session is there, in order, regardless of which handler emitted it.
Useful fields: `request_id`, `logger`, `message`, `level`.

- `request_id` values shaped `<session_id>.<agent_id>.<n>` came from the
  agent; `n` counts its calls (`1` = the first `load`). A gap in `n` means
  the agent made a call that never reached the backend (network) — check the
  agent side for the same `n`.
- Other `request_id`s (UUIDs) are browser calls.

## Agent side

```bash
docker compose logs --no-log-prefix agent | grep '"session_id": "<session_id>"' > sess-agent.jsonl
```

Lines are stamped from `bind_session` onward (right after the room is
joined). Lines before that carry only `job_id` (the LiveKit job) — find it
from the first stamped line and grep for `"job_id": "<job_id>"` to get the
dispatch/connect lines too.

Markers worth searching for, in order of a normal interview:

| marker | meaning |
|---|---|
| `registered worker` (no session) | worker is up |
| `[LLM-METRICS]` lines with `event: llm_call` | each LLM turn — `duration_ms`, tokens |
| `[STT-METRICS]` / `[TTS-METRICS]` | per-utterance STT/TTS latencies |
| `SESSION_STARTED`, checkpoint saves | persistence calls (`request_id` matches the backend line) |
| `renew-lease` | every `LEASE_RENEWAL_INTERVAL_SECONDS` |
| `shutdown` reason `completed` / `agent_failure` / `lease_lost` / `session_not_loaded` | how the worker left |

## Join the two

Both files are JSON lines with `ts` in UTC; merge and sort:

```bash
cat sess-backend.jsonl sess-agent.jsonl | python -c "import sys,json; rows=[json.loads(l) for l in sys.stdin if l.startswith('{')]; [print(r['ts'], r['service'], r.get('request_id') or '-', r['message']) for r in sorted(rows, key=lambda r: r['ts'])]"
```

A backend `4xx`/`5xx` and the agent line that triggered it share the same
`request_id`, so the pair reads as one event.

## Text mode (local dev)

Without JSON the same ids are appended to each line:
`… request_id=<id> session_id=<id>` (backend), `… session_id=<id> agent_id=<id>`
(agent). `grep session_id=<id>` works the same way.

## Database view

```sql
select status, active_agent_id, agent_lease_expires_at, disconnected_at, completed_at
  from interview_sessions where id = '<session_id>';
select sequence_number, event_type, phase, created_at from interview_events
  where session_id = '<session_id>' order by sequence_number;
```

(the events table is the durable timeline the agent writes; the logs are
the how and why around it).
