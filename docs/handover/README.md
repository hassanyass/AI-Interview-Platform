# Handover — operating Path2Hire

Start here if you are taking over the running system rather than developing
it. Written during the production-hardening initiative
(`docs/production-hardening-plan.md`, H3) and kept current with it.

## What runs

| Service | Image / command | Port | Health |
|---|---|---|---|
| `postgres` | `postgres:15`, volume `postgres_data` | 5432 | `pg_isready` |
| `migrate` | `backend/` image, `alembic upgrade head`, exits | — | exit code 0 |
| `backend` | `backend/` image, `uvicorn backend.main:app` | 8001 | `GET /health` (liveness), `GET /ready` (readiness, checks the DB) |
| `agent` | `agent/` image, `python -m agent.main dev` (LiveKit worker) | — | worker registers with LiveKit; logs `registered worker` |
| `frontend` | `node:22-alpine`, Vite dev server (dev only) | 5174 | page loads |

Everything reads the root `.env` (see `backend/.env.example`,
`agent/.env.example`, `frontend/.env.example`). Boot fails closed: a
missing or placeholder secret outside `ENVIRONMENT=local|test` stops the
process with the offending setting named (H1-A).

## Where to look

- **Logs**: JSON lines to stdout in containers (`LOG_FORMAT=json`); every
  line carries `request_id` and `session_id` → `observability.md`.
- **Metrics**: `GET /metrics` on the backend (Prometheus text) → `observability.md`.
- **Background work**: the four admin AI actions run in the backend's task
  worker (`tasks` table). `GET /admin/tasks/{id}` is the poll;
  `task_queue_*` are the metrics → `runbooks/stuck-task.md`.
- **Operational commands**: `python -m backend.cli …` (from the repo root
  with `PYTHONPATH=backend`; `make cli ARGS="…"` / `scripts/dev.ps1 cli`).
  `make-admin`, `finalize-stuck-sessions [--dry-run]`,
  `backfill-evaluations [--dry-run]`, `create-demo-admin`, `seed-demo-data`.
- **Runbooks** (each executed once against the compose stack when written):

| Situation | Runbook |
|---|---|
| Start, stop or upgrade the stack | `runbooks/start-stop-upgrade.md` |
| Apply a database migration | `runbooks/apply-migration.md` |
| Rotate a secret or API key | `runbooks/rotate-secret.md` |
| An interview is stuck (`IN_PROGRESS` / `DISCONNECTED` with no agent) | `runbooks/stuck-session.md` |
| An AI generation (questions, invitation draft, evaluation) is stuck or failed | `runbooks/stuck-task.md` |
| Groq / LiveKit / storage is down or slow | `runbooks/provider-outage.md` |
| Restore the database from a backup | `runbooks/restore-from-backup.md` |
| Trace what happened in one interview | `runbooks/follow-one-interview.md` |
| Add or swap a provider (LLM, storage, email, …) | `runbooks/add-provider-adapter.md` |

## Frozen contracts

Do not change without an approved sub-phase plan (`CLAUDE.md` §2):
`agent/agent/interview/controller.py`, every `/api/v1/internal/*` route,
`frontend/src/…/InterviewerCharacter.tsx`.

## Open items an operator should know

- Retention of recordings/transcripts is undecided (U1) — nothing is deleted automatically.
- Concurrency limit per worker is undecided (U4) — one LiveKit worker process handles the jobs LiveKit dispatches to it.
- Email is the `null` provider; invitations are logged to the console, not sent (P1 in `CURRENT_DECISIONS.md`).
