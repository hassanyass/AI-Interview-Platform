# Runbook — a stuck interview session

## Symptoms

- A candidate reports "the interviewer stopped responding" or the
  admin dashboard shows a session `IN_PROGRESS` long after the interview
  should have ended.
- `InterviewSession.status` is `IN_PROGRESS` or `DISCONNECTED` and
  `agent_lease_expires_at` is in the past (or `NULL`).

## What normally happens

- The agent renews its lease every `LEASE_RENEWAL_INTERVAL_SECONDS`
  (`POST …/internal/interviews/{id}/renew-lease`). If it crashes it writes
  `DISCONNECTED` on the way out (H2-D teardown).
- The **idle-disconnect sweep** (every `DISCONNECT_SWEEP_INTERVAL_SECONDS`,
  advisory-locked so only one backend replica runs it) finalizes sessions
  that stayed `DISCONNECTED` for `DISCONNECT_AUTO_FINALIZE_MINUTES`:
  sets `TERMINATED`, writes an evaluation placeholder (no LLM run — the
  evaluation is the agent's job at interview end) and stops the egress.
- The sweep never touches `IN_PROGRESS`. A session that stays
  `IN_PROGRESS` with a dead lease means the agent died without reaching
  its teardown (OOM kill, host lost) — that is the case for this runbook.

## Diagnose

1. Find the session id (admin UI, or the candidate's link).
2. Backend logs for it:

```bash
docker compose logs backend | grep '"session_id": "<id>"' | tail -50
```

   Last `renew-lease` line = when the agent was last alive.
3. Agent logs: `docker compose logs agent | grep '"session_id": "<id>"' | tail -50`
   — look for a traceback or a `shutdown` reason (`agent_failure`,
   `lease_lost`, `completed`).
4. Metrics: `curl -s localhost:8001/metrics | grep sweep_` — is the sweep
   running (`sweep_runs_total{outcome="ran"}` increasing)? `failed` rising
   means the sweep itself errors: read its log line (`logger` =
   `backend.services.sessions.finalization`).

## Fix

Preview, then finalize every stuck session (no live lease):

```bash
make cli ARGS="finalize-stuck-sessions --dry-run"
make cli ARGS="finalize-stuck-sessions"
```

(Windows: `scripts/dev.ps1 cli -CliArgs "finalize-stuck-sessions --dry-run"`.
Inside the container: `docker compose exec backend python -m backend.cli finalize-stuck-sessions --dry-run`.)

This uses the same `finalize_live_session` as the sweep: `TERMINATED`,
evaluation placeholder, egress stopped. It only selects sessions whose
lease is `NULL` or expired — never finalize one that is genuinely live.

If the session is `DISCONNECTED` and younger than
`DISCONNECT_AUTO_FINALIZE_MINUTES`, do nothing: the candidate can still
reconnect and the agent resumes from its checkpoint.

## Afterwards

- The candidate sees the result page for a `TERMINATED` session; there is
  no scored evaluation (placeholder only). Whether they may retake is undecided
  (`CURRENT_DECISIONS.md`) — it is an admin decision today (new invitation).
- If the agent died from an exception, the traceback is in its log under
  the session id; open an issue with the `request_id` of the last backend call.
