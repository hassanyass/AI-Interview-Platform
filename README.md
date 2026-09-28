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

## Status and plans
- `docs/PROJECT_STATUS.md` — what is done and verified
- `docs/production-hardening-plan.md` — production-readiness track (H0–H6)
- `docs/responsive-design-plan.md` — responsive/RTL track (R0–R7)
- `docs/path2hire-transition-plan.md` — the original B2C→B2B phase plan
