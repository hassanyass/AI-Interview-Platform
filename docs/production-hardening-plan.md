# Production hardening — phased plan (2026-09-21)

Goal: turn the Himma / Path2Hire prototype (FastAPI backend, LiveKit
`livekit-agents` voice worker, React/Vite frontend) into a production-grade,
handover-ready product for e&: packaged as portable containers, no
hard-coded provider or policy values, provider logic behind interfaces,
consistent error handling, observability, automated tests with CI, and a
security posture that survives an audit. **Product behaviour is frozen** —
every screen and API keeps doing what it does today; only structure,
reliability, operations, tests and security change.

This is the *overall* plan. Each phase is executed as its own task under the
same discipline as `.claude/skills/transition-phase/SKILL.md` and
`AGENTS.md` §4: **Explore → Plan → wait for approval → Execute → Verify**,
one phase (or sub-phase) per approval. Nothing in this document is code.

Status: **H0, H1, H2 (A–F), H3 built, verified and committed (through 2026-09-23; one commit
per phase). Live DB at head `a3f7d05c1e94` (the compose `migrate` service applied the H2-F
table during its check, §20). Owed: one live interview check (H2-C/D/E items) and one
live admin-driven generation through the new queue (needs an admin login). Next: H4
(tests + CI), after examine + confirm.**

---

## 0. Decisions that scope this plan (all confirmed by the owner)

| # | Decision (2026-09-17 / 2026-09-21) | Consequence |
|---|---|---|
| S1 | Hosting undecided; explicitly **not** Render/Vercel/Railway long-term | Deliverable is a portable container stack (compose today, k8s-mappable), not a cloud-specific deploy. `render.yaml` is kept until H6 decides its fate. |
| S2 | Load = 1000+ candidates **total**; no concurrency target | H6 measures a baseline (concurrent live interviews on one worker) and records it; no autoscaling work. |
| S3 | Single tenant (e&), current flow only; no multi-tenancy, RBAC expansion or white-label | No schema changes for tenancy. Existing `admin` role stays. |
| S4 | Priorities in order: **reliability & error handling → observability & ops → tests & CI/CD → security & compliance** | Phase order below follows this after the two foundation phases (H0, H1) that everything else depends on. |
| S5 | Fixed stack: **Python/FastAPI + React/Vite/TS only**. Supabase, LiveKit, Groq/TTS/STT, storage, email are *not* fixed | Each external dependency sits behind a provider interface selected by configuration (H1). No vendor is switched in this plan. |
| S6 | Behaviour frozen; production gaps (email) get the provider **infrastructure and integration point**, but stay inert until a vendor is chosen | `EmailProvider` port + `NullEmailProvider`; the composer's Send keeps its current outcome. |
| S7 | Testing: unit + integration against a **real disposable Postgres**; no browser e2e in CI | Docker Postgres + real Alembic migrations in CI; frontend component tests in jsdom. |
| S8 | Handover-grade documentation for **e& IT / another vendor** | Runbooks, architecture, env matrix, ADRs live in a tracked `docs/handover/` (not in the git-ignored `CLAUDE.md`/`AGENTS.md`, which are deliberately untracked). |
| S9 | Background jobs: **DB-backed job table + in-process worker, Postgres advisory lock** | No Redis/Celery. `JobQueue` port so it can be swapped later. |
| S10 | Root test scripts (`test_phase*.py`, `verify_9*.py`, `conftest.py`): **move under `tests/legacy/`, run against the test DB** | Moved unchanged (git `mv`), pointed at `TEST_DATABASE_URL`, kept green as regression coverage. |
| S11 | Cleanup may delete: dead frontend code, stray root artefacts, `frontend/test_5c.cjs`, `New Avatar/` | A final listing is shown for OK at that step (H0-B) before anything is removed. |
| S12 | Frozen `controller.py`: **one scoped sub-phase** (H2-C) with its own approval gate | Fix the `IM_READY` `NameError`, route English fallback strings through the language table, require a confirmation control before keyword-triggered `END_INTERVIEW`. No contract change. |

Standing rules that bind every phase (AGENTS.md): additive-only migrations;
`agent/agent/interview/controller.py` and `/internal/*` are frozen except
under H2-C; `InterviewerCharacter.tsx` untouched; legacy names
(`InterviewConfiguration`, `InterviewSession`) stay; no test file deleted
or moved without the consent recorded in S10/S11; the responsive track
(`docs/responsive-design-plan.md`, R0–R2B staged uncommitted) is parallel
work this plan must not undo.

### Still unresolved — the plan does NOT decide these (AGENTS.md §5)
- **U1 Data retention.** How long candidate recordings, transcripts and
  CVs are kept, and who may delete them. H5 builds the deletion *mechanism*
  (a job that can purge by age/status) but ships it disabled until you set
  the policy in `CURRENT_DECISIONS.md`.
- **U2 Commit cadence — RESOLVED 2026-09-22.** Responsive R0–R2B and
  hardening H0–H2-D were committed as two separate commits (`c2dff10`,
  `d6079cc`); from H2-E on, one commit per verified phase.
- **U3 Duplicate `users_roles` rows.** The audit found no unique index
  (`MultipleResultsFound` risk). Adding one is additive, but if duplicates
  exist in the live DB the migration fails. H2 adds the index only after a
  read-only check you approve; the dedupe itself needs your OK.
- **U4 Concurrency acceptance.** H6 will *measure* how many simultaneous
  live interviews one agent worker sustains; whether that number is enough
  is a product call.
- **U5 CV extraction failure status.** A transient LLM failure during CV
  parsing today keeps the upload and marks the resume `COMPLETED` with an
  empty profile (deliberate: the candidate is not blocked by a Groq blip;
  the upload endpoint 500s on `FAILED`). Kept as-is in H2-B by the owner's
  decision; revisit if HR needs "profile missing" to be visible.

---

## 1. Ground rules for every phase ("no leftovers" guardrails)

1. **Behaviour parity is the acceptance test.** Every phase ends by running
   the existing live flows (login → publish → apply → intro → one verbal
   section → results) and the full test suite; any diff in behaviour is a
   defect unless the phase explicitly lists it.
2. **Config, not code.** A value is hard-coded only if it is a *protocol*
   constant. Everything else (models, bucket names, TTLs, timeouts, limits,
   sweep intervals, provider names, CORS, feature switches) is a typed,
   validated setting with a documented default. §1 of H1 lists every value
   being lifted; a phase may not add a new hard-coded value.
3. **Ports before adapters.** External systems are reached only through an
   interface in `backend/backend/providers/` or `agent/agent/providers/`;
   the concrete adapter is chosen by a factory from settings. No router,
   service or controller imports `groq`, `boto3`, `httpx`, `aiohttp`,
   `livekit.api` directly after H1.
4. **Fail closed, fail loud.** Missing required config refuses to boot in
   any `ENVIRONMENT != local`. No `except Exception: pass`; every catch
   either handles, translates to a typed error, or re-raises. Every external
   call has a timeout; every retry has a cap and is logged.
5. **Additive migrations only.** New tables, nullable columns, indexes.
   Nothing dropped or made mandatory in this plan.
6. **Frozen contracts.** `controller.py` and `/internal/*` change only in
   H2-C, byte-identical otherwise. `InterviewerCharacter.tsx` never.
7. **Scope discipline.** A phase touches only the files in its own plan.
   Findings on the way go to §6 (parking lot).
8. **Test-file discipline.** Existing tests are moved only as S10 allows,
   never deleted or rewritten; new tests are added beside them.
9. **Verification is evidence.** Each phase pastes: `pytest` output (backend
   + agent + legacy), `npm run typecheck && npm run lint && npm test`,
   container build output, and the live-flow checklist ticked.

---

## 2. Target architecture (what "done" looks like)

```
repo/
  compose.yaml            # dev: postgres, migrate (one-shot), backend, agent, frontend(dev)
  compose.prod.yaml       # prod: migrate, backend, agent, web (nginx + built frontend)
  .github/workflows/ci.yml
  backend/
    backend/
      core/config.py      # single typed Settings; fail-closed validation
      core/errors.py      # AppError hierarchy → RFC 7807 problem responses
      core/logging.py     # JSON logs, request_id / session_id context
      providers/          # ports + adapters, chosen by settings
        llm/  (base.py, groq.py)
        storage/ (base.py, s3_compatible.py)        # R2 today, S3-compatible
        realtime/ (base.py, livekit.py)             # token + egress
        email/ (base.py, null.py)                   # inert until vendor chosen
        notifications/ (existing base.py, console.py — moved, unchanged)
        jobs/ (base.py, db_queue.py)                # JobQueue port + advisory-lock worker
      services/           # domain logic lifted out of routers
        sessions/finalization.py, evaluation/upsert.py, jobs/publish_rules.py, ...
      api/endpoints/      # thin routers: parse → call service → respond
      workers/            # sweep loop + job worker, each guarded by pg_advisory_lock
      cli.py              # `python -m backend.cli <cmd>` replaces root scripts/
    tests/                # unit + integration (disposable Postgres, real migrations)
  agent/
    agent/
      config.py           # replaces 20 os.getenv sites
      providers/          # LLM (existing ABC moved), STT/TTS factory, persistence (existing ABC)
      runtime/            # entrypoint split: bootstrap, session lifecycle, teardown
      interview/controller.py   # FROZEN (H2-C only)
    tests/
  frontend/
    src/lib/api.ts        # ApiError with status; timeout/abort
    src/components/ErrorBoundary.tsx
    src/config.ts         # validated import.meta.env
  tests/legacy/           # moved root scripts (S10), pointed at TEST_DATABASE_URL
  docs/handover/          # architecture, runbooks, env matrix, ADRs
```

