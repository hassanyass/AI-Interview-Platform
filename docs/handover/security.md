# Security and data protection

Written during hardening H5 and kept current with it. Three things: what
an attacker would try and what stops them, where every piece of personal
data lives and what deletes it, and where this system stands on PDPL/GDPR
obligations — including the one that is still an open decision.

## 1. Trust boundaries

| Who | Credential | What they can reach |
|---|---|---|
| Candidate (public link) | guest JWT, HS256, minted here, 24h | only their own session: `GET/POST /interviews/{id}/*`, `/livekit/token`. Every route re-checks ownership |
| Candidate (invited) | Supabase JWT (ES256/RS256) | as above, plus redeeming their own invitation |
| Admin (HR) | Supabase JWT + a `users_roles` row | all `/api/v1/admin/*` |
| Agent worker | `X-Agent-Secret` shared secret | only `/api/v1/internal/*` |
| Anyone | none | three routes: the two public-apply ones and the invitation preview |

The two token kinds are told apart **before** verification by whether the
JOSE header carries a `kid` — a Supabase token always does, a guest token
never does — so a token is verified on exactly one path, with algorithms
pinned and `iss`/`aud` checked. Neither falls back to the other
(`core/security.py`, H5-A).

## 2. Threat model

| An attacker tries to… | What stops them | Where |
|---|---|---|
| Forge a token | Asymmetric verification against the project JWKS; guest tokens HS256 with `SECRET_KEY`; algorithms pinned; `iss`/`aud`/`exp`/`sub` required | `core/security.py` |
| Swap one token kind for the other (algorithm confusion) | Path chosen by `kid`, never by "try both" | `core/security.py` |
| Read another candidate's interview | Every session route compares the caller's profile to the session's owner; `terminate` and `/livekit/token` scope their query by owner and answer 404 rather than confirming the session exists | `api/endpoints/interviews.py`, tested in `test_auth_matrix.py` |
| Reach the admin API as a signed-in candidate | `get_current_admin` requires a `users_roles` row, 403 not 401 | `api/deps.py` |
| Claim someone's profile by signing up with their address | An identity may only adopt a profile that holds no sessions and no CV, unless the token proves the address was verified; `IDENTITY_AUTOLINK` sets the policy; every outcome logged | `api/deps.py`, H5-A |
| Change their address to impersonate an invited candidate | `email` is not writable on `PATCH /profiles/me` | `schemas/profile.py` |
| Drive the interview from another participant | `ui_command` must come from `candidate-*`, be under the size cap, match the shape, **and be one of 20 known commands** | `agent/interview/voice_adapter.py`, H5-B |
| Script thousands of registrations | Token-bucket limits per scope; 429 with `Retry-After` | `core/ratelimit.py`, H5-B |
| Make us pay for recordings | Recording start is claimed with a conditional UPDATE, so one session starts at most one egress | `services/sessions/room_token.py`, H5-B |
| Use a stolen admin session unnoticed | Publish, status change, job/session/candidate deletion and score overrides all write an `admin_audit_log` row with actor, target, details and request id | `services/audit.py`, H5-C |
| Read the metrics endpoint | Unauthenticated by design — **keep `/metrics` off the public ingress**, or set `METRICS_ENABLED=false` on internet-facing replicas | `observability.md` |

Known and accepted: there is **no rate limit on admin routes** (they need
a valid admin credential first), and rate limits are per process — with N
replicas each enforces its own share (`core/ratelimit.py` says how to swap
the store).

## 3. Data map

What personal data exists, where it lives, and what removes it.

| Data | Where | Removed by |
|---|---|---|
| Name, email, CV-derived profile (skills, education, experience) | `candidate_profiles` (Postgres) | `DELETE /admin/candidates/{id}`; the purge job |
| CV file | Supabase Storage, `RESUMES_BUCKET` | as above — **the only paths that delete a stored CV** |
| CV metadata and extracted text | `resumes` | cascade from the profile |
| Interview transcript | `interview_messages` | cascade from the session |
| Interview events, checkpoints, consent | `interview_events`, `interview_checkpoints`, consent rows | cascade from the session |
| Evaluation, scores, HR override | `evaluations`, `scores` | cascade from the session |
| Audio/video recording | Cloudflare R2, `R2_BUCKET_NAME` | `DELETE /admin/interviews/{id}` and `DELETE /admin/candidates/{id}`; the purge job |
| Auth identity (email, password hash) | Supabase Auth — **not this database** | deleted in the Supabase dashboard; deleting a profile here does not remove the Supabase user |
| Who did what to the above | `admin_audit_log` | nothing: deliberately outlives the data it describes |
| Names/emails in application logs | container stdout | log rotation, per deployment |

Two limits worth stating plainly. Deleting a **session** deliberately
leaves the person intact, because a profile is shared with every other job
they applied to — use the candidate delete to erase a person. And the
Supabase Auth user is a separate system: a full erasure request needs both.

## 4. Deletion and retention

- `DELETE /api/v1/admin/candidates/{profile_id}` — erases the person:
  every recording, every CV object, then the profile row, which cascades
  to sessions, applications, invitations and resume rows. Object storage
  is best effort; anything that could not be deleted is named in the audit
  entry as an orphan needing manual cleanup, because refusing to delete
  the rows would leave an administrator unable to remove the person at all.
