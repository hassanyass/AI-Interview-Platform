# Himma / Path2Hire — AI Interview Platform

A voice-AI interview platform for e&: HR authors a Job with an ordered
interview definition (verbal, coding, MCQ sections), candidates join via
invitation or public link, and a LiveKit agent runs the live interview and
produces an evaluation.

## Architecture
- **Frontend** — React 19 + TypeScript + Vite (`frontend/`, dev port **5174**)
- **Backend** — Python 3.13 + FastAPI + SQLAlchemy (async) + Alembic (`backend/`, dev port **8001**)
- **Agent worker** — Python 3.13 + `livekit-agents` (`agent/`)
- **Database / Auth / Storage** — PostgreSQL (Supabase in the hosted setup), Supabase Auth, Supabase Storage (CVs), Cloudflare R2 (recordings)
- **Realtime** — LiveKit Cloud
- **LLM / STT / TTS** — Groq (Azure TTS optional)

## Repository layout
| Path | What |
|---|---|
| `frontend/` | SPA: admin panel (HR) + candidate entry + live interview workspace |
| `backend/backend/` | FastAPI app (`backend.main:app`), models, Alembic migrations in `backend/alembic/` |
| `backend/tests/` | Backend test suite (runs against the disposable test DB) |
| `agent/agent/` | LiveKit worker (`python -m agent.main`), interview controller, voice adapter |
| `tests/legacy/` | Phase-by-phase regression scripts (`test_phase*.py`), same test DB |
| `scripts/` | Operational scripts (`create_demo_admin.py`, `seed_demo_data.py`, …) and `dev.ps1` |
| `docs/` | Plans, decisions (`CURRENT_DECISIONS.md`), architecture, status (`PROJECT_STATUS.md`) |

## Prerequisites
- Python **3.13** (`.python-version`), Node **22** (`frontend/.nvmrc`), Docker Desktop
- A Supabase project, a LiveKit Cloud project, Groq API key(s)

## Setup
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt -r agent/requirements.txt -r requirements-dev.txt
cd frontend && npm ci && cd ..
```
Copy `.env.example` → `.env` and `frontend/.env.example` → `frontend/.env`, then fill in
the credentials. `backend/.env.example` and `agent/.env.example` document exactly which
variables each service reads.

## Run (local, three terminals)
See [docs/LOCAL_DEMO_SETUP.md](docs/LOCAL_DEMO_SETUP.md) for the full walkthrough. In short:

```bash
# 1 backend
cd backend && ../.venv/Scripts/uvicorn.exe backend.main:app --reload --port 8001
# 2 agent
cd agent && ../.venv/Scripts/python.exe -m agent.main dev
# 3 frontend  → http://127.0.0.1:5174
cd frontend && npm run dev
```

Or the whole stack in Docker (reads the root `.env`):
```bash
docker compose --profile app up --build
```

## Test
```bash
docker compose up -d postgres-test     # disposable Postgres on 5433
python -m pytest                       # backend/tests + agent + tests/legacy
cd frontend && npm run typecheck && npx oxlint src && npm test
```
The suites never touch `DATABASE_URL`: `conftest.py` substitutes `TEST_DATABASE_URL`
(default = the `postgres-test` service), rebuilds the schema from the Alembic chain,
and refuses to run against a Supabase host.

`make <target>` (Linux/macOS) and `.\scripts\dev.ps1 <target>` (Windows) wrap all of
the above: `install`, `lock`, `up`, `down`, `test`, `lint`, `typecheck`, `migrate`.

## Dependencies
`backend/requirements.in` and `agent/requirements.in` hold the top-level dependencies;
the pinned `requirements.txt` files are compiled from them (`make lock`). Edit the `.in`,
never the lockfile.

## Deploying and operating it

**`docs/handover/` is the entry point for anyone running this rather than
developing it** — start at [docs/handover/README.md](docs/handover/README.md).

| If you want to | Read |
|---|---|
| Stand the stack up somewhere new | [handover/deploy.md](docs/handover/deploy.md) — a portable container stack; anything that runs Docker will run it |
| Put it on Kubernetes | [handover/kubernetes.md](docs/handover/kubernetes.md) |
| Look up a setting: what it does, whether it is required | [handover/env-matrix.md](docs/handover/env-matrix.md) — **generated from the code**, and a test fails if it drifts |
| Size a deployment | [handover/capacity.md](docs/handover/capacity.md) |
| Find logs, metrics, request ids | [handover/observability.md](docs/handover/observability.md) |
| Threat model, personal data, erasure | [handover/security.md](docs/handover/security.md) |
| Fix something at 2am | [handover/runbooks/](docs/handover/runbooks/) — nine runbooks, each executed once against the stack when written |
| Swap a provider (LLM, storage, email, …) | [handover/runbooks/add-provider-adapter.md](docs/handover/runbooks/add-provider-adapter.md) |

### How portable is it, really

**Cloud-portable: yes.** `compose.prod.yaml` plus three Dockerfiles, no
hosting-provider specifics, TLS deliberately left to a proxy you put in
front. It runs on any Docker host or Kubernetes cluster.

**Vendor-portable: partly.** Six concerns sit behind provider ports with a
written swap procedure — `llm`, `storage`, `realtime`, `email`,
`notifications`, `queue`. **Authentication does not.** Supabase Auth is
wired through `backend/backend/core/security.py`, `core/config.py`,
`api/deps.py`, the `supabase_user_id` column on the candidate profile, and
the frontend's `lib/supabase.ts`. Moving to another identity provider is a
project, not a configuration change. This is a deliberate position, not an
oversight — see `docs/handover/deploy.md` § "What is and is not swappable".

Note also that each port currently has exactly one real adapter (`groq`,
`livekit`, `s3`, `postgres`). The seams are exercised by tests against
fakes, not yet by a second real implementation.

## Status and plans
- `docs/PROJECT_STATUS.md` — what is done and verified
- `docs/production-hardening-plan.md` — production-readiness track (H0–H6)
- `docs/responsive-design-plan.md` — responsive/RTL track (R0–R7)
- `docs/path2hire-transition-plan.md` — the original B2C→B2B phase plan
