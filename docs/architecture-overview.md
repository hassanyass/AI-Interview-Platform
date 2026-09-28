# Himma Interview Platform — High-Level Architecture

Snapshot of what is **actually running** in production right now (2026-09-11), not a target/aspirational design. Every version number below is a pinned value confirmed directly from this repo's own lockfiles (`backend/requirements.txt`, `agent/requirements.txt`, `frontend/package.json`) — not a general assumption about "the latest version."

---

## 1. One-paragraph summary

Himma is a three-service system: a static React SPA (Vercel), a FastAPI REST backend (Render), and a Python LiveKit voice-agent worker (Railway) — sharing one Postgres database and one Supabase Auth tenant. A candidate's live interview is a real-time WebRTC session on LiveKit Cloud, with the agent worker as an AI participant conducting the interview by voice, backed by Groq (primary) or Azure Speech (fallback) for STT/TTS and Groq for the LLM reasoning that drives questions and evaluation.

---

## 2. Deployment topology

```
┌─────────────┐        ┌──────────────┐        ┌──────────────┐
│   Vercel    │  HTTPS │   Render     │ agent  │   Railway    │
│  frontend/  │───────▶│  backend/    │◀──────▶│  agent/      │
│  (static)   │  REST  │ (Docker svc) │  auth  │ (Docker      │
└─────────────┘        └──────────────┘ secret │  worker)     │
       │                      │                └──────────────┘
       │ direct                │                       │
       ▼                      ▼                       ▼
┌─────────────┐        ┌──────────────┐        ┌──────────────┐
│  Supabase   │        │  Supabase    │        │  LiveKit     │
│  Auth       │        │  Postgres    │        │  Cloud       │
└─────────────┘        └──────────────┘        └──────────────┘
                                                        │
                                          ┌─────────────┼─────────────┐
                                          ▼             ▼             ▼
                                    ┌─────────┐   ┌──────────┐  ┌──────────┐
                                    │  Groq   │   │  Azure   │  │Cloudflare│
                                    │ (LLM +  │   │  Speech  │  │    R2    │
                                    │ STT/TTS)│   │(fallback)│  │(recordings)│
                                    └─────────┘   └──────────┘  └──────────┘
```

**Why this split, specifically:**
- **Render (backend)**: genuine stateless HTTP API, fits the free-tier Web Service type correctly. Spins down after 15 min idle (~30–60s cold start on next request) — accepted tradeoff for a free demo.
- **Railway (agent)**: a real, always-listening background worker. Render's free tier has *no* background-worker instance type at all (confirmed against Render's own docs); Railway's Trial plan supports one, no card required.
- **Vercel (frontend)**: pure static SPA, no server functions used — genuinely free, no caveats.
- **Frontend never proxies through the backend for auth or media** — it talks to Supabase Auth and LiveKit Cloud directly from the browser; the backend only issues the LiveKit access token and handles everything else REST-shaped.

---

## 3. Tech stack by layer

### 3.1 Frontend — `frontend/` (Vercel)
| Concern | Technology | Version |
|---|---|---|
| Framework | React | 19.2.8 |
| Build tool | Vite | 8.2.0 |
| Language | TypeScript | ~6.0.2 |
| Routing | react-router-dom | 7.18.2 |
| Styling | Tailwind CSS | 4.3.3 (via `@tailwindcss/postcss`) |
| Auth client | @supabase/supabase-js | 2.112.3 |
| Real-time media | livekit-client + @livekit/components-react | 2.21.0 / 2.9.24 |
| Proctoring (face detection) | @mediapipe/tasks-vision | 1.0.1 |
| i18n (English/Arabic, RTL) | i18next + react-i18next | 26.4.0 / 17.0.12 |
| Icons | lucide-react | 1.31.0 |
| Testing | Vitest | 3.2.4 |

No state-management library (Redux/Zustand) — state is React Context (`AuthContext`, `RoleContext`) plus per-page local state. No server-state cache library (React Query/SWR) — direct `fetch` wrapper (`lib/api.ts`).

### 3.2 Backend — `backend/` (Render, Docker)
| Concern | Technology | Version |
|---|---|---|
| Framework | FastAPI | 0.141.1 |
| ASGI server | Uvicorn | 0.52.1 |
| ORM | SQLAlchemy (async) | 2.0.52 |
| DB driver | asyncpg | 0.31.0 |
| Migrations | Alembic | 1.19.1 |
| Config | pydantic-settings | 2.15.0 |
| Auth verification | PyJWT (+ JWKS via Supabase) | 2.13.0 |
| Supabase admin/storage client | supabase-py | 2.31.0 |
| LLM client | groq (official SDK) | 1.7.0 |
| LiveKit token/egress API | livekit-api | 1.2.0 |
| Object storage client | boto3 (S3-compatible, for R2) | 1.43.85 |
| PDF text extraction | PyMuPDF | 1.28.2 |
| Runtime | Python | 3.13 (Docker base `python:3.13-slim`) |

