# Deployment Guide — Free Tier, No Credit Card (2026-09-03 revision)

Supersedes the previous "Render for everything, disguise the agent as a web
service" plan. That plan is still technically possible (the code paths for
it still exist in git history), but is deliberately not the one below —
see `docs/deployment-readiness.md`'s full comparison for why. **This
revision: Render (backend) + Vercel (frontend) + Railway (agent worker)**,
confirmed genuinely free and card-free on all three as of this writing.

## Architecture
- **Frontend (Vercel)**: 100% free, static SPA, no functions used.
- **Backend (Render Web Service)**: free tier fits this correctly — it's a
  genuine stateless HTTP API. Spins down after 15 minutes idle, ~30-60s
  cold start on the next request — a real, accepted UX tradeoff for a
  free demo, not a bug.
- **Agent worker (Railway)**: a real background-worker deployment, not a
  disguise. Confirmed directly against Railway's own docs: no `$PORT`, no
  public domain, and no ongoing healthcheck are required for a
  non-HTTP worker to keep running. Railway's Trial plan gives a one-time
  $5 credit with **no credit card required** (confirmed on Railway's own
  pricing page) — comfortably enough for a light, mostly-idle worker over
  a 2-week window, though real interview sessions cost more than pure
  idle time, so it's worth checking Railway's usage dashboard partway
  through rather than assuming the full 2 weeks is guaranteed.

## Prerequisites
- A GitHub repository containing the latest code (this revision's
  `render.yaml`/`agent/start.sh`/pinned `agent/requirements.txt`).
- A [Vercel account](https://vercel.com/) — no card required.
- A [Render account](https://render.com/) — no card required.
- A [Railway account](https://railway.com/) — no card required (confirmed:
  *"Can I try Railway without a credit card? Yes... No credit card
  required."*).
- Your Supabase, LiveKit, Groq, and (if using recordings) Cloudflare R2
  credentials.
- **Before starting**: confirm the Supabase DB password rotation (if one
  was in progress) is actually finished, and that whatever value you type
  into Render's `DATABASE_URL` is the current, real password.

---

## Step 1: Render (Backend only)

1. Go to your [Render Dashboard](https://dashboard.render.com/).
2. Click **New** → **Blueprint**, connect your GitHub repository. Render
   reads `render.yaml`, which now proposes exactly **one** service:
   `ai-interview-backend`.
3. **Instance Type**: Free.
4. **Environment Variables** — Render will prompt for each of these
   (matching `render.yaml`'s current list exactly; the previous version of
   this guide was missing two of the *required* ones, which would have
   crashed the backend on boot):
   - `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`,
     `SUPABASE_JWKS_URL` — all four required, no defaults.
   - `DATABASE_URL` — the Supabase **Supavisor pooler** connection string
     (not the direct connection string), required.
   - `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`.
   - `SECRET_KEY` — generate a real random value (e.g. `openssl rand -hex
     32`); do **not** leave this at the code's own placeholder default.
   - `GROQ_API_KEY`, `GROQ_MODEL` — used by the backend itself for AI
     question generation, the invitation-message composer, and evaluation
     regeneration.
   - `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`,
     `R2_BUCKET_NAME`, `R2_ENDPOINT` — for recording playback (confirmed
     wanted for this deployment).
   - `BACKEND_CORS_ORIGINS` — leave a placeholder for now (e.g.
     `["http://localhost:5173"]`); you'll update this for real in Step 4.
   - `AGENT_API_SECRET` — a secure random string you generate; the exact
     same value goes into Railway's agent env vars in Step 2.
5. Click **Apply**. `preDeployCommand: alembic upgrade head` runs your
   migrations automatically on every deploy.
6. Once deployed, note the backend's public URL (e.g.
   `https://ai-interview-backend.onrender.com`).

---

## Step 2: Railway (Agent worker)

1. Go to your [Railway Dashboard](https://railway.com/dashboard) and sign
   up/log in — no card required.
2. **New Project** → **Deploy from GitHub repo**, select this repository.
3. Once the service is created, open its **Settings**:
   - **Root Directory**: `agent` (Railway will then find `agent/Dockerfile`
     automatically — it looks for a `Dockerfile` at the root of whatever
     directory you point it at).
   - **Networking**: leave this service **private** — it never needs a
     public domain. It only makes outbound calls (to LiveKit Cloud and to
     the Render backend's public URL); nothing ever calls into it.
4. **Variables** tab — set every one of these (all are read directly by
   `agent/agent/main.py`; the first six are hard-required and the process
   refuses to run without them):
   - `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`
   - `GROQ_API_KEY`
   - `AGENT_API_SECRET` — must exactly match what you set on Render in
     Step 1.
   - `BACKEND_INTERNAL_URL` — the Render backend's public URL from Step 1
     (e.g. `https://ai-interview-backend.onrender.com`). This is a normal
     outbound HTTPS call across providers — no special cross-provider
     networking setup needed, since Railway's *private* networking only
     applies between services inside the same Railway project.
   - `TTS_PROVIDER` — set to whatever this project is actually configured
     to use (confirm against your own `.env`; defaults to `azure` in code
     if unset, which is easy to silently deploy wrong).
   - `GROQ_API_KEY_1` through `GROQ_API_KEY_7` (optional but recommended)
     — the multi-key rotation pool for Groq's per-key daily TTS quota.
   - `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` — only if `TTS_PROVIDER` is
     `azure` or you want it as a fallback.
5. Deploy. Check the service's **Logs** tab for the same "registered
   worker" line you'd see locally (`docs/LOCAL_DEMO_SETUP.md` shows exactly
   what a healthy startup looks like) — that's the real proof it
   registered with LiveKit Cloud, not just that the container started.

---

## Step 3: Vercel (Frontend)

1. Go to your [Vercel Dashboard](https://vercel.com/dashboard) → **Add
   New** → **Project** → import this repository.
2. **Framework Preset**: Vite (auto-detected). **Root Directory**: `frontend`.
3. **Environment Variables**:
   - `VITE_SUPABASE_URL`
   - `VITE_SUPABASE_PUBLISHABLE_KEY` (the public/anon key — safe to embed
     in a client bundle by design)
   - `VITE_API_BASE_URL` — the Render backend URL from Step 1.
4. Deploy. Note the resulting Vercel URL (e.g.
   `https://your-app.vercel.app`).

---

## Step 4: Wire up CORS and Supabase Auth

1. **Render → `ai-interview-backend` → Environment**: update
   `BACKEND_CORS_ORIGINS` to include your real Vercel URL, e.g.
   `["https://your-app.vercel.app"]`. Saving triggers an automatic
   redeploy.
2. **Supabase Dashboard → Authentication → URL Configuration**: set
   **Site URL** to your Vercel URL, and add it (with `/**`) to **Redirect
   URLs**. This is required for the OTP/magic-link candidate flow to
   redirect back to the deployed app instead of `localhost` — the code
   side of this (`emailRedirectTo: window.location.href`) is already
   dynamic and needs no change.

## Validation
1. Open the Vercel URL, log in as admin.
2. Publish a job, generate an invite link or send yourself an invitation.
3. Start a real interview end-to-end: the frontend should get a LiveKit
   token from Render, connect to LiveKit Cloud, and the Railway-hosted
   agent should join the room and start speaking — check Railway's logs
   live during this to confirm the job dispatch actually reached it.
4. Expect the **first** request to Render after any 15-minute idle period
   to take 30-60 seconds (the free-tier cold start) — this is expected,
   not a failure.