Runtime shape is unchanged: one backend, one agent worker (N replicas
allowed once H2's locks land), static frontend, Supabase Postgres/Auth,
LiveKit Cloud. What changes is that every one of those is a config-selected
adapter behind a port, and the process boundaries are safe to replicate.

---

## 3. Phases

Order rationale: H0/H1 are foundations every later phase builds on (you
cannot add retries without a place to configure them, or integration tests
without a disposable DB). Then S4's priority order: H2 reliability, H3
observability, H4 tests/CI (the harness exists from H0; H4 makes it the
gate), H5 security, H6 packaging + handover + baseline measurement.
Sub-phases (`-A`, `-B`, …) are separate approvals.

### H0 — Groundwork: repo hygiene and a one-command dev stack *(no behaviour change)*

**H0-A Test database harness.** `compose.yaml` gains a `postgres-test`
service; a `TEST_DATABASE_URL` setting; a `backend/tests/conftest.py`
fixture that creates a schema per session, runs `alembic upgrade head`,
truncates between tests. Root `conftest.py`'s regex-cleanup fixture is
retargeted at the test DB (content otherwise unchanged).
**H0-B Cleanup (S11).** Present the exact `git rm` list for a final OK,
then remove: `frontend/src/App.css`, `components/layout/AppShell.tsx`,
`Container.tsx`, `routes/admin/AdminResultView.tsx`, unreferenced
`assets/*.svg`; root `temp.tsx`, `replace.py`, `rtl_replace.py`,
`9a_responses.txt`, `frontend/error_jobs.png`; `frontend/test_5c.cjs`;
`New Avatar/`, and the unreferenced `frontend/src/assets/hero.png`.
**H0-C Move legacy tests (S10).** `git mv` root `test_phase*.py`,
`verify_9*.py`, `conftest.py` → `tests/legacy/`; `pytest.ini` gains
`testpaths = backend/tests agent tests/legacy`; imports fixed only where
the move breaks them. They must pass against the test DB before this step
closes.
**H0-D Dev stack + pins.** `compose.yaml` with `postgres`, `migrate`
(one-shot `alembic upgrade head`), `backend`, `agent`, `frontend` (Vite
dev, port 5174); `.env.example` per service listing *every* read setting
and none that isn't read; `.python-version`/`.nvmrc` + `engines`;
`requirements.txt` split into `backend/requirements.txt` and
`agent/requirements.txt` (each only what it imports) — image size and
supply-chain surface. `scripts/dev.ps1` / `Makefile` targets: `up`,
`test`, `lint`, `typecheck`. Stale docs corrected to the real commands
(`README.md`, `DEPLOYMENT.md`, `docs/LOCAL_DEMO_SETUP.md`).

Files: new compose/env/pins/`tests/legacy/`; `pytest.ini`; docs. No
`src` logic changes. **Verify:** fresh clone → `docker compose up` → all
services healthy; `pytest` green (backend + agent + legacy) against the
test DB; frontend typecheck/lint/test green.

### H1 — Configuration and provider ports *(the "no hard-coding, object-oriented" ask)*

**H1-A Backend settings.** `core/config.py` becomes the single typed
`Settings` (pydantic-settings): every value below lifted with a default
and a docstring; `model_validator` refuses to boot when
`ENVIRONMENT != local` and `SECRET_KEY` is the shipped default, or any
required provider key is missing; dead settings (`STT_PROVIDER`,
`LLM_PROVIDER`, `TTS_PROVIDER`, `SUPABASE_PUBLISHABLE_KEY`) either wired or
removed. Values lifted: resumes bucket name, 5 MB CV cap, Groq base URL +
model fallbacks, HTTP timeouts, `AGENT_LEASE_DURATION`, sweep interval,
egress retry/layout/path template, presign TTL, guest-JWT TTL, LiveKit
token TTL (new), `admin_tester@path2hire.local`, JWT algorithms/audience,
version string, CORS origins, pool sizes.
**H1-B Backend provider ports.** `providers/` package as in §2:
`LLMProvider` (Groq adapter wrapping the four inline call sites +
`resume_ingest`), `StorageProvider` (S3-compatible adapter for R2; presign,
put, delete), `RealtimeProvider` (LiveKit token + egress), `EmailProvider`
(`NullEmailProvider` logs and returns "not sent" — S6), existing
`NotificationService` moved under `providers/notifications/` unchanged.
One `providers/factory.py` builds them from `Settings`; FastAPI
dependencies inject them. Routers/services stop importing vendor SDKs.
**H1-C Agent settings + factory.** `agent/agent/config.py` replaces the
20 `os.getenv` sites; `required_vars` becomes the settings validator
(adds `LLM_MODEL`, `AZURE_SPEECH_*` when the provider needs them);
defaults reconciled with `.env`/docs (`TTS_PROVIDER`); the Arabic Groq
voice becomes a setting; provider factory (`main.py` L471–568) moves to
`agent/agent/providers/factory.py`; `prewarm_fnc` loads VAD once;
`WorkerOptions` gets `agent_name`, `job_memory_limit_mb`; `.groq_key_state`
and `.tts_cache` paths become settings pointing at a writable volume, not
the app dir. `controller.py` untouched.
**H1-D Frontend config.** `src/config.ts` validates `VITE_API_BASE_URL`,
`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` at boot (no silent
`localhost:8000` / `""` fallbacks); `frontend/.env.example`; `/dev/*`
routes behind `import.meta.glob`/lazy import so they leave the prod bundle;
head-pose debug logging defaults **off**.

**Verify:** parity run of the live flows; `pytest` green; a deliberately
missing `SECRET_KEY` in `ENVIRONMENT=staging` refuses to boot (test);
`grep` proves no vendor SDK import outside `providers/`.

### H2 — Reliability and error handling *(priority 1)*

**H2-A Backend error model + service layer.** `core/errors.py`
(`AppError` → `NotFound`, `Conflict`, `Forbidden`, `UpstreamTimeout`,
`ValidationFailed`…), one global exception handler producing RFC 7807
`application/problem+json` with `request_id`; the 17 `except Exception`
sites classified (handle / translate / re-raise); typed response models on
every route (`get_transcript`, `get_events`, internal routes). Domain
logic moves out of `admin.py` (1674 LOC) and `internal.py` (847) into
`services/` — finalization state machine, evaluation upsert, aggregation,
egress orchestration, publish rules (single source; today duplicated at
`admin.py:451-473` vs `497-524`). Cross-router private imports and direct
route-function calls removed. Fixes the P0 `PATCH /admin/jobs/{id}/status →
DRAFT` 500 (`admin.py:442`, phantom `backend.models.session`, undefined
`func`). Pagination on list endpoints (additive query params; defaults
preserve today's "all" behaviour so the frontend is unchanged).
**H2-B Backend resilience.** Timeouts + bounded retries (tenacity) on
every provider call; sync I/O (`PyJWKClient`, boto3, PyMuPDF) moved to
`asyncio.to_thread`; engine gets `pool_size`, `max_overflow`,
`pool_pre_ping`, `pool_recycle`; no commits inside auth dependencies;
`resume_ingest` writes the DB row before the upload and the extraction
failure becomes `FAILED`, not `COMPLETED`; `livekit.py:205` egress task
tracked and awaited on shutdown; LiveKit token TTL. Additive migration:
FK indexes on `interview_sessions(job_id)`, `(candidate_profile_id)`,
`(status, disconnected_at)`, `interview_checkpoints(session_id, created_at)`,
`interview_events(session_id)`, `interview_questions(section_id)`,
`users_roles(user_id)` (+ unique only after U3). `/health` = liveness,
`/ready` = DB + providers reachable and returns 503 when degraded;
`engine=None` boot path removed (fail closed). Migrations leave the
container start (they run in the `migrate` one-shot); the disconnect sweep
and finalization become idempotent and run under `pg_try_advisory_lock`
so N replicas are safe.
**H2-C Agent controller sub-phase (S12 — frozen file, own approval).**
Minimal diff to `controller.py`: (1) `IM_READY` `NameError` at L1281 in the
legacy `TECHNICAL_INTRO` path; (2) fallback strings at L515, L547,
L609–611, L1286, L1903–1904 routed through the existing language table;
(3) keyword intents at L1325–1368 (`"i'm done"`, `"let's move on"`,
`"help me"`) no longer perform the state change directly — they emit a
`CONFIRM_INTENT` UI event and the transition happens only on the existing
`END_INTERVIEW` / `END_SECTION_EARLY` / `REQUEST_HINT` control. Wire
contract (`ui_state`, `/internal/*`) unchanged; any needed frontend
confirmation reuses `EndInterviewDialog`/`EndSectionEarlyDialog`.
**H2-D Agent runtime resilience.** `entrypoint` split into
`runtime/bootstrap.py`, `runtime/session.py`, `runtime/teardown.py` with a
`try/finally` that always leaves the session in a terminal or
`DISCONNECTED` state (never stranded `IN_PROGRESS`); LLM calls get a
timeout (setting) and the `_turn_lock` is released on timeout so
`END_INTERVIEW` can't be blocked; `APIPersistence` gets retries with
backoff and a local outbox so sequence counters advance only on success,
completion is retried until acknowledged, and a failed lease renewal
triggers a controlled shutdown (no dual agents); STT stream bound to the
candidate participant only, restarted on error, closed on teardown;
`ui_command` validated (sender, schema, size) and tasks referenced;
`ctx.shutdown()` after `COMPLETED`; TTS plugin rebuild re-attaches the
`metrics_collected` listener; key-state file written atomically.
**H2-E Frontend resilience.** `ApiError { status, code, detail,
requestId }` from `lib/api.ts` (pages stop string-matching "404"/"409");
request timeout + `AbortController`; `ErrorBoundary` at the router root
and around `InterviewWorkspace` (a render throw shows a recoverable
screen, not white); `RoleContext` distinguishes 401/403 from network
failure (admins are not bounced to `/login` on a backend blip);
`CandidateAccess.handleTestDrive` opens `/interviews/:id` and stops
writing the orphan token; `alert()`/`confirm()` replaced with the existing
modal components; realtime type drift fixed (`ActiveQuestion.source`,
`AllowedControl`, `RealtimeMessage`).

**Verify (each sub-phase):** parity run; new tests for every fixed defect
(a test that fails on the old code first); agent fault-injection tests
(kill the backend mid-session → session ends `DISCONNECTED`, resumes);
two backend replicas + one sweep → single execution proven by log.

### H3 — Observability and operations *(priority 2)*

Structured JSON logging (`structlog` or stdlib `JSONFormatter`) in backend
and agent with `request_id`, `session_id`, `job_id` bound in context; the
backend generates `X-Request-ID` and the agent propagates it on every
`/internal/*` call so one interview is one trace across both services;
agent's double logging (basicConfig + SDK handler) removed. Prometheus
metrics (`prometheus_client` is already installed): request latency/
status, provider call latency/errors/retries, job-queue depth/age, active
sessions, sweep outcomes; agent exposes STT/TTS/LLM latencies already
collected via `metrics_collected`. `/metrics` guarded by network policy
(documented). Health/readiness from H2 documented per service. Root
`scripts/*.py` become `python -m backend.cli` sub-commands
(`create-admin`, `seed-demo`, `finalize-stuck`, `backfill-evaluations`)
with the same behaviour. `docs/handover/runbooks/`: start/stop/upgrade,
rotate keys, stuck session, provider outage, restore from backup, read
the logs of one interview.

**Verify:** one full interview produces a single `request_id`-correlated
log trail across backend + agent; `/metrics` scrapes; each runbook is
executed once against the compose stack.

### H4 — Tests and CI/CD *(priority 3)*

Backend: unit tests for services and providers (fakes), integration tests
against the disposable Postgres for every router (auth matrix, publish
rules, finalization idempotency, job queue, sweep lock); Alembic
`upgrade head` + `downgrade -1` + `upgrade head` smoke in CI; a check that
the SQLAlchemy metadata and the migration head agree. Agent: tests with
fakes for `APIPersistence` (retry/outbox), `LLMProvider` timeout,
resume-restore, TTS retry/cache/rotator, STT loop restart,
completion/teardown; existing `agent/test_*.py` untouched. Frontend:
`tsconfig` `strict: true` reached incrementally (per-folder, `any` count
tracked to zero), oxlint rule set widened, `vitest` + jsdom component tests
for `ErrorBoundary`, `RoleContext`, `api.ts`, `ResponsiveTable`; `npm run
build` runs typecheck + lint first. GitHub Actions `ci.yml`: lint →
typecheck → unit → integration (services: postgres) → legacy suite →
container builds for backend/agent/web; `pre-commit` with ruff, oxlint,
end-of-file/secret scan. Coverage reported, no arbitrary threshold gate.

**Verify:** CI green on a PR that deliberately breaks a rule (proves the
gate), green on `main`; `docs/technical/testing-strategy.md` rewritten to
describe what actually runs.

### H5 — Security and compliance *(priority 4)*

`core/security.py`: Supabase-JWT and guest-JWT verification are selected
by issuer/`kid`, never by "Supabase failed, try guest"; algorithms pinned;
audience checked. `api/deps.py` auto-link-by-email replaced with an
explicit, logged link that requires a verified email; `profiles.py` email
change requires re-verification (or is disabled — the current UI never
changes it; confirm). Rate limiting without Redis: a DB/in-memory token
bucket per IP and per token on `public_apply`, `/redeem`, `/livekit/token`,
login-adjacent routes (`slowapi` in-process is sufficient for one replica;
the DB variant is the swap for N). `POST /livekit/token` no longer spawns an
egress per call (idempotent per session). `ui_command` sender check (H2-D)
plus a schema allow-list. Dockerfiles run as non-root, have `HEALTHCHECK`,
copy only the package (no tests/caches/`.env`); `pip-audit` + `npm audit`
in CI; `frontend/public/mediapipe/` (38 MB, unreferenced tflite) trimmed
to what is loaded. Data lifecycle: a `purge` job (H2's `JobQueue`) that can
delete recordings/CVs/transcripts by age and status — **shipped disabled
pending U1**. Audit trail: `InterviewEvent` already exists; admin
mutations (publish, delete, override) additionally write an
`admin_audit_log` row (additive table). CORS explicit per environment.
Secrets: documented sources (env/secret files), never defaults;
`.env.example` files contain no real values. `docs/handover/security.md`:
threat model, data map (what personal data lives where), PDPL/GDPR
posture and the open U1.

**Verify:** auth tests for every rejection path (expired, wrong audience,
guest-on-admin, admin-on-candidate); rate-limit tests; container image
scan output; a manual pass with the OWASP API top-10 checklist recorded.

### H6 — Packaging, handover and baseline

`compose.prod.yaml` (migrate → backend → agent; `web` = nginx serving the
built frontend with SPA fallback and security headers) runnable on any
Docker host; a `docs/handover/kubernetes.md` mapping each compose service
to a Deployment/Job/Service/Ingress (no Helm chart until hosting is
decided); env matrix (every setting × local/staging/prod, required or
default); architecture doc with the §2 diagram, data model regenerated
(`BASELINE_SCHEMA.md` is 20 migrations behind), sequence diagrams for
apply → interview → finalize; ADR directory seeded with S1–S12 and the
decisions already in `CURRENT_DECISIONS.md` (that file remains the product
decision log). Load baseline: a script that drives N simulated candidates
through `/apply` → `/livekit/token` and N agent sessions with the existing
`simulator.py` against a staging LiveKit room; the sustained N per worker
and the p95 latencies are recorded in `docs/handover/capacity.md` (U4).
`render.yaml` either updated to the new images or removed (your call at
this step). `docs/PROJECT_STATUS.md` updated; `DEPLOYMENT.md` replaced by
`docs/handover/deploy.md`.

**Verify:** a stranger's test — a clean machine, the handover docs only,
stack up and one interview completed; the numbers in `capacity.md` come
from the script's output, pasted.

---

## 4. Per-phase template (what each phase's own plan must contain)

```
## Hn-X — <name>
Explore: quoted current contents of every file to be touched (re-read live).
Plan:    files touched; new modules/tables (additive); settings added;
         Frozen Contracts Confirmation (controller.py, /internal/*,
         InterviewerCharacter.tsx — untouched, or H2-C approval cited);
         decisions from §0 this phase relies on (by ID); unresolved U-items it must not decide.
Execute: after approval only. One commit per logical step (subject to U2).
Verify:  parity run of live flows; pytest (backend, agent, legacy) pasted;
         npm typecheck/lint/test pasted; container build pasted;
         fault-injection evidence where the phase claims resilience.
Left over: anything discovered and NOT fixed, appended to §6.
```

---

## 5. Dependencies and sequencing

```
H0-A ─┬─ H0-C (legacy tests need the test DB)
      └─ H1-A ─ H1-B ─ H2-A ─ H2-B ─ H3 ─ H4 ─ H5 ─ H6
H0-B (cleanup) any time after the final listing is OK'd
H0-D (dev stack) after H0-A; before H1 so every phase runs on the stack
H1-C, H1-D (agent/frontend config) in parallel with H1-B
H2-C (controller) after H1-C; own approval gate
H2-D after H1-C and H2-C (the confirm-intent event is consumed by the runtime)
H2-E after H1-D; coordinate with the responsive track (U2)
```

Estimated size (not time): H0 small; H1 medium; H2 large (five sub-phases,
the bulk of the initiative); H3 medium; H4 medium-large; H5 medium; H6
medium. The responsive track's remaining phases (R2-C, R3–R7) can
interleave; the only shared files are in H2-E.

---

## 6. Parking lot (found, deliberately not in this plan)

- Frontend i18n gaps in the live workspace chrome and results pages —
  responsive track / a dedicated i18n pass.
- `document.documentElement.dir` set only by `LanguageToggle` — responsive R7.
- Transition Phase 8 (Evaluation/Score tables) and Phase 10 (retire
  `InterviewConfiguration`) — the transition plan owns these.
- Head-pose thresholds on handheld devices — responsive D5.
- `QuestionEditor`/`SectionsEditor` use `window.confirm` — H2-E replaces
  with the modal only where it already exists; UX redesign is not in scope.
- The VAD/endpoint-delay coalescing race noted in
  `docs/realtime-voice-hardening.md` — voice-quality work, not hardening.

---

## 7. Audit findings (2026-09-17) — the evidence this plan is built on

### Backend (`backend/backend/`, ~5.8k LOC, FastAPI, async SQLAlchemy + asyncpg, 21 Alembic revisions)

Structure: routers own the domain — `api/endpoints/admin.py` (1674 LOC) and
`internal.py` (847) hold aggregation, finalization state machine, evaluation
upsert, R2 presign/delete, egress orchestration; routers import each other's
private helpers (`admin.py:1296`, `interviews.py:23`) and call route
functions directly (`admin.py:673`, `:1391`); 11 in-function imports work
around cycles; publish rules duplicated (`admin.py:451-473` vs `497-524`).

P0: `admin.py:442-443` imports non-existent `backend.models.session` and
uses undefined `func` → `PATCH /admin/jobs/{id}/status` to DRAFT always
500s. `core/security.py:34-44` `except Exception` turns every Supabase-JWT
failure into a guest-HS256 attempt; `config.py:7` ships a default
`SECRET_KEY` and nothing refuses to boot with it. `api/deps.py:37-46`
auto-links any existing profile to a JWT by email; `profiles.py:58-81` lets
a user change that email → cross-account link. No rate limiting;
`public_apply.py:69-139` mints unlimited guest JWTs/sessions; each
`POST /livekit/token` spawns an egress task. `main.py:61-78` `/health`
returns 200 while "degraded"; `db/session.py:36-42` boots with
`engine=None`. `backend/Dockerfile` runs `alembic upgrade head` on every
start (replica race); `internal.py:193-231` sweep loop assumes one process.

P1: no pool sizing/`pool_pre_ping`/`pool_recycle`; commits inside the auth
dependency (`deps.py:45,59,71`). Missing FK indexes (see H2-B).
Groq calls inline in requests, no timeout/retry/queue: `admin.py:591,892,
963,1277`, `resume_ingest.py:52`; two different silent default models.
Sync I/O on the event loop: `PyJWKClient` (`security.py:26`), boto3
(`admin.py:196,242`), PyMuPDF (`resume_service.py:98`).
`resume_ingest.py:33-70` uploads before any DB row, 3 commits;
`resume_service.py:193` swallows LLM extraction failure → `COMPLETED`.
`livekit.py:205` fire-and-forget task; `:190-196` LiveKit token has no TTL.

P2: 17 `except Exception`; no global exception handler, request-id,
structured logs or metrics (`prometheus_client` installed, unused);
deprecated `on_event`; no pagination; untyped responses; dead settings;
`.env.example` missing 9 settings; `requirements.txt` is a merged
backend+agent freeze; `docker-compose.yml` = Postgres only;
`DEPLOYMENT.md` contradicts `render.yaml`; tests hit the live
`DATABASE_URL` with a regex cleanup fixture; `docs/technical/*`
aspirational. Existing abstraction to generalise:
`services/notifications/{base,console}.py`.

### Agent worker (`agent/agent/`, ~11k LOC incl. tests; livekit-agents 1.7.1)

Structure: `main.py` `entrypoint()` is ~440 lines (env validation, `/load`,
checkpoint restore, provider factory L471-568, teardown L600-642);
`controller.py` 2639 LOC (FROZEN), `voice_adapter.py` 1153,
`persistence.py` (`InterviewPersistence` ABC + `APIPersistence`, aiohttp),
`llm/provider.py` ABC + `GroqProvider`. No config module: 20 `os.getenv`
sites.

P0: no try/finally around `entrypoint` → sessions stranded `IN_PROGRESS`
(backend sweep only finalizes `DISCONNECTED`); no timeout on LLM calls
while `_turn_lock` is held → a hung Groq call blocks `END_INTERVIEW`;
`APIPersistence` 10 s timeout, zero retries, failures swallowed, sequence
counters advance on failure, lease renewal failures ignored (dual-agent
risk); STT pipeline (`voice_adapter.py:476-521`) no error handling, any
participant treated as the candidate, streams leak; keyword intents in the
frozen controller (`controller.py:1325-1368`) cause hard state changes.

P1: `ui_command` unvalidated (`voice_adapter.py:291-305`);
`controller.py:1281` `NameError` on `IM_READY`; config defaults contradict
`.env`; Arabic voice hard-coded (`main.py:521`); `WorkerOptions` untuned
(no `prewarm_fnc`, `agent_name`, memory limit, no `ctx.shutdown()`); disk
state in the app dir baked into the image; logs emitted twice; English
fallback strings reach Arabic candidates; TTS rebuild drops the metrics
listener.

P2: frontend realtime type drift; zero tests for persistence/provider/
restore/retry/cache/rotator/STT/teardown; Dockerfile root, no HEALTHCHECK;
no `agent/.env.example`.

### Frontend + repo/infra

Frontend: single fetch wrapper (`lib/api.ts`) but errors lose HTTP status
(pages string-match "404"/"409"); no timeout/abort; `tsconfig.app.json`
not strict, ~70 `any`s, oxlint 2 rules, `npm run build` skips
typecheck/lint; no `ErrorBoundary`; `RoleContext.tsx:33-41` maps any ping
failure to "candidate"; `CandidateAccess.tsx:101-102` opens
`/interview/:id` (route is `/interviews/:id`); head-pose debug log on by
default; silent env fallbacks; `/dev/*` routes in the prod bundle;
`alert()`/`confirm()` in 4 places; 1 test file. Dead files and stray
artefacts as listed in H0-B; `frontend/public/mediapipe/` 38 MB in git.

Repo/infra: no CI, pre-commit or task runner; `docker-compose.yml` =
Postgres only; a fresh clone cannot run with one command; root
`.env.example` missing 14 keys incl. required `SECRET_KEY`/
`AGENT_API_SECRET`; Python 3.13 in Dockerfiles vs "3.11+" README, Node
unpinned; `README.md`/`DEPLOYMENT.md`/`docs/LOCAL_DEMO_SETUP.md` stale;
`BASELINE_SCHEMA.md` 20 migrations behind; no ADR dir. `.gitignore`
excludes `CLAUDE.md`/`AGENTS.md`/skills **deliberately** (public repo) —
not a defect; handover docs go to tracked `docs/handover/` instead. No
real secrets in tracked files.

---

## 8. H0 — verify record (2026-09-21)

**H0-A.** `requirements-dev.txt` (pytest, pytest-asyncio, httpx, pip-tools) —
`pytest-asyncio` was in neither `.venv` nor any requirements file, so nine
backend/legacy modules could not even be collected before this step.
`docker-compose.yml` gained `postgres-test` (postgres:15, port 5433, tmpfs).
New root `conftest.py`: sets `DATABASE_URL = TEST_DATABASE_URL` before any
`backend` import, aborts if the host contains "supabase", and — once per
session, only when backend/legacy tests are collected — drops/recreates
`public` and runs `alembic upgrade head` as a subprocess from `backend/`.
`pytest.ini` gained `testpaths = backend/tests agent tests/legacy`. The old
root `conftest.py` moved unchanged to `tests/legacy/conftest.py`.

Finding fixed on the way: **the Alembic chain could not build a database
from scratch.** Revision `cfaa8eeb37cf` (4th of 21) did
`op.drop_table('code_submissions')` for a table no revision ever creates —
it pre-dated the initial revision on the original database. Changed to
`DROP TABLE IF EXISTS`; identical where the table existed, a no-op on a
fresh DB. The live DB is past this revision, so it is unaffected.

Checked: `TEST_DATABASE_URL=…supabase.com…` → run refused with the message;
fresh container → `alembic_version = b7e2c4d9a1f3`, 19 tables;
`pytest backend/tests` 19 passed; `pytest agent` 127 passed with no DB
setup (skip path).

**H0-B.** Removed (all confirmed unreferenced by import/grep): `frontend/src/
App.css`, `components/layout/AppShell.tsx`, `components/layout/Container.tsx`,
`routes/admin/AdminResultView.tsx`, `assets/{hero.png,react.svg,vite.svg}`,
root `temp.tsx`, `replace.py`, `rtl_replace.py`, `9a_responses.txt`,
`frontend/error_jobs.png`, `frontend/test_5c.cjs`, `New Avatar/` (26 files).
Correction to §3: no `__pycache__` was tracked. Checked: `tsc -b` clean,
oxlint 17 warnings all pre-existing in untouched files, vitest 3/3,
`vite build` OK.

**H0-C.** `git mv` of 17 `test_phase*.py` + `verify_9a.py` + `verify_9b.py` →
`tests/legacy/` (no `__init__.py` — a root `tests` package shadowed
`backend/tests`). No content edits. Checked: `pytest tests/legacy` 68 passed,
1 skipped against the from-scratch DB. Full run: **214 passed, 1 skipped**.

**H0-D.** `docker-compose.yml` `app` profile: `migrate` (one-shot
`alembic upgrade head`) → `backend` (uvicorn 8001, healthcheck) → `agent`
(`BACKEND_INTERNAL_URL=http://backend:8001`) → `frontend` (node:22, Vite
5174, node_modules volume, install only when empty, `PUPPETEER_SKIP_DOWNLOAD`).
Dockerfiles unchanged; `.dockerignore` (already excluded `.env`) extended
with `tests/`, key-state and TTS cache. `backend/requirements.in` and
`agent/requirements.in` written from the real import lists and compiled
with pip-tools constrained to the versions already in use: agent set
identical; backend drops 47 packages it never imports (livekit-agents,
numpy, supabase client, opentelemetry, typer…) and gains six that the old
freeze was missing (boto3's `s3transfer`/`jmespath`/`six`/
`python-dateutil`, `dnspython`, `httptools`). Pins: `.python-version` 3.13,
`frontend/.nvmrc` 22, `engines` in `package.json`. `backend/`, `agent/`,
`frontend/.env.example` list exactly what each service reads today (root
`.env.example` = the local-dev union). `Makefile` + `scripts/dev.ps1`
(`install lock up down test test-* lint typecheck migrate`). `README.md`
rewritten to the real commands; `docs/LOCAL_DEMO_SETUP.md` corrected in
place (path, 8001/5174, `.venv`); `DEPLOYMENT.md` banner "superseded → H6".

Checked: three images build from the split lockfiles; `docker compose
--profile app up` → migrate exit 0, backend `/health` 200 `database:
connected`, agent `registered worker` (AW_…, region UAE), frontend 200 with
the e& title. Stack stopped afterwards (a containerised agent competes with
the local worker for LiveKit jobs). **Side effect to record:** `migrate`
ran against the live `DATABASE_URL` in `.env` and applied
`c3f9a72e4d18 → b7e2c4d9a1f3` (inserts the TEMPLATE `cv_alignment` row into
`assessment_criteria`); the live DB had been one revision behind the
committed code (`16f9f2a`). Additive; nothing else changed.

Left over → §6: none new. `frontend/public/mediapipe/` (38 MB) stays for H5.

## 9. H1-A — verify record (2026-09-21)

`core/config.py` rewritten as one grouped, documented `Settings` (still the
mutable `settings` singleton — `tests/legacy/test_phase1.py`/`3a.py` assign
to it). `ENVIRONMENT` is now `Literal[local|test|staging|production]`; an
`after` validator refuses to boot outside local/test when `SECRET_KEY` is
the shipped default or < 32 chars, or `AGENT_API_SECRET`/`LIVEKIT_*` are
empty. Dead fields: `SUPABASE_PUBLISHABLE_KEY` required→optional (never
read), `STT_PROVIDER`/`TTS_PROVIDER` removed (agent concerns; `extra=ignore`
keeps shared .env files valid), `LLM_PROVIDER` kept as `Literal["groq"]`
for H1-B's factory. `BACKEND_CORS_ORIGINS` default gains 5174.

17 literals lifted, defaults = previous behaviour: `RESUMES_BUCKET`,
`MAX_RESUME_BYTES`, `SUPABASE_STORAGE_TIMEOUT_SECONDS`, `GROQ_API_BASE_URL`,
`GROQ_MODEL` (default replaces the three `or "llama-3.3-70b-versatile"`
fallbacks; an empty value still means default), `GROQ_EXTRACTION_MODEL`,
`GROQ_TIMEOUT_SECONDS` + `GROQ_MAX_RETRIES` (now passed to the Groq SDK
client — before, the SDK's own 60 s/2 applied to three call sites and 30 s
to the fourth; the SDK sites therefore now time out at 30 s instead of 60 s
— the one deliberate, documented change), `RECORDING_URL_TTL_SECONDS`,
`ADMIN_TEST_CANDIDATE_EMAIL/NAME`, `AGENT_LEASE_MINUTES`,
`DISCONNECT_SWEEP_INTERVAL_SECONDS`, `EGRESS_START_RETRY_ATTEMPTS/
DELAY_SECONDS`, `EGRESS_LAYOUT`, `RECORDING_PATH_TEMPLATE`,
`LIVEKIT_TOKEN_TTL_MINUTES` (360 = the SDK's `DEFAULT_TTL`, verified in
`livekit.api.access_token`), `GUEST_JWT_TTL_HOURS`, `GUEST_JWT_ALGORITHM`,
`SUPABASE_JWT_ALGORITHMS`, `SUPABASE_JWT_AUDIENCE`, `APP_VERSION`. Left as
constants (R2 protocol, not policy): `region_name="auto"`, `s3v4`,
path-style addressing.

Files: `core/config.py`, `core/security.py`, `services/{resume_service,
question_generator,evaluation_generator,invitation_message_generator,
guest_jwt_service}.py`, `api/endpoints/{admin,internal,livekit}.py`,
`main.py`; `backend/.env.example`, root `.env.example`; new
`backend/tests/test_settings.py` (11 tests). No migration, no frozen file,
no `agent/` change; `/internal/*` payloads and routes unchanged.

Checked: full `pytest` **225 passed, 1 skipped**; backend imports with the
real `.env` (`ENVIRONMENT=local`, `GROQ_MODEL=openai/gpt-oss-120b` kept);
grep finds no lifted literal outside `config.py`; backend container with
`ENVIRONMENT=production` + shipped `SECRET_KEY` exits 1 with "Refusing to
start … SECRET_KEY is the shipped default; AGENT_API_SECRET is empty";
with a complete production config it boots.

## 10. H1-B — verify record (2026-09-21)

New `backend/backend/providers/`: `llm/` (`LLMProvider.complete_json`,
`GroqLLMProvider` on `AsyncGroq` — async end-to-end, replacing three
sync-SDK-in-`to_thread` sites and one hand-rolled httpx call), `storage/`
(`ObjectStorage` + `S3Destination`; `S3CompatibleStorage` for R2,
`SupabaseStorage` for CVs), `realtime/` (`RealtimeProvider`;
`LiveKitProvider` owns token minting, the egress `not_found` retry loop,
stop, delete-room), `email/` (`EmailProvider`; `NullEmailProvider` logs and
returns `sent=False` — S6), `notifications/` (existing `NotificationService`
+ `ConsoleNotificationService` `git mv`'d unchanged; new
`EmailNotificationService(EmailProvider)`), `factory.py` (one `lru_cache`'d
`get_<port>()` per port, `reset_providers()` for tests). `Settings` gained
`REALTIME_PROVIDER`, `RECORDINGS_STORAGE_PROVIDER`, `RESUMES_STORAGE_PROVIDER`,
`NOTIFICATIONS_PROVIDER` (console default = today's behaviour),
`EMAIL_PROVIDER` (null).

Call sites rewired, behaviour-identical: the three generators and
`ResumeService.build_candidate_profile` take `llm: LLMProvider | None`
(default `get_llm()`; the "no GROQ_API_KEY → RuntimeError / empty profile"
outcomes preserved); `ResumeService.upload/delete_object` take
`storage: ObjectStorage | None` with the same 502/500/False mappings;
`admin.py` presign/delete use `get_recordings_storage()` (`configured`
replaces the five-field `all([...])` check; `_delete_recording_object` is
now `async`, its one caller awaits it); `livekit.py` egress start and token
minting, `internal.py` room delete and egress stop use `get_realtime()`;
`invitations.py` uses `get_notification_service()`. Vendor imports outside
`providers/`: only `core/security.py`'s unused `import httpx` (H5 file).

Tests: `backend/tests/fakes.py` (`FakeLLMProvider`, `FakeEmailProvider`,
`MemoryStorage`); `backend/tests/test_providers.py` (12: factory selection
+ caching, LLM key requirement, email routing, selector validation, null
email result, invitation rendering, S3 presign URL + egress destination,
Supabase no-presign, LiveKit token claims via PyJWT, generators/resume
through injected fakes). **With the owner's OK (2026-09-21), the two tests
welded to the old wiring were edited** — `test_background_evaluation.py`
(one test, two blocks) and `test_resume_profile_extraction.py` (two tests)
now inject `FakeLLMProvider` instead of patching `evaluation_generator.Groq`
/ `resume_service.httpx.AsyncClient`; every assertion kept except
`response_format == json_object`, which is now the port's contract rather
than a per-call argument.

Checked: full `pytest` **237 passed, 1 skipped**; backend container builds
and boots, `/health` connected; token minting exercised by
`test_room_token_is_gated_on_the_cv` through the real `LiveKitProvider`.
**Owed:** a live interview start on the owner's side to confirm egress
start/stop and room delete against LiveKit Cloud through the adapter
(`recording_egress_id` set on the session; recording stops at end).

Tooling note: the Bash tool's transport drops one backslash from `\
`
sequences inside heredocs — Python edit scripts containing escaped
backslashes must be written with the Write tool, not heredoc'd.

## 11. H1-C — verify record (2026-09-21)

New `agent/agent/config.py`: `AgentSettings` (pydantic-settings, added to
`agent/requirements.in`; the only lockfile change) declaring every variable
the worker reads, defaults = the inline literals, the inline parsing
semantics preserved by validators (unparseable → default, then floor:
VAD .85/.55, STT endpoint .8/.25, waiting room 300/1), `TTS_PROVIDER`
lower-cased and validated, `groq_tts_keys` (the `_1.._20` scan with the
legacy fallback), `missing_for_job()` (the six historical required vars
**plus `LLM_MODEL`, plus `AZURE_SPEECH_KEY/REGION` when azure**), new knobs
`GROQ_TTS_ARABIC_VOICE` (was hard-coded "abdullah"), `LEASE_RENEWAL_INTERVAL_
SECONDS`, `AGENT_NAME`, `JOB_MEMORY_LIMIT_MB/WARN_MB`, `AGENT_STATE_DIR`,
`TTS_CACHE_DIR`. `get_settings()` is cached and **side-effect free**: dotenv
loading stays in `main._load_env()` (→ `config.load_env_files`, same
override=True precedence) at entrypoint start and `__main__` only — a
first draft loaded .env inside `get_settings()` and would have clobbered
the pytest process's test `DATABASE_URL` the moment a test built a
`VoiceInterviewAdapter`; caught before running the suite. `entrypoint`
resets the cache after the per-job reload so a rotated key is still picked
up per job.

New `agent/agent/providers/factory.py`: `build_llm/stt/tts/vad`, `prewarm`
(VAD into `proc.userdata`), `vad_for`. The 100-line inline block in
`entrypoint` (L471–568) is now four calls; the per-language/per-provider
rationale comments moved with the code. `WorkerOptions` built by
`worker_options()` with `prewarm_fnc`, `agent_name`, optional memory
limits. Backward-compatible constructors: `GroqProvider(api_key=None,
model=None)`, `GroqKeyRotator(..., keys=None, state_dir=None)`,
`tts_cache.configure(dir)`. `voice_adapter.py` reads its two values from
settings. `groq.STT` now receives `api_key` explicitly (the new test
exposed that the plugin otherwise reads the env itself). `main.py` has no
`os.getenv` left; the only env reads outside `config.py` are the documented
fallbacks in `groq_provider.py`/`groq_key_rotator.py` and the frozen
`controller.py:56`. Compose: agent gets `AGENT_STATE_DIR=/var/lib/himma-agent`
on a named volume. `.dockerignore` gains `**/tests/`.

Behaviour deltas (both safer, both deliberate): a missing `LLM_MODEL` or
Azure credential now aborts before the session is touched (previously after
`PATCH IN_PROGRESS` → stranded session); the Silero VAD loads once per job
process instead of once per interview (in `dev` mode the SDK keeps 0 idle
processes, so prewarm runs at the first job; `start` mode prewarms up to 4).

Tests: `agent/agent/tests/` (package `agent.tests` — a top-level
`agent/tests` would collide with `backend/tests`), `test_config.py` (9) +
`test_factory.py` (7). Full `pytest` **253 passed, 1 skipped**; agent
container rebuilt with the new lock, `registered worker` (UAE) against
LiveKit Cloud; stack stopped afterwards. **Owed (shared with H1-B):** one
live interview to hear STT/TTS through the factory and confirm egress.

## 12. H1-D — verify record (2026-09-21)

New `frontend/src/config.ts`: pure `loadConfig(env)` + `config`/
`configProblems`. `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`,
`VITE_SUPABASE_PUBLISHABLE_KEY` are required with **no fallbacks** (the
`localhost:8000` fallback in `lib/api.ts` and the `|| ""` in
`lib/supabase.ts` are gone; `createClient("")` used to throw at module load
= blank page); the API base must be absolute and loses a trailing slash;
the three proctoring tunables keep `Number(x) || default`;
`headPoseDebug` = on in dev builds, off in production, `VITE_HEAD_POSE_DEBUG`
overrides (owner's pick (b); recorded in `docs/CURRENT_DECISIONS.md`).
`loadConfig` never throws. `main.tsx` renders the new
`components/ConfigErrorScreen.tsx` (operator-facing, no i18n/auth/API
dependency) instead of `<App/>` when there are problems; `lib/supabase.ts`
exports a failing proxy in that case so nothing else explodes at import.
`vite-env.d.ts` types the seven `VITE_*` keys. `useFaceDetectionMonitor.ts`
reads its four values from `config`. After this, `import.meta.env.VITE_*`
appears only in `config.ts`.

Audit correction: the `/dev/*` preview routes were **never** in the
production bundle — the `import.meta.env.DEV` route gates let Rollup drop
the static imports (0 occurrences of any preview route in
`dist/assets/index-*.js`). The planned lazy-import item was dropped, so
H1-D touches no file shared with the staged responsive work (`App.tsx`
untouched).

Tests: `src/config.test.ts` (6). Checked: `tsc -b` clean; oxlint clean on
touched files; vitest **9/9**; `vite build` OK, bundle still has no dev
previews and no `localhost:8000`; dev server with `VITE_API_BASE_URL`
blanked via a temporary `.env.local` renders "Configuration error —
VITE_API_BASE_URL is not set" (card centred, verified by DOM rects; the
override was removed afterwards), restored env renders the login page with
no console errors.

## 13. H2-A1 — verify record (2026-09-21)

New `core/errors.py` (`AppError` + `BadRequest/Unauthorized/Forbidden/
NotFound/Conflict/PayloadTooLarge/ValidationFailed/UpstreamError/
ServiceUnavailable/UpstreamTimeout`, `problem()`, `install_exception_handlers`)
and `core/request_id.py` (pure-ASGI middleware: inbound `X-Request-ID`
honoured when safe, else UUID4; echoed on every response; outermost
middleware). Every failure — typed error, legacy `HTTPException` (95 raises,
untouched), `RequestValidationError`, unhandled exception — returns
`{type,title,status,detail,instance,request_id[,code]}`. **`detail` is
byte-identical to what was raised** (str/list/dict) and the media type stays
`application/json` (the agent's aiohttp `resp.json()` rejects
problem+json). Unhandled exceptions: full traceback logged with the
request id, body says "quote the request_id", nothing leaked; the 500
handler sets the header itself because it runs in Starlette's outermost
`ServerErrorMiddleware`, above ours (found by the test).

Broad excepts: all 17 now carry `# noqa: BLE001 -- <reason>`: 8 best-effort
by contract (recordings presign/delete, room delete, egress start/stop,
sweep loop, CV extraction non-fatal, resume ingest FAILED), 2 translated to
typed `UpstreamError(code="llm_generation_failed")` (still 502), **3
narrowed to `IntegrityError`** (message/event/consent idempotency paths —
any other DB failure now propagates instead of being swallowed into "return
existing"), 1 typed (pymupdf), 3 explicitly deferred (`security.py` JWT
fallback → H5; `db/session.py` engine=None and `/health` → H2-B).

Fixed: `PATCH /admin/jobs/{id}/status → DRAFT` 500 (phantom
`backend.models.session` import + unimported `func`). Typed:
`GET /interviews/{id}/transcript` (`TranscriptEntryResponse`),
`/events` (`SessionEventResponse`), `/admin/ping` (`AdminPingResponse`) —
same JSON shapes.

Tests: `backend/tests/test_errors.py` (8; a probe router exercises each
path; the DRAFT test fails on the old code with 500 and passes now —
checked by temporarily restoring the old lines). Full `pytest` **261
passed, 1 skipped**. Container smoke over real HTTP: 404 / 401 / 422 all
return the problem body with `content-type: application/json` and
`x-request-id`; an inbound `X-Request-ID: smoke-42` is echoed in header and
body. `internal.py` touched only at the two narrowed excepts (routes and
payloads unchanged).

## 14. H2-A2 — verify record (2026-09-21)

Extracted verbatim (docstrings and the dated rationale comments moved with
the code): `services/sessions/finalization.py` (`ensure_evaluation_placeholder`,
`delete_livekit_room`, `stop_recording_egress`, `finalize_live_session`,
`disconnect_auto_finalize_sweep_loop`), `services/evaluations/upsert.py`
(`resolve_criteria_for_job`, `upsert_evaluation`), `services/sessions/
room_token.py` (`assert_cv_gate_satisfied`, `issue_candidate_room_token`,
`start_recording_egress`), `services/results/candidate_result.py`
(`presign_recording_url`, `INTEGRITY_EVENT_TYPES`, `get_integrity_events`,
`get_live_transcript`, `get_live_question_records_and_submission`,
`build_candidate_result`), `services/publish_rules.py`
(`assert_sections_publishable` / `assert_definition_publishable` — the two
verbatim copies in `publish_job` and `update_job_status` are now one;
messages unchanged). `internal.py` re-imports the moved helpers under their
old private names so its routes are textually unchanged (frozen file,
sub-phase OK given 2026-09-21); `interviews.py` and `main.py` import from
the services; `admin.py`'s test-drive uses `issue_candidate_room_token`
instead of calling the `/livekit/token` route function with a synthetic
request; `regenerate_evaluation` returns `build_candidate_result(...)`
instead of calling the result route. No router imports another router;
no in-function service imports remain (both enforced by a new AST test).
`admin.py` 1647 → 1317 lines, `internal.py` 841 → 554, `livekit.py` 178 →
53. `load_session_for_agent` deliberately stays in `internal.py`.

Two things the extraction surfaced:
1. **Real H1-B regression, now fixed.** `GroqLLMProvider` passed
   `GROQ_API_BASE_URL=https://api.groq.com/openai/v1` to the SDK, which
   appends `/openai/v1` itself → every real backend Groq call since H1-B
   404'd (`.../openai/v1/openai/v1/chat/completions`). The H1-B unit tests
   use fakes, so it only showed when the legacy generation tests hit the
   network (see 2). Setting default is now the origin
   (`https://api.groq.com`); the provider normalises a `/openai/v1`
   suffix; tests for both; a live completion through the provider
   returned `{"ok":true}`.
2. **Patch-target late binding.** `tests/legacy/test_phase4.py`/`9b.py` patch
   `backend.services.question_generator.generate_questions`; the old
   in-function imports resolved that name at call time, a top-level `from
   … import generate_questions` would not. `admin.py` now calls the three
   generators through their modules (`question_generator.generate_questions(…)`),
   preserving the late binding — no legacy test edited.
3. `backend/tests/test_session_cv_gate.py:68` patch target updated to the
   moved `backend.services.sessions.room_token.start_recording_egress`
   (same category as the H1-B test edits; one line).

Tests: `backend/tests/test_services_extraction.py` (5: publish-rule
messages, router-coupling AST check, finalization idempotency + placeholder
never overwrites a real evaluation on the test DB, room-token mint +
single egress schedule, unconfigured-LiveKit refusal); `test_providers.py`
+4 base-url cases; `test_settings.py` default updated. Full `pytest` **270
passed, 1 skipped**; pyflakes clean on every touched file; backend
container rebuilt, `/health` connected, `/admin/ping` 401, no errors in
the log.

## 15. H2-B — verify record (2026-09-22)

Scope decisions (owner, 2026-09-22): the DB-backed job queue (S9) moves to
its own sub-phase **H2-F** after H2-E (it changes four admin endpoints to
job-id + polling and touches admin pages carrying staged responsive edits);
H2-B has **no API contract change**. U3: read-only check on the live
`users_roles` (260 rows, 0 duplicate `user_id`) → unique index safe. U5
recorded (above). `/health` became liveness-only, `/ready` added.

Changed: `db/session.py` — `pool_size/max_overflow/pool_recycle/
pool_timeout` from settings, `pool_pre_ping`, **fail closed** (the
`engine=None` boot path is gone). Sync I/O off the loop: JWKS lookup
(`security.py`, `to_thread`), PDF parse (`ResumeService.extract_text_async`),
boto3 put/delete (S3 adapter). Provider resilience: LiveKit API
`aiohttp.ClientTimeout` (`LIVEKIT_API_TIMEOUT_SECONDS`), Supabase Storage
bounded retry on transport errors only (`STORAGE_RETRY_ATTEMPTS`), boto3
connect/read timeouts + standard-mode retries (`S3_*`). Migration
**`c4d1e8f2a9b7`** (additive): 12 FK/filter indexes + `uq_users_roles_user_id`.
`main.py`: `lifespan` replaces `on_event`; `/health` (no DB) and `/ready`
(200/503); shutdown drains tracked background tasks then disposes the
engine. New `core/background.py` (`spawn/pending/drain`); egress start is
spawned through it. `finalization.py`: sweep iteration under
`pg_try_advisory_xact_lock(SWEEP_LOCK_KEY)`; `finalize_live_session`
re-selects the row `FOR UPDATE` and re-checks the terminal status;
`ensure_evaluation_placeholder` inserts inside a savepoint and treats the
unique-violation as "already written". `resume_ingest`: row first
(deterministic key via `ResumeService.storage_path_for`), upload second,
`FAILED` on upload failure — a first draft read `profile.id` after the
commit (expired instance, `MissingGreenlet`); caught by the cv-gate test.
Pagination: `limit`/`offset` on `GET /admin/jobs` and the invitations
list, defaults = unbounded. Dockerfile: `docker-entrypoint.sh`, migrations
only with `RUN_MIGRATIONS_ON_START=true` (`$PORT` still honoured); compose
healthcheck → `/ready`. `backend/.env.example` documents the 10 new keys.
`deps.py` auto-link commits deliberately left for H5.

Tests: `backend/tests/test_resilience.py` (8): liveness vs readiness incl.
503 with a broken engine; sweep skips while a second real connection holds
the advisory lock and runs once it is released; **two concurrent finalizers
→ exactly one finalizes, one placeholder, one egress stop**; background
registry; storage retry then give-up; ingest row-before-upload + FAILED on
upload error; pagination defaults + `limit=0` → 422. Full `pytest` **278
passed, 1 skipped**; the migration applies on the from-scratch test DB
(head `c4d1e8f2a9b7`, 13 new indexes). Container: rebuilt backend boots
through the entrypoint without running alembic, `/health` ok, `/ready`
200, compose healthcheck healthy.

**Live DB state:** `migrate` ran yesterday's image (compose tags images per
service; only `backend` was rebuilt) → live head still `b7e2c4d9a1f3`, the
index migration is **not** applied there. The code does not depend on the
indexes; applying it (`docker compose --profile app build migrate && docker
compose --profile app up migrate`, or `alembic upgrade head`) is the
owner's call — brief locks on small tables plus the unique index.

Left over: `--scale backend=2` fails on the fixed `8001:8001` mapping —
ports belong on a proxy in the prod compose (H6).

## 16. H2-C — verify record (2026-09-22) — frozen-file sub-phase (S12)

Owner signed off hunks C1–C7 on 2026-09-22 after a line-level examination;
the diff to `agent/agent/interview/controller.py` is 55 lines in a
2,600-line file, applied by an assert-every-hunk script. Wire contract
(`/internal/*`, `ui_state`, data-channel commands, `StructuredAction`)
unchanged; `main.py`, `voice_adapter.py`, `persistence.py` untouched.

- **C1** `IM_READY` in `TECHNICAL_INTRO`: `current` (never bound in
  `process_ui_command`) → `self.context.current_phase`; the `NameError`
  is gone and the transition to `TECHNICAL` happens.
- **C2–C6** nine spoken English lines (already-completed, time-up wrap,
  LLM-failure fallback, IM_READY ack, five forced-transition lines) now
  come from `SYSTEM_MESSAGES[language]` via a 2-line `_msg()` helper; 14
  new keys in `llm/prompts.py`, `en` and `ar` (Saudi conversational
  register matching the existing entries; parity 32/32 asserted).
- **C7** `process_candidate_input`: a spoken control in
  `CONFIRM_BEFORE_EXECUTING` (END_INTERVIEW, SKIP_QUESTION,
  CHANGE_QUESTION, MOVE_TO_TECHNICAL, SKIP_SECTION) is held in
  `_pending_voice_control` and the controller returns an `ASK` with
  `confirm_<intent>`; the next utterance executes it only if
  `voice_intents.is_affirmative()` (short, contains an affirmative, no
  negation; en + ar tables), otherwise the pending intent is dropped and
  the utterance is processed as ordinary speech. Hint / repeat /
  clarification stay immediate; UI buttons unaffected; pending intent is
  in-memory only. New non-frozen module `interview/voice_intents.py`.

Tests: `agent/agent/tests/test_controller_h2c.py` (22): IM_READY no longer
raises (en + ar ack), key parity, completed/LLM-failure/forced lines in
Arabic contain no Latin letters, "i'm done" → ASK with no state change →
"yes" ends; "no wait…" cancels and goes to the LLM; a later bare "yes" is
not a stale confirmation; Arabic end request confirmed in Arabic; skip
confirmation stays out of LLM history; repeat immediate; 12
`is_affirmative` cases incl. the too-long-utterance rule. The one
pre-existing keyword-dependent test
(`test_skip_acknowledgement_is_not_added_to_llm_history`) passes
**unmodified**. Full `pytest` **300 passed, 1 skipped**; agent image
rebuilt and imports the new module. Behaviour delta (by decision): one
extra spoken confirmation turn for irreversible voice commands.

## 17. H2-D — verify record (2026-09-22)

**D1 lifecycle.** New `agent/agent/runtime/bootstrap.py` (`build_context`,
the 140-line context-build block moved verbatim; helpers stay in
`agent.main` for the existing tests and are imported lazily) and
`runtime/teardown.py` (`finalize_session`, the old teardown moved verbatim;
`mark_disconnected_after_failure`, new). `entrypoint` now: validate →
connect → load → `try: _run_session(...) except: mark DISCONNECTED (unless
the lease was lost) finally: cancel lease task, `adapter.aclose()`,
`persistence.close()`, `ctx.shutdown(reason)`. A `_SessionSlots` object
carries what the failure path needs from wherever the session stopped.
**No path leaves a session `IN_PROGRESS`**; the job process exits after
`COMPLETED` instead of lingering until the room closes.
**D2** `GroqProvider(timeout_seconds, max_retries)` from settings (30 s / 1;
the SDK default was 60 s × 2) — a stalled model becomes the controller's
localized fallback and the turn lock is released. **D3** `APIPersistence`:
one `_request` transport (timeout + 0.5/1/2 s retries on transport errors
and 5xx, never 4xx) and an in-memory **outbox** for messages/events/
checkpoints that still fail, flushed in order before every write, on each
lease tick and at close (idempotent: backend unique constraints). `renew_lease`
returns `LeaseState.RENEWED|LOST|ERROR`; the ABC gained default
`renew_lease`/`close` so any persistence works in the runtime. **D4** the
lease loop: `LOST` (409) or `LEASE_ERROR_SHUTDOWN_AFTER` consecutive errors →
leave the room without writing `DISCONNECTED` (another worker owns it).
**D5** STT: only `candidate-*` participants are transcribed, one at a time;
both loops run under a guard that rebuilds the pipeline up to
`STT_RESTART_MAX` times; `aclose()` cancels tasks and closes the stream.
**D6** `ui_command`: sender must be `candidate-*`, ≤ `UI_COMMAND_MAX_BYTES`,
JSON object with `command` matching `^[A-Z_]{1,64}$`; handlers tracked and
cancelled on close. **D7** `metrics_collected` re-attached after a TTS
rebuild. **D8** key-rotation state written via temp file + `os.replace`.
Settings: 7 new (documented in `agent/.env.example`). `controller.py`,
the wire contract and `/internal/*` untouched.

Tests (`agent/agent/tests/`): `test_runtime.py` (7) — failure after
`IN_PROGRESS` → event + checkpoint + `DISCONNECTED`, never raises even with
persistence broken; completed / unfinished finalization; **the real
`entrypoint` with fakes**: crash → `DISCONNECTED` + `shutdown("agent_failure")`,
lease lost → no `DISCONNECTED` write + `aclose` + `shutdown("lease_lost")`,
room disconnect after completion → completion + evaluation +
`shutdown("completed")`. `test_persistence_transport.py` (8) — retries then
success, 4xx unretried, outbox park/replay in order, ordering kept when the
replay fails, evaluation never parked, lease tri-state + flush, close flushes,
load status mapping. `test_adapter_guards.py` (7) — candidate-only audio,
STT crash restart then give-up, cancellation not a crash, `aclose`, sender /
shape / size validation, valid command dispatched and tracked. Full
`pytest` **322 passed, 1 skipped** (165 pre-existing agent tests unchanged
and green); agent image rebuilt and imports the runtime modules.

## 18. H2-E — verify record (2026-09-22)

`lib/api.ts`: `ApiError { status, code?, detail, requestId? }` thrown for
every failure — `message` is still the `detail` string (every
`err.message` consumer unchanged); network failure → `status 0, code
"network"`, timeout → `code "timeout"`; `AbortController` with
`config.apiTimeoutMs` (`VITE_API_TIMEOUT_MS`, default 30 000) and a
per-call `timeoutMs` (CV upload: 120 000); the caller's own `signal` still
works; `X-Request-ID` read from body or header. Pages: `JobDetailPage` →
`err.status === 404`, `SectionsEditor` → `err.status === 409` (no more
message string-matching). New `components/ErrorBoundary.tsx` (i18n en+ar,
reload button, collapsible details) at the router root and, with
candidate copy ("your progress is saved"), around `/interviews/:id`.
`RoleContext`: 401/403 → candidate; anything else → `unknown` + `roleError`
+ `retryRoleCheck`; `AdminLayout` shows "couldn't verify your access —
Retry" instead of `signOut()` + redirect. Test-drive
(`CandidateAccess`): `/interviews/:id`, `setGuestToken()` + `navigate()`
in the same tab (sessionStorage is per tab; `api.ts` prefers the guest
token minted for that session id) — the old code opened a non-existent
route and wrote a `localStorage` key nothing read (verified live:
`/interview/abc` → catch-all → `/login`). `alert()`/`confirm()` gone:
`JobCreatePage` hands a one-time notice to `JobDetailPage` via router
state; `JobsListPage` inline error; `QuestionEditor`/`SectionsEditor` use
`ConfirmDeleteModal`. `types/realtime.ts`: `source` gains
`HR_APPROVED | BACKGROUND`; `AllowedControl` gains the four spoken-only
controls; new `UiCommand`; `ControlIntentPayload` now `{ command, payload? }`
(the real wire shape). DEV-only `/dev/boom` route to exercise the boundary.

Tests: `lib/api.errors.test.ts` (6), `components/ErrorBoundary.test.tsx`
(3, jsdom), `context/RoleContext.test.tsx` (4, jsdom) — `jsdom` +
`@testing-library/react` added as devDependencies. vitest **22/22**;
`tsc -b` 0 errors; oxlint: only pre-existing warnings; `vite build` OK
(old test-drive code absent from the bundle). Live: `/dev/boom` renders
the boundary. Not checked live (needs an admin login): the retry screen
and the test-drive flow — covered by the RoleContext test and left to the
owner's pass.

## 19. H3 — verify record (2026-09-22)

**Logging.** Backend `core/logging.py`: `request_id_var` / `session_id_var`
contextvars, `ContextFilter` stamps `service`/`env`/`request_id`/`session_id`
on every record, `JsonFormatter` (ts, level, logger, message, service, env,
request_id, session_id, extras, exception) and `TextFormatter` (readable
line + ` request_id=… session_id=…`), `configure_logging()` replaces
`basicConfig` and routes the uvicorn loggers through the same handler.
`RequestIdMiddleware` binds the id for the request's lifetime; a router-level
dependency (`deps.bind_session_id_from_path`) binds `session_id` for every
`/api/v1/interviews/*` and `/api/v1/internal/interviews/*` route before the
handler (and before auth fails). Agent `logging_setup.py`: the SDK's root
handler is reused (exactly one plain `StreamHandler` kept; pytest's capture
handlers are subclasses and untouched), JSON formatter with the same shape
plus `agent_id`/`job_id`, text mode wraps the SDK's coloured formatter and
appends the context; `bind_session()` from `entrypoint` (job id) and after
`agent_id` creation; the old `basicConfig` block is gone (no more doubled
lines). Settings: backend `LOG_FORMAT` (json|text|auto), `LOG_LEVEL`,
`METRICS_ENABLED`; agent `LOG_FORMAT`, `LOG_LEVEL`, `ENVIRONMENT`
(`log_format_for(devmode)`); compose sets `LOG_FORMAT=json` for both.

**Correlation.** `APIPersistence._request()` sends
`X-Request-ID: <session_id>.<agent_id>.<n>` on every backend call. The
`[LLM-METRICS]` line carries `extra={event, llm_model, duration_ms,
prompt_tokens, completion_tokens}` which the JSON formatter unpacks.

**Metrics.** `core/metrics.py` (`prometheus_client` added to the lock):
`http_requests_total{method,route,status}`, `http_request_duration_seconds`,
`provider_call_duration_seconds{provider,op}`, `provider_call_failures_total`,
`sweep_runs_total{outcome}`, `sweep_finalized_total`,
`ready_check_failures_total{check}`, `background_tasks_pending`.
`MetricsMiddleware` labels by path **template**; the map now recurses into
`_IncludedRouter` entries (FastAPI 0.141 lists `include_router` routers that
way in `app.routes`) with the include prefix — the first container check
had labelled the agent's `renew-lease` 403 `<unmatched>`. `/metrics`
(unauthenticated, `include_in_schema=False`) — exposure rule documented.
Adapters decorated: groq `complete_json`; s3/supabase `put`/`delete`;
livekit `start_room_recording`/`stop_recording`/`delete_room`.

**CLI.** `backend/backend/cli.py`: `make-admin`, `finalize-stuck-sessions
[--dry-run]`, `backfill-evaluations [--dry-run]`, `create-demo-admin`,
`seed-demo-data`, using the app's engine and services (the backfill's
private copy of `resolve_criteria_for_job` is gone). `scripts/*.py` are
shims; `make cli ARGS=…` / `dev.ps1 cli -CliArgs …` set `PYTHONPATH=backend`.

**Docs.** `docs/handover/README.md`, `observability.md`, `runbooks/`
(start-stop-upgrade, apply-migration, rotate-secret, stuck-session,
provider-outage, restore-from-backup, follow-one-interview,
add-provider-adapter); `docs/technical/testing-strategy.md` rewritten to
what actually runs; hardening table added to `docs/PROJECT_STATUS.md`;
`.env.example` files extended.

**Tests.** `backend/tests/test_observability.py` (10): JSON shape, context
vars, request + session binding through a probe route, `/metrics` by
template, **included-router template** (`…/{session_id}/renew-lease`),
`<unmatched>` cardinality, provider decorator, CLI dry runs on the test DB,
parser. `agent/agent/tests/test_observability.py` (4): single handler, text
suffix, JSON context + SDK `extra` unpacking, `X-Request-ID` per call.
`test_runtime.py` fake settings extended. Full `pytest` **335 passed,
1 skipped**; vitest 22/22.

**Live (compose).** Backend image rebuilt; `POST …/internal/interviews/<sid>/renew-lease`
with a bad secret and `X-Request-ID: <sid>.runbook.1` → the JSON access line
carries `request_id` and `session_id`; `/metrics` shows
`http_requests_total{method="POST",route="/api/v1/internal/interviews/{session_id}/renew-lease",status="403"}`
and `route="/api/v1/admin/jobs/{job_id}"` for an admin route. Earlier in the
same phase the real agent container's `renew_lease` produced the same
correlated pair (`<sid>.agent-demo.1`). Runbooks executed once each:
`alembic current` = `alembic heads` = `c4d1e8f2a9b7`; `finalize-stuck-sessions
--dry-run` inside the backend container (0 stuck); `provider_call_*` /
`sweep_runs_total{outcome="ran"}` scraped; `pg_dump -Fc` → `pg_restore` into
a fresh DB (19 tables, head `c4d1e8f2a9b7`) on `postgres-test`;
`up -d --force-recreate backend` re-read the env and came back ready; the
log-merge one-liner from `follow-one-interview.md` printed the correlated
line. **Side effect to know:** starting the stack with the rebuilt `migrate`
image applied `b7e2c4d9a1f3 → c4d1e8f2a9b7` (H2-B indexes, additive) to the
live Supabase database — the item §15 left owed is therefore done. Not
checked: a full spoken interview (still owed from H2-C/D).

## 20. H2-F — verify record (2026-09-23)

Owner decisions (2026-09-23): entity named **`Task`** / table `tasks`
(`Job` is the hiring entity, AGENTS.md §1); the four endpoints **converted
in place** (with explicit sign-off to edit the legacy assertions that
pinned the synchronous contract); **CV extraction out of scope** (still
inline in the candidate's upload request); finished task rows **kept**
(no retention sweep). Two smaller calls accepted: claim with `FOR UPDATE
SKIP LOCKED` rather than S9's single advisory lock (same exclusivity per
row, but workers and replicas run in parallel), and **no automatic
requeue** of a failed task.

The defect this closes, stated concretely: `config.ts` gives every admin
call a 30s abort (`VITE_API_TIMEOUT_MS`) while the Groq adapter is built
with `timeout=30s, max_retries=2` -- up to ~90s server-side. Inline, a
slow generation aborted in the browser while the backend carried on and
**committed**: questions appeared that the admin had been told failed, an
evaluation was upserted behind a failure message, and the invitation
draft -- persisted nowhere else -- was lost outright.

New: `models/task.py` (`tasks`: kind, status `QUEUED|RUNNING|SUCCEEDED|
FAILED`, payload/result JSONB, error + error_code, attempts,
requested_by, created/started/finished, index on `(status, created_at)`),
registered in `db/base.py`; migration **`a3f7d05c1e94`** (additive, one
table). `providers/queue/{base,postgres}.py` -- the `TaskQueue` port S9
asked for, returning `TaskRecord`/`QueueStats` dataclasses rather than ORM
objects so a non-SQLAlchemy adapter can satisfy it -- plus
`factory.get_task_queue()` and `TASK_QUEUE_PROVIDER`.
`services/tasks/{handlers,registry,worker}.py`: the four endpoint bodies
moved verbatim into handlers (generators still called *through* their
module, so the legacy `patch("backend.services.question_generator.
generate_questions")` still intercepts), a kind->handler registry, and
`TASK_WORKER_CONCURRENCY` claim loops started from the lifespan and
cancelled on shutdown. Settings: 5 new, documented in `.env.example`.
Metrics: `task_queue_depth{status}`, `task_queue_oldest_age_seconds`,
`tasks_total{kind,outcome}`, `task_duration_seconds{kind}` -- the
"job-queue depth/age" H3 listed and could not yet build.

API: the four POSTs answer **202** with `{task_id, kind, status}`; their
404/409 validation stays in the endpoint so a bad request still fails
immediately rather than becoming a failed task. New
`GET /admin/tasks/{task_id}` (admin-only). Frontend: new `lib/tasks.ts`
`runTask(start, poll)` -- 1.5s polls, 3-minute ceiling, a FAILED task
rethrown as the `ApiError` the pages already display; `adminClient`
absorbs the change, so `QuestionEditor`, `InvitationComposer` and
`CandidateResultPage` keep their existing call shapes (the composer reads
the draft from `task.result`, the result page re-reads
`GET .../result`). A handler failure always carries a code now:
`NotFound`/`Conflict` have none of their own, so the worker falls back to
`task_failed` (found by the first container check, which recorded a bare
`None`).

Interrupted work: a process that dies mid-task leaves the row `RUNNING`;
worker 0 fails rows past `TASK_STALE_MINUTES` with `task_interrupted` so
a poller is never left waiting. That is reporting, not a retry.

Tests: `backend/tests/test_tasks.py` (11) -- 202 with the provider
**never awaited** during the request, a missing section still 404 at
request time, the worker running the queued generation and the rows
landing, **six concurrent claims over four rows: each claimed exactly
once**, unknown kind fails the task not the worker, handler failure
recorded with its own message, a row deleted between queueing and running,
stale-RUNNING reaped, poll 404 + admin-only, depth/age reported.
`frontend/src/lib/tasks.test.ts` (5). Legacy edits under the owner's §7
sign-off: `test_phase4.py` (two assertions, now 202 -> `run_pending_once()`
-> read the questions back through the job detail, via a new
`_questions_of` helper), `test_phase9b.py` (two, reading the rows from the
database), and `verify_9a.py` (the manual script drains the queue and
prints the task result). Full `pytest` **346 passed, 1 skipped**; vitest
**27/27**; `tsc -b` clean; pyflakes clean on every touched file (the one
warning in `admin.py` is pre-existing and untouched).

Live (compose): backend + migrate rebuilt, migration applied
(`c4d1e8f2a9b7 -> a3f7d05c1e94`) to the shared database, `/ready` 200,
`Task worker 0 started` in the JSON log, `task_queue_*` gauges published
on `/metrics`. Two real tasks enqueued inside the running container and
picked up by the worker within a second -- `regenerate_evaluation` and
`generate_invitation_message` against ids that do not exist -- each
recorded FAILED with the handler's own message and `task_failed`,
counted in `tasks_total{outcome="failed"}` and `task_duration_seconds`;
both check rows deleted afterwards. `runbooks/stuck-task.md`'s inspect
command is the one that produced that output. **Not checked live:** a
successful generation through the browser (needs an admin login) --
owed alongside the H2-C/D/E items.

