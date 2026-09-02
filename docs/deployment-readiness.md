# Deployment Readiness Report

This report evaluates the current state of the Path2Hire platform for deployment across three layers (Frontend, Backend, Agent Worker). It focuses on free-tier viability, environment configuration, and codebase readiness based on a full repository audit.

## 1. Agent Layer (Highest Risk)
**Goal:** Run the LiveKit agent worker as a continuous, long-running process for free.

**Findings (Render Free Tier):**
- Render's **Free Tier** is strictly limited to "Web Services" (which sleep after 15 minutes of inactivity) and small PostgreSQL/Redis instances.
- Render's **Background Worker** service type—the correct category for this process—**is not available on the free tier**. It requires a paid instance (starting at $7/month).
- Attempting to hack the free "Web Service" tier by binding a dummy HTTP port and pinging it is actively discouraged by Render and will result in the instance being spun down regardless. More importantly, when it sleeps or restarts, any active LiveKit WebSocket connections will drop, abruptly killing live candidate interviews.

**Alternatives for Free Long-Running Workers:**
True "always-on" free PaaS options for background workers essentially no longer exist in the modern cloud landscape.
- **Railway**: No longer offers a renewing free tier; they provide a $5 one-time trial credit. Once exhausted, the service pauses.
- **Fly.io**: Once the go-to for free Docker containers, they now require a credit card and bill for overages. It is no longer a strictly "free" tier.
- **Koyeb / Zeabur**: Free tiers exist for Docker containers, but like Render, they aggressively sleep instances that don't receive HTTP traffic.
- **Cloud VPS (GCP e2-micro / Oracle Cloud Always Free)**: The only true "always free" options are raw VMs. GCP offers an `e2-micro` instance, and Oracle offers ARM VMs for free. However, these are bare-metal Linux servers requiring manual setup (installing Docker, configuring systemd, etc.) rather than a simple PaaS deployment.

**Conclusion for Agent:** A reliable, free PaaS for the agent is not feasible. The most straightforward path is either upgrading Render to a $7/mo background worker or manually deploying to a free GCP/Oracle VPS.

## 2. Backend Layer (FastAPI)
**Goal:** Deploy as a free web service on Render.

**Findings:**
- Render's free web service tier **will spin down after 15 minutes of inactivity**.
- **Cold-Start UX Impact:** When a candidate clicks an invitation link or attempts to register after the app has been idle, the initial API request (e.g., `GET /api/v1/apply/...`) will trigger Render to spin the instance back up.
- A Python FastAPI + SQLAlchemy container typically takes **30 to 60 seconds** to boot. During this time, the candidate's browser will hang. This is a severe UX problem that may lead candidates to assume the platform is broken and abandon the interview.

**Conclusion for Backend:** Render's free tier works mechanically but provides an unacceptable UX for candidates due to the ~45s cold start.

## 3. Frontend Layer (Vite/React)
**Goal:** Deploy as a free SPA on Vercel.

**Findings:**
- **Vercel Free Tier:** Perfectly sufficient and well-suited for this SPA.
- **Build Config:** `package.json` specifies `build: tsc -b && vite build`. Vercel automatically detects Vite and will use this build command.
- **Output Directory:** Uses the standard `dist` folder, which Vercel defaults to.
- **Routing:** A `vercel.json` file is already present with the correct rewrite rule (`/(.*)` -> `/index.html`) to support client-side routing.

**Conclusion for Frontend:** Ready as-is.

## 4. Full Environment Variable Inventory
Based on an audit of `.env`, `.env.example`, and `render.yaml`, the following variables are required across the stack.

