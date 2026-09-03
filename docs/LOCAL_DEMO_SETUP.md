# Local Demo Setup — Exact Current Commands

Written for a clean VS Code terminal (PowerShell). Every command below matches what this project's own files/scripts actually contain as of 2026-09-02 — not remembered/assumed defaults. Start the three layers **in this order** (backend → agent → frontend) in **three separate terminal tabs**, since all three need to keep running simultaneously.

## Before you start anything

**⚠️ DB credential check, specific to right now**: the Supabase database password was mid-rotation as of this writing. Before running the backend or agent, confirm with whoever is doing the rotation that it's finished, and that `.env` (repo root) and `agent\.env`'s `DATABASE_URL` both already reflect the **new** password. Starting the backend against a stale password will fail immediately and loudly (a Postgres auth error on startup) — better to confirm first than debug it live.

**Env files this project actually reads** (confirmed from `backend/backend/core/config.py` and `agent/agent/main.py` directly):
- Backend loads `../.env` (repo root) then `backend/.env` if present — today only the root `.env` exists.
- Agent loads its own `agent/.env` (mirrors most of the root file).
- Frontend reads `frontend/.env` (Vite env vars, `VITE_*` only).

**Minimum required variables, confirmed by reading the actual code that checks for them (not just what's listed in `.env.example`):**
| Layer | Hard-required (the process errors/refuses without these) | Where enforced |
|---|---|---|
| Backend | `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`, `SUPABASE_JWKS_URL`, `DATABASE_URL` | `backend/backend/core/config.py` — Pydantic settings with no default, will raise on import if missing |
| Agent | `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `GROQ_API_KEY`, `AGENT_API_SECRET`, `BACKEND_INTERNAL_URL` | `agent/agent/main.py:161-168` — checked, but only **inside `entrypoint()`**, i.e. only when a real interview room is actually dispatched to the worker. **The worker will start and successfully register with LiveKit Cloud even if these are missing or wrong** — a clean "registered worker" log line does NOT by itself prove these are correct. The real proof only comes from a real test interview actually starting a session without an immediate silent failure. |
| Frontend | `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`, `VITE_API_BASE_URL` | `frontend/src/lib/supabase.ts`, `frontend/src/lib/api.ts` — no hard runtime check, but blank/wrong values cause every Supabase/API call to fail |

Open `.env`, `agent\.env`, and `frontend\.env` now and confirm none of these are placeholder text (e.g. `<your-api-key>`) before continuing.

---

## 1. Backend (FastAPI) — start first

```powershell
cd C:\Users\hassa\Documents\AI-Interview-Platform\backend
..\.venv\Scripts\uvicorn.exe backend.main:app --reload --port 8000
```

This is the real module path (`backend.main:app`, i.e. `backend/backend/main.py` — this project has a nested `backend/backend/` package layout, not a top-level `app/`). Do not use `uvicorn app.main:app` — that module does not exist in this repo (a real, previously-shipped bug in `backend/Dockerfile` made exactly this mistake, fixed 2026-09-02).

**What a healthy startup looks like:**
```
INFO:     Will watch for changes in these directories: ['C:\\Users\\hassa\\Documents\\AI-Interview-Platform\\backend']
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [xxxxx] using WatchFiles
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```
**A known, harmless line you may also see** — `Failed to initialize Supabase client: Invalid...` from `resume_service.py`. This is a documented, non-blocking startup warning (`docs/PROJECT_STATUS.md`'s "Known non-blocking debt") — it does **not** affect admin/RBAC endpoints. Don't mistake it for a real failure, but also don't ignore *other* errors around it.

**Real failure signs, not to ignore:** any `pydantic.ValidationError` mentioning a missing field (means one of the hard-required vars above is actually missing/empty), or a Postgres/`asyncpg` connection error (check `DATABASE_URL` — especially relevant right now given the in-progress password rotation above).

**Quick verify it's actually serving:** open `http://127.0.0.1:8000/docs` in a browser — a real FastAPI Swagger UI should load.

---

## 2. Agent worker (LiveKit) — start second

```powershell
cd C:\Users\hassa\Documents\AI-Interview-Platform\agent
C:\Users\hassa\AppData\Local\Programs\Python\Python313\python.exe -m agent.main dev
```

**Use `dev`, not `start`, for local demo work.** `start` is the production subcommand (used in `agent/start.sh` for a deployed container); `dev` is the local-development mode with readable console log formatting — both were directly confirmed this session by reading the installed `livekit-agents` CLI source (`start`/`dev`/`console`/`download-files` are the real, distinct subcommands; running with no subcommand at all just prints help and exits without starting anything — a real bug that existed in `agent/start.sh` until it was fixed 2026-09-02).

**A local quirk worth knowing, not a bug**: this repo has two separate Python installs with `livekit-agents` present — the project's own `.venv`, and the system-wide `Python313` install shown above. Both currently report the same version (`1.7.1`), and the system install is the one that has actually been used and proven working, repeatedly, this whole project. If you'd rather use the repo's own `.venv` instead (`..\.venv\Scripts\python.exe -m agent.main dev`), it should work identically today — just be aware these are two independent installs that could silently drift apart later if only one is ever updated.

**What a healthy startup looks like** (real log lines, seen live and repeatedly this session):
```
WARNING [livekit.agents] dev mode is deprecated and will be removed in a future release; use `lk agent dev` instead
WARNING [livekit.agents] in-process auto-reload has been removed from the Python CLI; use `lk agent dev` for hot-reload
INFO [livekit.agents] starting worker                 {"version": "1.7.1", "rtc-version": "1.1.15"}
INFO [livekit.agents] plugin registered                {"plugin": "livekit.plugins.openai", ...}
INFO [livekit.agents] plugin registered                {"plugin": "livekit.plugins.groq", ...}
INFO [livekit.agents] plugin registered                {"plugin": "livekit.plugins.silero", ...}
INFO [livekit.agents] plugin registered                {"plugin": "livekit.plugins.azure", ...}
INFO [livekit.agents] HTTP server listening on :XXXXX
INFO [livekit.agents] registered worker                {"agent_name": "", ..., "id": "AW_xxxxxxxx", "url": "wss://ai-interview-v1-hriz644s.livekit.cloud", "region": "UAE", ...}
```
The two `WARNING` lines are expected noise from `dev` mode itself — not errors, ignore them. **The line that actually proves it worked is `registered worker`**, with a real `id` and your real LiveKit Cloud URL. If that line never appears, or the process exits right after the plugin-registered lines, something in the required-vars list above is wrong.

**Important limitation of this check, stated plainly (see the table above)**: `registered worker` proves the connection to LiveKit Cloud succeeded. It does **not** prove `BACKEND_INTERNAL_URL`/`AGENT_API_SECRET` are correct, or that the backend is even reachable — that only gets exercised once a real interview session actually starts (step below). If a candidate connects and the agent never joins the room or the interview silently never progresses, check this process's console for an error at that moment, not just its startup log.

---

## 3. Frontend (Vite/React) — start last

```powershell
cd C:\Users\hassa\Documents\AI-Interview-Platform\frontend
npm run dev
```

(This runs `vite`, per `frontend/package.json`'s own `"dev"` script — nothing more elaborate.)

**What a healthy startup looks like:**
```
  VITE v_._._  ready in ___ ms

  ➜  Local:   http://127.0.0.1:5173/
  ➜  Network: use --host to expose
```
Note it's `127.0.0.1`, not `localhost` — `frontend/vite.config.ts` explicitly sets `server: { host: '127.0.0.1' }`. Open that exact URL.

**Quick verify it's actually the current code, not a stale cached build**: open the browser console (F12) — there should be no red errors on initial load, and the page should show the real Himma/e& login screen, not a blank page or a raw error boundary. If you get a blank white page, check this terminal for a Vite/esbuild compile error before assuming it's a backend problem.

---

## Full startup order, summarized

1. Backend (`uvicorn`) — wait for `Application startup complete.`
2. Agent (`python -m agent.main dev`) — wait for `registered worker`
3. Frontend (`npm run dev`) — wait for the `Local: http://127.0.0.1:5173/` line, then open it

**End-to-end proof all three are actually wired together correctly** (not just "each one's log looked fine individually"): open the frontend, log in as admin, open a published job's public link or send yourself an invite, and actually start one interview session through to the agent greeting you out loud. That's the only check that exercises all three processes talking to each other for real — matching this project's own established standard of "a live browser + live agent-worker run," not just clean-looking logs in isolation.

## Stopping everything cleanly

Each of the three commands above runs in the foreground of its own terminal tab — `Ctrl+C` in each tab stops that layer. If a terminal was closed without stopping its process first (this project has a documented history of exactly this leaving stale processes running unnoticed), check for leftovers before starting fresh:
```powershell
Get-CimInstance Win32_Process | Where-Object {
  $_.CommandLine -match 'uvicorn' -or $_.CommandLine -match 'agent\.main' -or $_.CommandLine -match 'vite'
} | Select-Object ProcessId, CommandLine
```
Anything listed here that you don't recognize as a terminal you meant to leave open should be stopped (`Stop-Process -Id <id> -Force`) before starting a fresh copy — a stale duplicate silently serving old code has caused real, confusing bugs in this project before.