- `DELETE /api/v1/admin/interviews/{session_id}` — one interview and its
  recording.
- **Purge job** (`purge_expired_data`, a task kind in the H2-F queue) —
  deletes candidates whose every interview is older than a threshold.
  **Shipped disabled**: `DATA_PURGE_ENABLED=false`,
  `DATA_PURGE_AFTER_DAYS=0`, and it refuses to run under either. Its
  `dry_run` mode reports what would go without touching anything.

> **Open decision — U1.** How long recordings, transcripts and CVs are
> kept, and who may authorise deletion, is not decided. Until it is
> recorded in `CURRENT_DECISIONS.md`, nothing is deleted automatically and
> the retention answer to a candidate's question is "indefinitely".
> This is the single biggest gap in this document.

## 5. PDPL / GDPR posture

Honest status, not a compliance claim.

| Obligation | Where this stands |
|---|---|
| Lawful basis, transparency | Candidates consent to recording before an interview starts (`POST /interviews/{id}/consent`, stored with the disclosure text they saw) |
| Purpose limitation | Data is used for the interview and its evaluation; no profiling beyond it, no third-party sharing beyond the processors below |
| Storage limitation | **Not met — U1 is open.** The mechanism exists and is switched off |
| Right of access | No self-service export. HR can read everything through the admin UI; a request is manual today |
| Right to erasure | Met for this system by the candidate delete (above); the Supabase Auth user must be deleted separately |
| Right to rectification | Partial: HR can edit; the candidate cannot, and `email` is deliberately not self-editable |
| Data minimisation | The CV is parsed into structured fields; the original file is kept and is deletable |
| Security of processing | Sections 1–2; TLS is the deployment's responsibility (H6) |
| Processors | Supabase (auth, database, CV storage), LiveKit (real-time media, recording), Groq (LLM/STT/TTS — transcripts and CV text are sent), Cloudflare R2 (recordings). A data-processing agreement with each is the operator's responsibility |
| Breach notification | No documented procedure — for the operator to write |

## 6. Operational rules

- Secrets come from the environment; nothing has a working default.
  Outside `local`/`test` the process **refuses to start** with a
  placeholder `SECRET_KEY`, an empty `AGENT_API_SECRET` or LiveKit
  credential, or a CORS list that is empty, contains `*`, or still names
  localhost (`core/config.py`).
- `.env` is git-ignored and has never been committed; `.env.example`
  files contain placeholders only. Rotation: `runbooks/rotate-secret.md`.
- Both images run as an unprivileged user (uid 10001) and carry no tests,
  caches or `.env`.
- CI fails on a known vulnerability in a **runtime** dependency
  (`pip-audit`, `npm audit --omit=dev`); dev-only advisories are reported
  without gating.

## 7. OWASP API Security Top 10 — review of 2026-09-24

Reviewed against this codebase, not a checklist copied in.

| # | Risk | Status |
|---|---|---|
| 1 | Broken object-level authorization | **Addressed.** Every session route checks ownership; `test_auth_matrix.py` proves candidate B cannot reach candidate A's session on any of them |
| 2 | Broken authentication | **Addressed** in H5-A: one verification path per token, no fallback, pinned algorithms, `iss`/`aud` checked, JWKS outage reported as 503 |
| 3 | Broken object-property-level authorization | **Addressed** for the known case (`email` removed from the profile update schema). Admin schemas accept only declared fields |
| 4 | Unrestricted resource consumption | **Partly.** Rate limits on the anonymous and expensive routes (H5-B); provider calls bounded (H2-A). A permitted burst (20) can still exceed the database's own connection ceiling (15 on the Supabase pooler) — choose the two together per deployment — but that now answers **503 + `Retry-After`**, not a 500 (`core/db_errors.py`), so it reads as backpressure rather than a fault |
| 5 | Broken function-level authorization | **Addressed.** Admin routes require a role row; `test_auth_matrix.py` walks the whole route table so a new route without auth fails the build |
| 6 | Unrestricted access to sensitive business flows | **Partly.** Registration is rate-limited but still creates a session per call by design; no CAPTCHA or device signal |
| 7 | Server-side request forgery | **Not applicable.** No user-supplied URL is fetched |
| 8 | Security misconfiguration | **Addressed:** fail-closed settings, explicit CORS, non-root images, no secrets in the repo. **Gap:** TLS, ingress and network policy are the deployment's (H6) |
| 9 | Improper inventory management | **Yes.** One API version, documented in `docs/API_REFERENCE.md`. `/docs`, `/redoc` and `/openapi.json` are served only when `expose_api_docs` is true — on for `local`/`test`, **off for `staging` and `production`**, overridable either way with `EXPOSE_API_DOCS`. Passing `None` to FastAPI removes the routes rather than hiding them, so there is nothing left to probe. (Was an open gap through H5-C.) |
| 10 | Unsafe consumption of third-party APIs | **Addressed.** Every provider is behind an adapter with timeouts and bounded retries; LLM output is validated (`validate_question_config`) before it is stored |

Two items above are genuine open gaps rather than accepted risk: **#4**'s
burst-vs-pool ceiling and **#9**'s public `/docs`. Both are recorded here
rather than quietly closed.
