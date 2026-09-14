# Deployment Readiness Audit (2026-09-02)

Exploration/audit only, per instruction — nothing was deployed or changed except this document. All claims below are sourced against real repo contents (file paths/line numbers given) or current, dated primary-source documentation (linked). Where a claim rests on a secondary/aggregator source instead of the vendor's own docs, that's called out explicitly.

**TL;DR:** The two hardest, most consequential findings are (1) **Render's free tier cannot run the agent worker at all** — not a policy nuance, a hard product limitation confirmed against Render's own docs — and (2) **the agent's existing `start.sh`/Dockerfile don't actually start the worker even ignoring hosting** (`python -m agent.main` with no subcommand prints CLI help and exits; confirmed by reading the installed `livekit-agents` CLI source directly). Both need a decision/fix before any agent deployment attempt, free or paid.

---

## 1. Agent layer (highest risk) — Render free tier does NOT support this

**Finding, sourced directly from Render's own docs** ([render.com/docs/free](https://render.com/docs/free)): the free tier covers **Web Services, Static Sites, Postgres, and Key Value only. Background Workers, Cron Jobs, and Private Services are explicitly excluded** — there is no free instance type for them at all, at any size. A second, independent search corroborates this in the same words ("You cannot select free instances for Background Workers or Cron Jobs"). This is not a rate limit or a "sleeps when idle" caveat like the web-service free tier has — it's a plan-eligibility wall. A Starter Background Worker starts at **$7/month**.

**This repo already anticipated the problem and built a workaround — which has two independent, serious problems:**

[`render.yaml`](render.yaml:26) deploys the agent as `type: web` (not `background_worker`), specifically to qualify for the free Web Service tier. [`agent/start.sh`](agent/start.sh:1) makes this pass Render's port-binding health check by running a **dummy `python -m http.server` on `$PORT` in the background, alongside** the real agent process:
```sh
python -m http.server ${PORT:-8000} &
python -m agent.main
```
Two things wrong with this, found independently:

