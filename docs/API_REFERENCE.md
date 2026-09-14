# Path2Hire API Reference

**Source of truth**: pulled live from `GET /openapi.json` against the running
backend (`http://127.0.0.1:8000`) on **2026-08-24**, then cross-checked
against the actual endpoint/schema source under `backend/backend/`. This is
not reconstructed from prior phase reports — those are known to drift from
live code (see "Mismatches found while writing this doc" at the bottom).
If this doc and the running server ever disagree, re-pull the OpenAPI spec
and trust that over this file.

Base URL (local dev): `http://127.0.0.1:8000`. All application routes are
under `/api/v1`. Two unprefixed routes exist: `GET /health`, `GET /version`
(both public, no auth, useful for a frontend's own health check).

---

## 1. Auth — how requests are authenticated (Phase 3)

There is **no `/login` or `/token` endpoint in this backend.** Every
authenticated route uses a single mechanism: an `Authorization: Bearer
<jwt>` header, verified by one shared dependency
(`backend/backend/core/security.py::get_current_user_token_data`), which
tries two token types in order:

1. **Supabase JWT** — verified against Supabase's JWKS endpoint
   (`ES256`/`RS256`, audience `authenticated`). This is what the frontend
   gets from the Supabase client SDK after a real login/OTP flow — this
   backend never issues these itself.
2. **Guest JWT** — a locally HS256-signed token this backend mints itself
   (`backend/backend/services/guest_jwt_service.py::mint_guest_jwt`),
   payload `{"sub": <candidate_profile_id>, "email", "type": "guest",
   "exp": now+24h}`. Minted by `POST /apply/{token}/register` (§4) and the
   legacy `POST /interviews/public/register` (§7) — a frontend never
   constructs one itself, only receives and forwards it.

Every downstream dependency reads `token_data["type"]` to decide what a
token is allowed to do:

| Dependency | Accepts | Used by |
|---|---|---|
| `get_current_admin` | Supabase token only, `sub` must have an admin `UserRole` row | All `/admin/*` routes |
| `get_current_candidate_profile_id` (`current_user_dependency`) | Either token type — resolves to a `CandidateProfile.id` | `/interviews/*`, `/profiles/*`, `/resumes/*`, `/livekit/token` |
| Redeem's own inline check | **Supabase only**, and the JWT's `email` claim must exactly match the invitation's `candidate_email` — a guest token is hard-rejected (403) even if it resolves to the right profile | `POST /invitations/{token}/redeem` |
| `verify_agent_secret` | Not a JWT at all — a shared-secret header `x-agent-secret` | `/internal/*` only (§9) |

**Non-obvious rule**: `POST /invitations/{token}/redeem` (the personalized/OTP
flow) does **not** take an OTP code in its request body — there isn't one.
The frontend must first complete Supabase's own `signInWithOtp` /
`verifyOtp` flow client-side to obtain a real Supabase session, *then* call
`/redeem` with that session's JWT. Redeem's job is only to check that JWT's
email matches the invitation and provision the session — it does not
perform OTP verification itself.

**Guest tokens are scoped to a `CandidateProfile`, not a session.** The
minted guest JWT carries no `session_id` claim, so once a guest candidate
has a token, it's valid for every session-ownership check
(`candidate_profile_id == token's resolved profile`) across *all* of that
profile's sessions, not just the one it was issued for. Not currently
enforced any more narrowly than that — see §10.

---

## 2. Admin — Job / Section / Question CRUD (Phase 4, Phase 9A)

Auth: `get_current_admin` (Supabase + admin `UserRole` row) on every route
in this section.

### Jobs

| Method | Path | Notes |
|---|---|---|
| GET | `/admin/jobs` | List all jobs, newest first. |
| POST | `/admin/jobs` | Creates a `Job` **and** its 1:1 `InterviewDefinition` in one transaction. Body: `JobCreate`. `status` always starts `"DRAFT"`; `language` defaults to `"en"` if omitted. Returns `201` + `JobResponse` (includes nested `definition`). |
| GET | `/admin/jobs/{job_id}` | Returns `JobDetailResponse` — full nested `definition.sections[].questions[]`, i.e. the whole job tree in one call. |
| PATCH | `/admin/jobs/{job_id}` | Body: `JobUpdate` (all fields optional). **409 if job is not `DRAFT`** — published jobs are read-only. |
| DELETE | `/admin/jobs/{job_id}` | **409 if not `DRAFT`** (message calls out possible active invitations/sessions). `204` on success. |
| POST | `/admin/jobs/{job_id}/publish` | DRAFT → PUBLISHED. See publish validation rules below — this is not a simple flag flip. |

**Publish validation (`POST /admin/jobs/{job_id}/publish`), in order:**
1. `409` if job isn't `DRAFT` (`"Job is already {status}"`).
2. `409` if **any** section on the job has zero questions (`"Cannot
   publish: section(s) with no questions: {types}"`). Does *not* require at
   least one section to exist at all — a job with zero sections publishes
   fine.
3. **`409` if any section is `CODING` or `MCQ`** — `"Coding and MCQ
   sections are not yet supported by the interview engine — remove this
   section or contact support."` This is a deliberate, still-active
   stopgap (backend readiness for both types was confirmed live on
   2026-08-24 — see `docs/CURRENT_DECISIONS.md` — but the guard itself
   stays until the corresponding frontend authoring/submission UI ships).
   **Frontend should not build a "your job is live" flow that assumes
   Coding/MCQ jobs can publish today.**

### InterviewDefinition (1:1 with Job, created automatically — no separate create endpoint)

| Method | Path | Notes |
|---|---|---|
| PATCH | `/admin/definitions/{definition_id}` | Body: `InterviewDefinitionUpdate` (`duration_minutes`, `is_public`). **409 if parent job not `DRAFT`.** Returns the parent `JobResponse` (with updated `definition` nested), not a bare definition object. Setting `is_public=true` lazily generates `public_access_token` the first time, independent of publish state — a job can be public while still `DRAFT`, or published while not public. |

### Sections

| Method | Path | Notes |
|---|---|---|
| POST | `/admin/sections` | Body: `SectionCreate` (`definition_id`, `section_type`: `VERBAL`\|`CODING`\|`MCQ`, `order_index` default `0`, optional `config`). **409 if that section_type already exists on this definition** (one of each type max, enforced by a DB unique constraint). **409 if parent job not `DRAFT`.** |
| PATCH | `/admin/sections/{section_id}` | Body: `SectionUpdate` (`order_index`, `config`). This is how admin-configured section **reordering** happens (Phase 5's reorder UI + Phase 9B's ordered-walk runtime both key off `order_index`). 409 if not `DRAFT`. |
| DELETE | `/admin/sections/{section_id}` | 409 if not `DRAFT`. |

### Questions

| Method | Path | Notes |
|---|---|---|
| POST | `/admin/sections/{section_id}/questions` | Manual create. Body: `QuestionCreate`. `order_index` auto-assigned (append to end). `config` is validated against the section's type — see §6 for the exact shapes; **`422` on mismatch** (e.g. a VERBAL question with a `config` payload, or a CODING question missing `starter_code`). 409 if not `DRAFT`. |
| PATCH | `/admin/questions/{question_id}` | Manual update, same `config` validation as create, only if `config` is included in the patch body. 409 if not `DRAFT`. |
| DELETE | `/admin/questions/{question_id}` | 409 if not `DRAFT`. |
| POST | `/admin/sections/{section_id}/generate-questions` | **Real Groq LLM call.** Body: `QuestionGenerateRequest` (`num_questions`, 1–20, default 5). Generates type-appropriate content (VERBAL/CODING/MCQ have distinct prompts) using the job's title/description/seniority/skills/responsibilities/location/instructions as context. Each generated question is validated the same way manual ones are — **`422` names which generated item failed** (`"AI-generated question {i+1} has invalid config: ..."`), not a blanket failure. 409 if not `DRAFT`. Returns `201` + array of `QuestionResponse`. |
| POST | `/admin/questions/{question_id}/regenerate` | **Real Groq LLM call**, no request body. Replaces one question's `title`/`competency`/`text`/`eval_criteria`/`config` in place (same `id`, same `order_index`). `502` if generation returns nothing. 409 if not `DRAFT`. |

---

## 3. Invitations — Admin CRUD (Phase 6A)

Auth: `get_current_admin`. Mounted under `/api/v1/admin` (own router file,
`invitations.py`, but same prefix/auth as §2 from the frontend's
perspective).

| Method | Path | Notes |
|---|---|---|
| POST | `/admin/definitions/{definition_id}/invitations` | Body: `InvitationCreate` (`candidate_email`). Resolves-or-creates the `CandidateProfile` and `JobApplication` for that email, generates a URL-safe token, sets `status="INVITED"`, **`expires_at` is always `NULL`** (expiration policy is unresolved — see §10), and sends the invite email (console-stub notification provider today, not production email). Returns `201` + `InvitationResponse`. |
| GET | `/admin/definitions/{definition_id}/invitations` | Lists all invitations for that definition's job, newest first. |

---

## 4. Invitations — Personalized candidate redemption (Phase 6B)

Mounted at `/api/v1/invitations`, **separate router, no admin dependency.**

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/invitations/{token}` | None (fully public) | Returns `InvitationPublicContext` (job title/description/seniority/instructions/duration, plus `invitation_status`, `candidate_email`). First call flips status `INVITED` → `OPENED`. `410` if `expires_at` is set and passed (currently never set — see §1/§10). |
| POST | `/invitations/{token}/redeem` | **Supabase JWT required**, guest tokens explicitly rejected | See §1 for the two hard 403 checks (must be Supabase, email must match). No request body. Idempotent: calling it again once `status="STARTED"` doesn't create a second session — it re-mints a fresh LiveKit token for the existing one. Returns `RedeemResponse` (`session`, `livekit_token`, `livekit_url`). |

---

## 5. Public Apply — guest self-registration (Phase 6C)

Mounted at `/api/v1/apply`, fully public — no auth on either route, and
`register` is what *mints* the guest JWT the candidate then uses everywhere
else (§1).

| Method | Path | Notes |
|---|---|---|
| GET | `/apply/{token}` | `token` = the `InterviewDefinition.public_access_token`, not an invitation token. `403 "Invalid or inactive public access link"` unless the definition is `is_public=true` **and** its job is `PUBLISHED`. Returns `PublicApplyContext`. |
| POST | `/apply/{token}/register` | Body: `PublicRegisterRequest` (`name`, `email`, optional `resume_id`). Resolves-or-creates `CandidateProfile`/`JobApplication` by email, mints a guest JWT, **creates a brand-new `InterviewSession` every call** — repeat registrations by the same email are NOT idempotent the way §4's redeem is (no invitation-status concept here to key off). Returns `PublicRegisterResponse` (`access_token`, `session`, `livekit_token`, `livekit_url`) — the LiveKit token is already included, no separate `/livekit/token` call needed for the initial join. |

---

## 6. Type-specific `config` / `eval_criteria` JSONB shapes

**The OpenAPI spec shows `config` and `eval_criteria` as bare `object`
(`additionalProperties: true`) on every question/section schema** —
FastAPI can't express "shape depends on `section_type`" in the generated
spec. The real shapes, enforced server-side by
`backend/backend/schemas/admin.py::validate_question_config` at **every**
write path (manual create, manual update, AI generate, regenerate — no
exceptions), are:

### VERBAL
`config` must be **absent/null**. Sending one is a `422`
(`"VERBAL questions must not carry a config payload."`). `eval_criteria`
shape (not schema-enforced, but what the AI generator actually produces):
```json
{ "excellent": "...", "good": "...", "adequate": "...", "poor": "..." }
```

### CODING
`config` is **required**, shape (`CodingConfig`):
```json
{
  "starter_code": "def two_sum(nums, target):\n    pass",
  "supported_languages": ["python"],
  "constraints": "2 <= nums.length <= 10^4",
  "hints": ["Consider a hash map of seen values.", "..."]
}
```
`hints` defaults to `[]` if omitted — additive field from Phase 9A, safe to
leave off. `eval_criteria` shape actually produced by the AI generator
(**not** VERBAL's excellent/good/adequate/poor bands — this was a real
documentation error caught and corrected mid-transition, see
`docs/CURRENT_DECISIONS.md`):
```json
{
  "time_complexity": "O(n)",
  "space_complexity": "O(n)",
  "edge_cases": ["empty array", "no valid pair"],
  "rubric": "Award partial credit for a correct hash-map approach even if incomplete."
}
```

### MCQ
`config` is **required**, shape (`MCQConfig` / `MCQOption`):
```json
{
  "options": [
    { "id": "A", "text": "A programming language" },
    { "id": "B", "text": "A snake" }
  ],
  "correct_answers": ["A"],
  "is_multi_select": false
}
```
**Referential integrity is checked server-side**: every value in
`correct_answers` must match a real `options[].id`, or it's a `422`
(`"correct_answers references non-existent option IDs: [...]"`). This is
not something Pydantic's shape validation catches on its own — it's an
explicit extra check. `eval_criteria` shape actually produced (explanation
only, no bands):
```json
{ "explanation": "Python is an interpreted, general-purpose language." }
```

**Frontend implication**: a Coding/MCQ question-authoring or
submission-rendering UI cannot infer these shapes from the OpenAPI
schema/generated client types alone — hand-type them (or copy the JSON
shapes above) rather than trusting a codegen tool run against
`/openapi.json`.

---

## 7. Legacy / candidate self-serve — pending removal in Phase 10

**Do not build new frontend against the creation/registration endpoints in
this section.** They predate the Job → InterviewDefinition → Invitation
model (§2–§5) and create sessions with no `job_id`/`definition_id`/
`application_id` at all. Mounted at `/api/v1/interviews`.

| Method | Path | Auth | Status |
|---|---|---|---|
| POST | `/interviews/public/register` | None | **Legacy — do not build against.** Predecessor to §5's `/apply/{token}/register`. Only checks `definition.is_public`, **not** `job.status` — looser than §5's equivalent check, so a still-`DRAFT`-but-public job can register through this endpoint but not through §5's. Mints a guest JWT the same way. |
| POST | `/interviews/` | Candidate (guest or Supabase) | **Legacy — do not build against.** Creates an `InterviewSession` + `InterviewConfiguration` directly from a client-supplied `role`/`level`/`language`/`job_description`/`duration`/`thinking_time` — no Job/Definition involved at all. |

**These are NOT legacy — they're the current, active way any candidate
(from any flow) checks their own session, regardless of how it was
created.** Nothing in §3–§5 replaces them; a session created via redeem or
public-apply is looked up through these same routes afterward:

| Method | Path | Notes |
|---|---|---|
| GET | `/interviews/` | List the caller's own sessions. |
| GET | `/interviews/{session_id}` | Ownership-checked (`candidate_profile_id == caller`), `403` otherwise. |
| POST | `/interviews/{session_id}/terminate` | Closes an abandoned session so a fresh one can start; no-ops (returns 200) if already `COMPLETED`/`TERMINATED`. |
| GET | `/interviews/{session_id}/transcript` | Ordered message list. **No declared response schema in OpenAPI** (returns a raw list of dicts) — shape is `{sequence_number, speaker, text, phase, created_at}[]`. |
| GET | `/interviews/{session_id}/events` | Ordered event list, same "no formal schema" note. Shape: `{event_type, phase, sequence_number, metadata, created_at}[]`. |
| GET | `/interviews/{session_id}/result` | `400` if session isn't `COMPLETED`/`TERMINATED` yet. `409` if completed but evaluation hasn't finished persisting yet (poll again shortly). Returns `InterviewResultResponse` (`final_result` is the same JSONB blob `Evaluation`/`Score` tables will eventually replace per Phase 8). |

---

## 8. Candidate Profile & Resume (self-serve, authenticated)

Auth: `current_user_dependency` (guest or Supabase). Mounted at
`/api/v1/profiles` and `/api/v1/resumes`.

| Method | Path | Notes |
|---|---|---|
| POST | `/profiles/` | `400` if a profile already exists for this token's subject. |
| GET | `/profiles/me` | `404` if no profile yet. |
| PATCH | `/profiles/me` | Partial update, any subset of `CandidateProfileUpdate` fields. |
| POST | `/resumes/` | Multipart file upload (`UploadFile`). Validates PDF, uploads to Supabase Storage, extracts text, then **a real LLM call** structures it into profile fields (education/skills/languages/frameworks/projects/title/recommended_level) and writes them onto the candidate's profile directly. `extraction_status` goes `PROCESSING` → `COMPLETED`/`FAILED`; `500` returned synchronously if extraction throws (not backgrounded). |
| GET | `/resumes/` | List the caller's own resumes. |

## 9. LiveKit session token

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/livekit/token` | `current_user_dependency` | Body: `{"session_id": "..."}`. Ownership-checked. Mints a fresh LiveKit room-join token for an *existing* session — mainly needed for **reconnect** scenarios (candidate reloads mid-interview); initial join tokens are already returned inline by §4's redeem and §5's register, so a frontend shouldn't need to call this on first entry. `500` if `LIVEKIT_API_KEY`/`SECRET`/`URL` aren't configured server-side. |

---

## 10. Internal / agent-only — NOT for frontend consumption

Mounted at `/api/v1/internal/interviews`. Auth is **not a JWT at all** — a
shared-secret header, `x-agent-secret`, checked against
`settings.AGENT_API_SECRET` (`503` if the server has no secret configured,
`403` on mismatch). These exist purely for the LiveKit Agent Worker process
to talk to the backend; a browser frontend has no legitimate reason to call
any of these and has no way to obtain a valid `x-agent-secret` anyway.

| Method | Path | Purpose |
|---|---|---|
| GET | `/internal/interviews/{session_id}/load` | Agent bootstrap/resume: full session context including ordered `sections[].questions[]` (with their real `config`/`eval_criteria`), candidate profile, latest checkpoint, recent messages. Also acquires/refreshes the agent's exclusive lease on the session (`409` if another agent already holds it). `409` if session already `COMPLETED`/`TERMINATED`. |
| POST | `/internal/interviews/{session_id}/renew-lease` | Keep-alive for the lease acquired by `/load`. `409` if the caller doesn't currently hold it. |
| PATCH | `/internal/interviews/{session_id}/status` | Status machine: `CREATED→IN_PROGRESS→{DISCONNECTED,COMPLETED,TERMINATED}`, `DISCONNECTED→{IN_PROGRESS,TERMINATED}`. `400` on an invalid target or an unmodeled transition. Reaching `COMPLETED`/`TERMINATED` releases the lease. |
| POST | `/internal/interviews/{session_id}/messages` | Append one transcript message. Idempotent on `(session_id, sequence_number)` — a retry with the same sequence number returns the existing row instead of erroring. |
| POST | `/internal/interviews/{session_id}/events` | Same idempotency pattern, for lifecycle events. |
| POST | `/internal/interviews/{session_id}/checkpoints` | Append one recovery checkpoint (phase, question index, hints/followups used, section progress JSONB, etc.). |

---

## 11. Cross-reference: things a frontend/handover builder needs to know that aren't in the API shape itself

Pulled from `docs/CURRENT_DECISIONS.md`'s "Still unresolved" list — these
are **not bugs**, they're product decisions that haven't been made yet, so
don't build UI that assumes an answer either way:

- **Invitation expiration is unenforced.** `expires_at` is always `NULL`
  today (§3). The `410`-if-expired check in §4's `GET /invitations/{token}`
  exists in code and will activate automatically the moment this policy is
  set — no endpoint changes needed then, but right now an invitation link
  never expires.
- **Guest tokens aren't scoped to one session** (§1) — verified directly
  in `guest_jwt_service.py`, not currently listed in
  `CURRENT_DECISIONS.md`'s unresolved section even though it's a real,
  live behavior; flagging it there is worth doing separately from this doc.
- **Whether candidates can retake an interview** — unresolved. Nothing in
  the API currently blocks a repeat `/apply/register` (§5) creating a
  second session for the same email/job; don't build a "one attempt only"
  UI assumption.
- **Editing an already-published interview** — unresolved. Today, PATCH/
  POST/DELETE on jobs/sections/questions all hard-`409` once the job is
  `PUBLISHED` (§2) with no unpublish path exposed anywhere in this API.
- **Multiple admin users / permissions** — unresolved. `get_current_admin`
  is a single boolean role check; there's no per-admin scoping of which
  jobs an admin can see/edit.
- **Email templates / real provider** — blocked on the still-unresolved
  email provider decision; invitation emails currently go to a console
  stub, not a real inbox.
- **`level` silently defaults to `"mid"`** when `Job.seniority` is unset,
  at both §4's redeem and §5's register (`job_seniority or "mid"`) — a
  frontend that lets HR leave seniority blank should know candidates will
  silently get a "mid" level interview.

---

## Mismatches found while writing this doc

None. Every route, status code, and validation rule documented above was
read directly from the live `/openapi.json` pull and the actual endpoint
source in `backend/backend/`, not from `docs/PROJECT_STATUS.md` or other
prior phase reports. Cross-checking against `PROJECT_STATUS.md`'s claims
specifically (Phase 6A/6B/6C, Phase 9A/9F's publish-stopgap wording,
Phase 4/9A's config validation), live behavior matched what was reported
in every case checked. The one genuine surprise — legacy
`/interviews/public/register` checking only `is_public` while
`/apply/{token}/register` also requires `job.status == "PUBLISHED"` — is
already called out **in the code's own comment**, not a case of a report
claiming something the code doesn't do; recorded in §7 because it's a real
behavior difference a frontend engineer needs to know, not because a prior
report got it wrong.