Nested package layout: `backend/backend/` (not a top-level `app/`) — `backend.main:app` is the real ASGI entrypoint.

### 3.3 Agent worker — `agent/` (Railway, Docker)
| Concern | Technology | Version |
|---|---|---|
| Framework | livekit-agents (LiveKit Agents SDK) | 1.7.1 |
| RTC core | livekit | 1.1.15 |
| STT/TTS/LLM plugin (primary) | livekit-plugins-groq | 1.7.1 |
| STT/TTS plugin (fallback) | livekit-plugins-azure | 1.7.1 |
| VAD (voice activity detection) | livekit-plugins-silero (+ onnxruntime) | 1.7.1 / 1.29.0 |
| LLM client (direct calls, outside the plugin) | groq | 1.7.0 |
| Azure Speech SDK | azure-cognitiveservices-speech | 1.51.2 |
| Runtime | Python | 3.13 |

Two independent Python installs exist locally for this project (repo `.venv` and a system-wide install) — both currently at the same `livekit-agents` version; not an issue today, worth watching for drift later.

### 3.4 Data & identity
| Concern | Technology |
|---|---|
| Database | Postgres, hosted by Supabase (accessed via the Supavisor pooler connection string) |
| Auth provider | Supabase Auth — email+password (admin), OTP (Flow-B candidates), JWT (ES256/RS256, JWKS-verified) |
| Guest identity (Flow-B pre-verification) | Locally-issued HS256 JWT (`SECRET_KEY`), `type: "guest"` claim, verified by the same `get_current_user_token_data` dependency as a real Supabase token |
| RBAC | Custom `users_roles` table (`admin`/`candidate`), not Supabase's own role system |

### 3.5 Real-time & AI infrastructure
| Concern | Technology |
|---|---|
| WebRTC SFU | LiveKit Cloud (region: UAE, confirmed from live worker registration logs) |
| Primary LLM + STT/TTS | Groq (model configurable via `GROQ_MODEL`, default `llama-3.3-70b-versatile`) |
| Fallback STT/TTS | Azure Speech (`TTS_PROVIDER=azure`) |
| Recording storage | Cloudflare R2 (S3-compatible), written by LiveKit Room Composite Egress, read via short-lived presigned GET URLs computed by the backend on demand |

---

## 4. Cross-cutting design decisions worth knowing before redesigning anything

- **The agent never touches Postgres directly.** Every read/write during a live interview goes through the backend's `/internal/*` routes, authenticated by a shared secret (`AGENT_API_SECRET`), not a user JWT. This is a deliberately frozen contract — changes here require explicit sign-off (see `CLAUDE.md`).
- **Two independent candidate identities, same session model.** Flow A (public apply link, self-registered) and Flow B (HR-sent invitation, OTP-verified) both end up as a normal `interview_sessions` row — the branching only happens at acquisition time (`P2.3` in the DFD doc), not downstream.
- **Migrations are additive-only.** No destructive schema rewrite has shipped alongside a feature; new columns are nullable, new tables stand alone. `alembic upgrade head` runs as part of the backend container's own start command (baked into the Dockerfile `CMD`), not as a separate deploy-time hook — Render's free tier doesn't support the `preDeployCommand` mechanism that would otherwise run it.
- **Long-running LLM calls are explicitly offloaded off the event loop** (`asyncio.to_thread`) in every backend service that calls Groq synchronously — a real production bug (a blocked event loop reading as a misleading CORS failure) was found and fixed this way for all three Groq-calling services in the backend.
- **A candidate's raw resume upload path (`resume_service.py`) currently degrades silently**: `supabase-py`'s `create_client()` rejects this project's newer-format `SUPABASE_SECRET_KEY` (`sb_secret_...`) with `Invalid API key` — its regex only accepts the old 3-segment JWT key shape. The module catches this and sets `supabase = None`, so resume-storage-dependent features fail quietly rather than crashing. Worth a real fix (bypass the SDK with a direct REST call, as already done for demo-account creation in `scripts/create_demo_admin.py`), not yet done for this path.
- **CORS is environment-driven** (`BACKEND_CORS_ORIGINS`, a JSON array string), currently allowing the deployed Vercel origin plus `localhost:5173` for local dev against the prod backend.
- **No message queue, no cache layer, no CDN in front of the backend** beyond what Render/Cloudflare provide by default. This is a deliberately minimal stack sized for a 2-week, ~10-user free-tier demo, not a scaled production system.

---

## 5. Known operational constraints (current, not hypothetical)

- Render free-tier backend cold-starts after 15 minutes idle (~30–60s first request).
- Railway's free Trial credit is a one-time $5 grant — real interview sessions (not just idle time) draw it down; worth checking Railway's usage dashboard periodically during the demo window.
- The shared Supabase database has accumulated a substantial amount of leftover test data from development (dozens of test `jobs` rows with names like "ai engineer", "Software", "n") — cosmetic clutter in the admin jobs list, not a functional issue, left untouched by explicit decision.