1. **The free-tier sleep-after-15-minutes-inactivity behavior still applies, and nothing in this architecture would ever prevent it.** Render's own free-tier docs and current third-party coverage agree: a free Web Service spins down after 15 minutes with no *inbound HTTP request*, and the *entire container* stops — not just HTTP handling. The LiveKit agent worker's connection to LiveKit Cloud is an **outbound**, self-initiated connection; nothing in this system ever sends the dummy HTTP endpoint an inbound request to keep it alive. Once asleep, the whole container — including the LiveKit registration — goes down, and nothing here would wake it back up (LiveKit Cloud dispatches jobs over the connection the worker itself established; it doesn't "call back" over HTTP to wake a sleeping worker). In practice: the agent would go offline ~15 minutes after the last real interview session ended, and stay offline until *something* happens to hit its public URL. The only known mitigation is an external uptime-monitor ping (e.g. a free UptimeRobot check every ~10–14 minutes) — a real, commonly used pattern, but explicitly a fragile workaround, not a guarantee (a candidate could still hit a cold/asleep worker mid-connection).
2. **Independent of hosting entirely: `python -m agent.main` with no subcommand does not start the worker.** Confirmed by reading the installed `livekit-agents` package source directly (`.venv/Lib/site-packages/livekit/agents/cli/_legacy.py:1638-1642`):
   ```python
   @app.callback(invoke_without_command=True)
   def _set_dev_mode(ctx: typer.Context) -> None:
       if ctx.invoked_subcommand is None:
           print(ctx.get_help())
           raise typer.Exit()
   ```
   `start`, `dev`, `console`, and `download-files` are the real subcommands (same file, lines 1708/1767/1650/1914). **`start.sh` is missing the `start` subcommand** — as written today, the container would launch, the dummy HTTP server would bind the port and pass Render's health check, but the actual agent process would print help text and exit almost immediately, silently going offline forever with no crash/error surfaced anywhere. This is a pre-existing bug, not something introduced by the free-tier workaround, and would need fixing regardless of which host is chosen.

**Free alternatives researched for a genuinely long-running Python process (all checked against current, dated sources — my own knowledge cutoff is 8 months stale by "today"):**

| Option | Free? | Verdict |
|---|---|---|
| **Railway** | Effectively no | New accounts get a one-time $5 trial credit (no card required), consumed in days to weeks running 24/7; after that, a $1/mo "Free" plan exists but is too limited for real continuous use, and background workers are reportedly awkward to run reliably even on paid tiers. |
| **Fly.io** | No | Fly.io removed its free tier entirely in 2024. New orgs get a 2-hour-or-7-day trial, then a card is required; cheapest always-on Machine is ~$2–5/month. |
| **Koyeb** | No, for this use case | Free tier explicitly **cannot run Worker Services** (only a very small always-scale-to-zero web instance), and — separately — Koyeb closed free-tier signups to new users after its February 2026 acquisition by Mistral AI. |
| **Oracle Cloud "Always Free"** | Yes, genuinely, but with a real practical catch | Still a real, non-trial, permanent free tier in 2026 (Oracle halved the Ampere A1 ARM allowance in June 2026, from 4 OCPU/24GB to 2 OCPU/12GB — still plenty for this workload). **The catch, consistently reported**: provisioning an Ampere A1 instance frequently fails with "out of capacity" errors in most regions — a genuinely free VM that can be hard to actually obtain. The older, smaller AMD-based Always Free micro-VM shape has historically been more reliably available if the ARM shape can't be provisioned (not independently re-verified this session — flagged as an open question below). |
| **Google Cloud "Always Free" e2-micro** | Yes, genuinely, most reliable of the free options found | One e2-micro VM (shared vCPU, 1GB RAM) free forever, no trial expiry, restricted to `us-west1`/`us-central1`/`us-east1`, 30GB persistent disk included. This looks like the most dependable *actually-free-and-actually-gettable* option researched. Trade-off: a bare VM, not a PaaS — you own process supervision (systemd or Docker + restart policy), OS patching, and there's no push-to-deploy convenience like Render/Railway. |
| **Render Background Worker (paid)** | No, but cheapest *managed* option | $7/month, fully-managed, no workaround needed — `render.yaml` and `start.sh` would both get simpler (drop the dummy HTTP server, use `type: background_worker` directly). Worth naming even though the ask was "free," since the free-tier workaround's fragility (point 1 above) may cost more in reliability than $7/month is worth for real candidates. |

**This is a real decision for you to make, not one I should default silently:** free-but-fragile (Render web-service disguise + external uptime pinger, accepting some risk of a candidate hitting a cold/sleeping worker), free-but-more-ops (a self-managed GCP/Oracle VM), or $7/month for a fully-managed, reliable background worker. I have not picked one.

---

## 2. Backend layer — Render free tier fits the service type, but confirm you're OK with the cold-start UX

The backend is a genuine stateless HTTP API (FastAPI/Uvicorn) — this is exactly what Render's free "Web Service" type is built for, so hosting-model-wise this is the right fit, unlike the agent.

**Confirmed current behavior** (Render's own site plus corroborating current coverage): a free Web Service spins down after **15 minutes of no inbound HTTP traffic**, and the next request triggers a cold start with roughly a **30–60 second** delay before it responds (one source says "about one minute," another "30-60 second cold start" — consistent order of magnitude).

**Real UX impact, concretely**: if a candidate opens an interview invite link (or an HR user opens the admin dashboard) after the backend has been idle 15+ minutes, their *first* request — loading the invite page, registering, or logging in — will hang for up to a minute before anything happens, with no built-in loading state in the frontend today accounting for a wait that long (worth checking whether the current loading spinners read as "broken" past ~10-15 seconds). For "a small group of test users" trying this sporadically rather than continuously, this will be hit often, not as a rare edge case.

No code change is required to make the backend deployable on Render free — this is purely a product/UX call: accept the occasional 30-60s first-load delay, pre-warm the backend with an external ping before a scheduled test session, or pay for a non-sleeping instance.

---

## 3. Frontend layer — Vercel Hobby fits technically; one policy fact to flag, not decide

Confirmed directly against Vercel's own current docs ([vercel.com/docs/plans/hobby](https://vercel.com/docs/plans/hobby), page dated 2026-08-11 — current):

- **Technically sufficient and a good fit**: this is a pure static SPA (`vite build` → default `dist/` output, no Vercel serverless functions anywhere in this codebase), so it consumes essentially none of the Hobby plan's Function Invocations/Active CPU limits — just static hosting + bandwidth (100GB/month included) and the CDN. [`frontend/vercel.json`](frontend/vercel.json:1) already has the one config a client-side-routed SPA needs (a catch-all rewrite to `index.html`), and `vite.config.ts` uses no custom `build.outDir`, so Vercel's default Vite framework preset (build command `vite build`, output `dist`) needs no extra configuration.
- **Policy fact, not a technical one, confirmed from the same page**: *"the Hobby plan restricts users to non-commercial, personal use only"* (Vercel's fair-use guidelines, linked from that same doc). Path2Hire/Himma reads as a real hiring product, even at prototype stage — whether "a small group of test users" trying an early build counts as the kind of use Vercel means by "non-commercial, personal use" is a judgment call for you, not something to quietly assume either way. Practically, Vercel is very unlikely to notice or enforce against a handful of test users on a low-traffic Hobby project, but it's a real term you'd be relying on, not a technicality I should paper over.

---

## 4. Full environment variable inventory (current, from the actual files — not memory)

Values are never reproduced below — only variable names and, where useful, whether a real value vs. a placeholder is currently set. **Security note on how this was gathered:** while confirming the database wasn't pointing at localhost, an early redaction attempt of mine had a regex bug and briefly echoed a fragment of the real Supabase DB password into this conversation's tool output (the actual password contains an `@`, which my first-pass "redact between `:` and `@`" pattern didn't anticipate). Flagging this here as its own action item, matching this project's own precedent in `docs/PROJECT_STATUS.md`'s Security note: **rotate the Supabase DB password before or shortly after deploying**, independent of everything else in this report.

### Backend (`backend/backend/core/config.py`, loads `../.env` then `.env`)
| Variable | Required? | Notes |
|---|---|---|
| `SUPABASE_URL` | Yes (no default) | Confirmed points at a real project (`nbqhupxkmlwydaboilpj.supabase.co`), not a placeholder. |
| `SUPABASE_PUBLISHABLE_KEY` | Yes | |
| `SUPABASE_SECRET_KEY` | Yes | Backend-only, never expose to frontend. |
| `SUPABASE_JWKS_URL` | Yes | |
| `DATABASE_URL` | Yes | Confirmed real remote Supabase Postgres pooler (`*.pooler.supabase.com`) — see §6. |
| `LIVEKIT_URL` / `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` | Functionally yes (empty-string default) | Real LiveKit Cloud project confirmed configured. |
| `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_BUCKET_NAME` / `R2_ENDPOINT` | Functionally yes for recordings | PR-C proctoring recording storage; degrades gracefully if unset (no recording, not a crash — confirmed earlier this session). |
| `GROQ_API_KEY` / `GROQ_MODEL` | Functionally yes | Used for admin-side AI question generation. |
| `STT_PROVIDER` / `LLM_PROVIDER` / `TTS_PROVIDER` | Has defaults (`livekit`/`openai`/`livekit`) | Backend-side defaults — note these differ from the agent's actual runtime config (see below); backend mostly doesn't drive voice behavior directly. |
| `AGENT_API_SECRET` | Functionally yes | Shared secret between backend and agent for `/internal/*` calls — must match the same value set on the agent service. |
| `SUGGESTED_EVIDENCE_SUFFICIENCY_FLOOR` | No (default 0.5) | |
| `DISCONNECT_AUTO_FINALIZE_MINUTES` | No (default 10) | |
| `BACKEND_CORS_ORIGINS` | No (default is localhost-only) | **Must be updated at deploy time** — see §5. |
| `SECRET_KEY` | No (has an insecure dev default) | `"local_guest_jwt_secret_key_change_me_in_prod"` — **must be overridden with a real secret before any real deployment**, this default is a placeholder. |

### Agent (`agent/agent/main.py`) — confirmed by reading the actual `os.getenv(...)` call sites, not the `.env` file alone
| Variable | Required? | Notes |
|---|---|---|
| `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `GROQ_API_KEY`, `AGENT_API_SECRET`, `BACKEND_INTERNAL_URL` | **Hard-required** — `agent/agent/main.py:161-168` checks these explicitly and refuses to start (logs an error, returns) if any are missing. | `render.yaml`'s agent `envVars` list already covers exactly these 6 — correct and complete for the hard minimum. |
| `GROQ_STT_MODEL`, `GROQ_TTS_ENGLISH_MODEL`, `GROQ_TTS_ARABIC_MODEL`, `GROQ_TTS_ENGLISH_VOICE` | No (have defaults) | |
| `GROQ_API_KEY_1` … `GROQ_API_KEY_7` | No, but functionally important | Multi-key rotation for Groq's per-key daily TTS quota (`groq_key_rotator.py`) — **not in `render.yaml` today**; without these, the agent silently falls back to a single key (`GROQ_API_KEY`) with no rotation, reintroducing the exact "voice goes silent on quota exhaustion" problem this feature was built to fix. |
| `TTS_PROVIDER` | No — **but defaults to `"azure"`** (`agent/agent/main.py:406`) | The project's actual current, deliberate configuration is `"groq"` (per `docs/CURRENT_DECISIONS.md`/`.env`'s own comment, switched 2026-08-27). **Not in `render.yaml` today** — deploying with the current `render.yaml` as-is would silently run Azure TTS instead of Groq, and would then also be missing `AZURE_SPEECH_KEY`/`AZURE_SPEECH_REGION`, likely breaking voice output entirely. |
| `STT_PROVIDER`, `STT_ENDPOINT_DELAY_SECONDS`, `VAD_MIN_SILENCE_DURATION_SECONDS`, `WAITING_ROOM_TIMEOUT_SECONDS` | No (have defaults) | Tunable but not required for basic function. |
| `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION`, `AZURE_TTS_ENGLISH_VOICE`, `AZURE_TTS_ARABIC_VOICE` | Conditionally required (only if `TTS_PROVIDER=azure`) | |
| `DATABASE_URL`, `SUPABASE_*` (present in `agent/.env` today) | **Not actually used by the agent process** — confirmed by grep, zero references in `agent/agent/`. | The agent only ever talks to the database indirectly, through the backend's `/internal/*` API using `AGENT_API_SECRET`. These entries in `agent/.env` are dead weight for deployment purposes (kept there only for local-dev symmetry with the root `.env`, per that file's own comment) — don't need to be set on the deployed agent service. `render.yaml` already correctly omits them. |

### Frontend (`frontend/.env`, all `VITE_*` — publicly embedded in the built bundle, none of these are secrets by design)
| Variable | Required? | Notes |
|---|---|---|
| `VITE_SUPABASE_URL` | Yes | |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Yes | This is the public/anon key — safe to embed in a client bundle by design. |
| `VITE_API_BASE_URL` | Yes | Currently `http://localhost:8000` — **must be set to the deployed backend's real URL in Vercel's project env vars.** Confirmed properly read via `import.meta.env.VITE_API_BASE_URL` in `frontend/src/lib/api.ts:4`, not hardcoded anywhere — this is a config change, not a code change. |
| `VITE_FACE_DETECTION_INTERVAL_SECONDS`, `VITE_HEAD_DOWN_CONFIRM_THRESHOLD`, `VITE_HEAD_DOWN_PITCH_THRESHOLD_DEGREES`, `VITE_HEAD_POSE_DEBUG` | No (all have defaults) | Proctoring tuning constants, optional. |

---

## 5. Hardcoded localhost / CORS audit

Grepped `backend/backend/`, `agent/agent/`, and `frontend/src/` for `localhost`/`127.0.0.1`. **Every single match found is a code-level fallback default for an environment variable, not a hardcoded value that would silently break in production** — genuinely good news, nothing found here needs a code change:

- [`backend/backend/core/config.py:51`](backend/backend/core/config.py:51) — `BACKEND_CORS_ORIGINS` default, overridden by the real env var.
- [`agent/agent/main.py:188`](agent/agent/main.py:188) — `BACKEND_INTERNAL_URL` default, overridden by the real env var (and already in `render.yaml`).
- [`frontend/src/lib/api.ts:4`](frontend/src/lib/api.ts:4) — `VITE_API_BASE_URL` default, overridden by the real env var.
- No hardcoded `localhost`/`127.0.0.1` anywhere else in `frontend/src/` at all (confirmed empty grep result).

**What genuinely needs a config change (not code) at deploy time:**
1. **`BACKEND_CORS_ORIGINS`** on the deployed backend must include the real Vercel frontend origin (currently only lists local dev ports). Without this, every browser request from the deployed frontend to the deployed backend will be blocked by CORS.
2. **Supabase Auth → Redirect URLs allowlist** (a Supabase *dashboard* setting, not a repo file) must have the new Vercel origin added. Confirmed the code side is already correct and dynamic — `frontend/src/pages/InvitePage.tsx:91` uses `emailRedirectTo: window.location.href` (the actual current page URL at runtime, not a hardcoded value) — so once the allowlist is updated, the OTP magic-link flow should work at the new domain without any code change. `docs/PROJECT_STATUS.md` already notes this exact allowlist was hit once before during Phase 6 dev — expect to hit it again for the new domain.
3. **`BACKEND_INTERNAL_URL`** on the deployed agent must point at the deployed backend's real URL, not `127.0.0.1`.
4. **`VITE_API_BASE_URL`** on Vercel must point at the deployed backend's real URL.

---

## 6. Database — confirmed real remote Supabase Postgres, not local

Confirmed (host only, credentials never re-displayed after §4's incident): `DATABASE_URL`'s host is a real Supabase Session/Transaction Pooler address (`*.pooler.supabase.com`, region `ap-southeast-1`), matching the same project as `SUPABASE_URL` (`nbqhupxkmlwydaboilpj.supabase.co`). **Not a local dev database** — confirmed rather than assumed, as asked.

---

## 7. Existing build/deploy configs — found, not absent (with real bugs to fix)

Contrary to a "Render will need to auto-detect this from scratch" assumption: **this repo already has `render.yaml`, `backend/Dockerfile`, `agent/Dockerfile`, `agent/start.sh`, and `frontend/vercel.json`**, all previously written (not part of this session). Reading them closely surfaced several concrete, verified issues:

| File | Issue | Confirmed how |
|---|---|---|
| [`backend/Dockerfile:13`](backend/Dockerfile:13) | `CMD` runs `uvicorn app.main:app` — **there is no `app` package.** The real, only-existing module path is `backend.main:app` (`backend/backend/main.py`, matching how it's actually run today — `uvicorn backend.main:app`). As written, the built image would crash on startup with `ModuleNotFoundError`. | Directly listed `backend/`'s real directory structure. |
| [`agent/start.sh:8`](agent/start.sh:8) | `python -m agent.main` has **no subcommand** — confirmed via the installed `livekit-agents` CLI source that this prints help text and exits rather than starting the worker (see §1). Needs to be `python -m agent.main start`. | Read `.venv/Lib/site-packages/livekit/agents/cli/_legacy.py` directly. |
| Both Dockerfiles | Pin `python:3.12-slim`, but the local dev environment (`.venv`) — the one the fully-pinned `backend/requirements.txt` lockfile was generated from — is **Python 3.13.5**. Installing those exact pinned versions under 3.12 in the image risks a dependency that only ships 3.13 wheels, or subtly different resolved behavior. | `.venv/Scripts/python.exe --version`. |
| [`backend/requirements.txt`](backend/requirements.txt) | The file is **UTF-16LE encoded** (with BOM), unusual for a `requirements.txt` — almost certainly produced by a PowerShell redirect without `-Encoding utf8`. **Confirmed NOT a real blocker**: a live `pip install --dry-run -r requirements.txt` parsed it correctly, and `pip`'s own `auto_decode()` utility explicitly detects and handles a UTF-16 BOM regardless of platform — but it's non-standard enough (could trip up some other tool later, e.g. a dependency scanner) to be worth normalizing to plain UTF-8 for hygiene. | Direct `file`/byte inspection + a real `pip install --dry-run` run. |
| [`agent/requirements.txt`](agent/requirements.txt) | **Zero version pins** on every dependency (`livekit-agents`, all four `livekit-plugins-*`, `groq`, `pydantic`, `python-dotenv`) — unlike the backend's fully-pinned file. A fresh Docker build today vs. one built later could silently pull a breaking major version of `livekit-agents` itself (whose own CLI has visibly been in flux — the deprecation warnings seen live this session for "dev mode"/"in-process auto-reload" are exactly the kind of change an unpinned install would absorb without warning). Recommend generating a real pinned lock (e.g. `pip freeze` from the current working local environment) before deploying. | Read the file directly. |
| [`render.yaml`](render.yaml:26-43) | Agent service's `envVars` list is missing `TTS_PROVIDER`, `GROQ_API_KEY_1`…`GROQ_API_KEY_7`, and (conditionally) the `AZURE_SPEECH_*`/voice-override variables — see §4 for the concrete behavioral risk (silently defaults to Azure TTS with no Azure credentials set). | Cross-referenced against `agent/agent/main.py`'s actual `os.getenv()` call sites. |
| `.dockerignore` (both `backend/` and `agent/`) | **Already correct** — both exclude `.env`/`.env.*`, so `agent/.env` (which sits inside the agent build context) does not get baked into the image. Nothing to fix here. | Read both files directly. |
| `render.yaml`'s `preDeployCommand: alembic upgrade head` | Looks correct — `rootDir: backend` matches where `alembic.ini` actually lives (`backend/alembic.ini`). Not independently re-verified against a live Render deploy this session (no deploy was performed, per instruction). | File structure check only — flagging as not fully verified rather than claiming certainty. |

---

## Follow-up research (2026-09-02): can the agent run as a subprocess INSIDE the backend's container?

Explored whether the agent worker could run as a background subprocess within the same Render free-tier container as the FastAPI backend — the backend's real inbound HTTP traffic would keep the whole container from sleeping, solving both free-tier problems (no worker support, sleep-after-idle) without a second host. **Conclusion: not viable, on real measured resource evidence, independent of the two already-fixed bugs below.**

**1. Render's real free-tier allocation, confirmed from Render's own docs** ([render.com/docs/compute-plans](https://render.com/docs/compute-plans)): a free Web Service gets **0.1 CPU and 512 MB RAM**. Not an estimate — the docs page states it in exactly those terms.

**2. Real measured memory footprint of this project's own processes** (local dev machine, not assumed from general knowledge of what FastAPI/livekit-agents "typically" use):
- The backend (`uvicorn backend.main:app`, fully loaded — FastAPI, SQLAlchemy, Supabase client, boto3, etc.) idles at **~145-170MB working set** with zero active requests.
- The agent worker's own **main process alone** idles at **~162MB working set / ~492MB private memory** — before a single interview session starts. This is with all four plugins loaded (`openai`, `groq`, `silero`, `azure`) plus their dependency trees (numpy, PyAV/ffmpeg bindings, grpc, opentelemetry).
- **livekit-agents pre-spawns an idle job-executor subprocess by default** (confirmed via `worker.py`'s `num_idle_processes` option, and directly observed as a second live process at startup) — an *additional* **~94MB working set**, again before any real interview begins. This isn't a tunable-away architectural detail either: `JobExecutorType.PROCESS` (the default, for real crash/OOM isolation between concurrent candidate sessions) is what creates it; `JobExecutorType.THREAD` exists as an alternative (confirmed in `job.py`) but trades away that isolation — a single interview session's bug or memory leak could then take down every other concurrent session *and*, in this exact combined-container scenario, the FastAPI backend serving on the same box.
- **Combined, at pure idle, with zero active interviews**: backend (~150MB) + agent main process (~162MB) + one idle job executor (~94MB) already totals **~400MB+ working set** against a 512MB ceiling — before accounting for a single live session's actual runtime cost (STT/TTS audio streaming buffers, LLM request/response buffering, real-time audio encode/decode). There isn't a plausible reading of these numbers where one real concurrent interview fits in the remaining headroom, let alone the FastAPI backend continuing to serve other requests at the same time.
- **CPU is the same story, arguably worse**: 0.1 CPU is a small fraction of one core, shared between FastAPI's request handling and the agent's real-time audio pipeline (VAD, STT/TTS streaming, LLM orchestration) if combined. This project already spent real, documented effort (`docs/realtime-voice-hardening.md`, RT-A/RT-B in `docs/PROJECT_STATUS.md`) diagnosing and fixing voice-pipeline symptoms — clashing audio, premature cutoff, intermittent delay — caused by timing/scheduling issues *within a single dedicated process*. Deliberately introducing CPU contention with an unrelated HTTP-serving process on 1/10th of a core would risk reintroducing that exact symptom class from a new, harder-to-diagnose cause.

**3. The process-model question itself, checked directly against the installed `livekit-agents` source** (`.venv/Lib/site-packages/livekit/agents/cli/_legacy.py`): `cli.run_app()` does **not** require being the container's PID 1 or foreground process. Its shutdown handling is ordinary Unix signal handling (`HANDLED_SIGNALS = (SIGINT, SIGTERM)`, `signal.raise_signal(...)`) — nothing PID-1-specific was found (no zombie-reaping assumption, no requirement to own the terminal). Architecturally, spawning it via `subprocess.Popen(["python", "-m", "agent.main", "start"], ...)` from a FastAPI lifespan hook (or a shell script launching both) would work, and log separability is a solved problem, not a blocker — a background thread reading the subprocess's `stdout`/`stderr` line-by-line and re-emitting each line with an `[agent]` prefix (or writing to a separate file) keeps both processes' output legible. **This part of the idea is sound — it's overridden by the resource math above, not by any process-model incompatibility.**

**Recommendation: don't merge them.** The two already-identified VM fallbacks from the original audit stand: **Google Cloud's free e2-micro** (more reliably provisionable, per the earlier research) or **Oracle Cloud's Always Free** tier (genuinely free but with real reported capacity/provisioning friction for the ARM shape) — both give the agent a dedicated allocation sized to what it actually needs, measured, not estimated. The $7/month Render Background Worker remains the simplest *paid* option if a fully-managed host is worth that much to avoid VM ops.

## Bugs fixed this pass (independent of the hosting decision)

Per the instruction to fix these regardless of which path is chosen:
- [`backend/Dockerfile`](backend/Dockerfile) — `CMD` now runs `uvicorn backend.main:app` (was `app.main:app`, a nonexistent module that would have crashed on container startup).
- [`agent/start.sh`](agent/start.sh) — now runs `python -m agent.main start` (was missing the `start` subcommand entirely; confirmed via source inspection that this previously printed CLI help and exited without ever starting the worker, regardless of host).

Both are simple, isolated text fixes — not re-verified with a fresh live deploy (out of scope for a research/planning pass), but `start` is confirmed to exist as a real subcommand in the installed `livekit-agents` package, and `dev` mode (the same underlying registration path, per this session's own live runs) has already been confirmed working end-to-end against the real LiveKit Cloud project multiple times.

## Checklist

**Ready as-is (no change needed):**
- Backend CORS, agent's `BACKEND_INTERNAL_URL` default, and frontend's `VITE_API_BASE_URL` default are all env-driven, not hardcoded — confirmed via grep across all three layers.
- `frontend/vercel.json`'s SPA rewrite rule is correct and sufficient; no `vite.config.ts` output-dir mismatch with Vercel's default Vite preset.
- `DATABASE_URL` already points at a real remote Supabase Postgres pooler, not a local DB.
- `.dockerignore` for both backend and agent correctly excludes `.env` files from the Docker build context.
- `render.yaml`'s hard-required agent env vars (6 of them) match exactly what `agent/agent/main.py` actually requires to start.
- `emailRedirectTo` in `InvitePage.tsx` is already dynamic (`window.location.href`), needing no code change for a new domain.

**Needs a code/config change before deploying:**
- ~~Fix `backend/Dockerfile`'s `CMD` module path~~ — **done, 2026-09-02** (`app.main:app` → `backend.main:app`).
- ~~Fix `agent/start.sh`'s missing `start` subcommand~~ — **done, 2026-09-02** (`python -m agent.main` → `python -m agent.main start`).
- Add the missing env vars to `render.yaml`'s agent service (`TTS_PROVIDER`, the `GROQ_API_KEY_1..7` pool, and `AZURE_SPEECH_*` if kept as a fallback).
- Set real deploy-time values: `BACKEND_CORS_ORIGINS` (add the Vercel origin), `BACKEND_INTERNAL_URL` (agent → real backend URL), `VITE_API_BASE_URL` (frontend → real backend URL), a real `SECRET_KEY` (not the placeholder default).
- Add the new Vercel origin to Supabase's Auth Redirect URLs allowlist (dashboard, not code).
- Rotate the Supabase DB password (this session's redaction-bug leak, §4 — independent of everything else).
- Pin `agent/requirements.txt`'s dependencies (currently fully unpinned).
- Recommended, not confirmed-blocking: normalize `backend/requirements.txt` to UTF-8, and align both Dockerfiles' `python:3.12-slim` to `python:3.13-slim` to match the environment the pinned lockfile was actually generated from.

**Open research questions (need your decision, not mine):**
- Whether "a small group of test users" trying an early hiring-product build is comfortably within Vercel Hobby's "non-commercial, personal use" restriction, or whether that's a line you'd rather not rely on.
- Whether the backend's 30-60s cold-start delay after 15 minutes idle is acceptable UX for test candidates, or worth avoiding (a paid always-on instance, or an external keep-warm ping).
- `render.yaml`'s `preDeployCommand: alembic upgrade head` wiring was checked for structural correctness only, not exercised against a real Render deploy.

## Resolved (2026-09-03): agent hosting is Railway, not Render

The "how to host the agent worker" question above is now settled — see
`docs/CURRENT_DECISIONS.md`'s "Agent worker hosting: Railway" entry for
the full comparison and evidence. Render's free tier is confirmed
structurally unable to run a real background worker at all (Web
Services, Static Sites, Postgres, and Key Value are the only free-tier
eligible types), and combining agent+backend in one container was
separately ruled out on measured RAM/CPU evidence. Railway's free Trial
(confirmed no credit card required, directly from Railway's own pricing
page) genuinely supports a real background-worker deployment — no
`$PORT`, no public domain, no ongoing healthcheck required, confirmed
directly against Railway's own docs.

**As part of this, re-examined and fixed for real deployment readiness:**
- `render.yaml` was missing two *required* backend env vars
  (`SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_JWKS_URL` — `Settings` has no
  default for either, so the backend would have crashed on boot with a
  Pydantic `ValidationError` before serving a single request). Also
  missing `GROQ_API_KEY`/`GROQ_MODEL` (needed by three backend-side AI
  features built this session) and a real `SECRET_KEY` override. All
  added, plus the R2 vars (recordings confirmed wanted for this
  deployment). The `ai-interview-agent` service block is removed
  entirely — the agent no longer deploys to Render at all.
- `agent/start.sh` simplified to just `python -m agent.main start` — the
  dummy-HTTP-server-for-Render's-benefit trick is dead weight now that
  Railway needs none of it.
- `agent/requirements.txt` — was completely unpinned; now a real, clean
  pin generated by installing the exact same package list into a fresh,
  isolated throwaway virtualenv (avoiding contamination from the shared
  dev `.venv`'s other dependencies) and freezing it. Confirmed installs
  cleanly (it's a direct freeze of a successful install, not hand-typed).
- Both Dockerfiles aligned from `python:3.12-slim` to `python:3.13-slim`,
  matching the actual local environment (3.13.5) both pinned lockfiles
  were generated against.
- `docs/deployment-guide.md` rewritten for the Render+Vercel+Railway plan
  with the corrected, complete env var lists for all three platforms.

**Still open, flagged explicitly, not resolved by this pass:** the
Supabase DB password rotation mentioned earlier in this engagement was
confirmed still not finished as of this writing — this blocks the actual
deploy (a wrong `DATABASE_URL` would fail immediately), not the code/config
prep, which doesn't touch the credential itself.