### Frontend (Vercel)
Must be prefixed with `VITE_` and set in Vercel project settings:
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_PUBLISHABLE_KEY`
- `VITE_API_BASE_URL` (Must point to the deployed Render backend URL)

### Backend (Render Web Service)
- `ENVIRONMENT` (e.g., `staging` or `production`)
- `SUPABASE_URL`
- `SUPABASE_SECRET_KEY`
- `SUPABASE_JWKS_URL`
- `DATABASE_URL` (Must use the Supavisor connection pooler string)
- `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`
- `BACKEND_CORS_ORIGINS` (Must include the deployed Vercel frontend URL, e.g., `["https://your-frontend.vercel.app"]`)
- `AGENT_API_SECRET` (Shared secret with the agent worker)

### Agent Worker (Render Background Worker / VPS)
- `ENVIRONMENT`
- `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`, `SUPABASE_JWKS_URL`
- `DATABASE_URL`
- `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`
- `GROQ_API_KEY`, `GROQ_MODEL`
- *(Optional)* `GROQ_API_KEY_1` through `GROQ_API_KEY_7` (For TTS quota rotation)
- `STT_PROVIDER`, `STT_MODEL`, `STT_LANGUAGE`
- `LLM_PROVIDER`, `LLM_MODEL`
- *(Optional)* `OPENAI_API_KEY` (If `LLM_PROVIDER=openai`)
- `TTS_PROVIDER`, `TTS_MODEL`, `TTS_LANGUAGE`, `TTS_429_COOLDOWN_SECONDS`, `TTS_MAX_RETRIES`, `TTS_429_RETRY_DELAY_SECONDS`
- *(Optional)* `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION`, `AZURE_TTS_ENGLISH_VOICE`, `AZURE_TTS_ARABIC_VOICE` (If using Azure)
- `GROQ_STT_MODEL`, `GROQ_TTS_ENGLISH_MODEL`, `GROQ_TTS_ARABIC_MODEL`
- `DEFAULT_MAX_DURATION_MINUTES`, `DEFAULT_LANGUAGE`
- `AGENT_API_SECRET` (Shared secret with backend)
- `BACKEND_INTERNAL_URL` (Must point to the deployed Render backend URL)

## 5. Hardcoded Localhost & CORS Audit
A repository-wide grep for `localhost` and `127.0.0.1` revealed the following required configuration changes for deployment:

1. **Frontend API URL:** `frontend/.env` hardcodes `VITE_API_BASE_URL=http://localhost:8000`. This will be overridden by the Vercel environment variable.
2. **Backend CORS:** `backend/backend/core/config.py` defaults to `["http://localhost:5173", "http://127.0.0.1:5173"]`. This is safely overridden by the `BACKEND_CORS_ORIGINS` environment variable, which must be set in Render to include the new Vercel URL.
3. **Agent Backend URL:** `agent/agent/main.py` defaults `BACKEND_INTERNAL_URL` to `http://127.0.0.1:8000`. This must be overridden via the environment variable in the agent's deployment environment.
4. **Supabase Auth Redirect URL (CRITICAL):** As noted in `CURRENT_DECISIONS.md`, the OTP magic-link flow (`emailRedirectTo`) requires the new Vercel domain to be added to the Supabase project's **Redirect URL Allowlist** in the Supabase Dashboard (Authentication > URL Configuration).

## 6. Supabase Database Verification
The backend is **already pointing to a real remote Supabase Postgres instance**, not a local dev DB.
- `DATABASE_URL` in `.env` is set to `postgresql://postgres.[project-id]...aws-0-ap-southeast-1.pooler.supabase.com...`.
- *Note:* `backend/alembic.ini` contains a placeholder `sqlalchemy.url = driver://user:pass@localhost/dbname`, but this is safely overridden by `backend/alembic/env.py` which reads `DATABASE_URL` from the environment.

## 7. Build Configurations & Dockerfiles
**Status: Ready as-is.**
- **Backend:** `backend/Dockerfile` is correctly structured (Python 3.12-slim, copies `requirements.txt`, runs `uvicorn`).
- **Agent:** `agent/Dockerfile` is correctly structured and explicitly installs `ffmpeg` via `apt-get`, which is critical for LiveKit/Silero audio processing.
- **Render Config:** `render.yaml` exists and correctly defines the backend as a `web` service (running `alembic upgrade head` pre-deploy) and the agent as a `worker` service.

## Action Checklist Before Deployment
- [ ] **Decide on Agent Hosting:** Acknowledge that a free PaaS for the agent is unviable. Choose between paying ~$7/mo for Render Background Worker or manually deploying to a free GCP/Oracle VM.
- [ ] **Acknowledge Backend Cold Start:** Confirm if a ~45s delay for candidate links is acceptable for the prototype, or upgrade the backend to a paid Render tier (~$7/mo) to prevent sleeping.
- [ ] **Supabase Dashboard:** Add the Vercel domain to the Auth Redirect URL allowlist.
- [ ] **Set Environment Variables:** Prepare the three sets of environment variables (Frontend, Backend, Agent) using the actual deployed URLs (`VITE_API_BASE_URL`, `BACKEND_CORS_ORIGINS`, `BACKEND_INTERNAL_URL`).
