# Himma Interview Platform — Data Flow Diagram (Level 0 → Level 1)

Written from the actual current codebase (2026-09-11), not a design intent doc. Every table, field, and endpoint named below exists in `backend/backend/models/`, `backend/backend/api/endpoints/`, and `backend/backend/schemas/` as of this writing. Use this alongside `architecture-overview.md` (tech stack / hosting) when redesigning the visuals — this file is the content spec; that file is the platform spec.

---

## 1. External entities

| Entity | Type | What it does at the boundary |
|---|---|---|
| **HR admin** | Human | Authenticated staff user. Authors jobs/interviews, reviews candidate results, generates invitations. |
| **Candidate** | Human | Applies to a job (Flow A) or opens an invite/public link (Flow B), completes a live voice interview. |
| **Supabase Auth** | External system | Issues/verifies JWTs for admin and Flow-A candidate logins (email+password, OTP). Source of truth for `auth.users`. |
| **LiveKit Cloud** | External system | WebRTC SFU. Hosts the interview "room"; both the candidate's browser and the agent worker connect to it as participants. |
| **Groq** | External system | LLM inference (question generation, evaluation scoring, invitation-message drafting) and, inside the agent, STT/TTS during the live interview. |
| **Azure Speech** | External system | Fallback/alternate STT+TTS provider for the live interview (selected via `TTS_PROVIDER` env var). |
| **Cloudflare R2** | External system | S3-compatible object storage for full session audio+video recordings (LiveKit Egress writes here; the backend reads via presigned URLs). |

---

## 2. Data stores (Postgres, via Supabase)

Every table below is a `Base` model in `backend/backend/models/`. "Owner process" = who mostly writes it; other processes may still read it.

| # | Table | Key columns (non-exhaustive) | Owner process |
|---|---|---|---|
| D1 | `auth.users` | `id`, `email`, encrypted password | Supabase Auth (external, not our schema) |
| D2 | `users_roles` | `id`, `user_id`, `role` (`admin`\|`candidate`) | P2.1 Auth & RBAC |
| D3 | `candidate_profiles` | `id`, `supabase_user_id`, `full_name`, `email`, `skills`, `resume` fields, `recommended_level`, `confirmed_level` | P2.3 Candidate Acquisition |
| D4 | `resumes` | `id`, `profile_id`, `storage_path`, `extracted_text`, `extraction_status` | P2.3 Candidate Acquisition |
| D5 | `jobs` | `id`, `title`, `description`, `seniority`, `location`, `required_skills`, `preferred_skills`, `responsibilities`, `status` (`DRAFT`\|`PUBLISHED`\|`CLOSED`), `language` | P2.2 Job & Content Authoring |
| D6 | `interview_definitions` | `id`, `job_id` (1:1), `duration_minutes`, `is_public`, `public_access_token` | P2.2 Job & Content Authoring |
| D7 | `interview_sections` | `id`, `definition_id`, `section_type` (`VERBAL`\|`CODING`\|`MCQ`), `order_index`, `config` (incl. `time_budget_minutes`) | P2.2 Job & Content Authoring |
| D8 | `interview_questions` | `id`, `section_id`, `order_index`, `title`, `competency`, `text`, `eval_criteria`, `config` (type-specific) | P2.2 Job & Content Authoring |
| D9 | `assessment_criteria` | `id`, `job_id` (null = TEMPLATE), `section_id`, `key`, `label`, `kind`, `weight`, `enabled`, `source` | P2.2 Job & Content Authoring |
| D10 | `job_applications` | `id`, `job_id`, `candidate_profile_id`, `resume_id`, `professional_title` | P2.3 Candidate Acquisition |
| D11 | `interview_invitations` | `id`, `application_id`, `candidate_email`, `status`, `token`, `otp_hash`, `otp_expires_at`, `expires_at` | P2.3 Candidate Acquisition |
| D12 | `interview_sessions` | `id`, `candidate_profile_id`, `job_id`, `definition_id`, `application_id`, `role`, `level`, `language`, `status`, `active_agent_id`, `agent_lease_expires_at`, `recording_egress_id`, `recording_storage_path`, `final_result` (JSONB) | P2.4 Live Session Support / P3 Agent |
| D13 | `interview_configurations` | `session_id` (1:1), `role`, `level`, `language`, `duration`, `thinking_time` | P2.4 Live Session Support |
| D14 | `interview_messages` | `id`, `session_id`, `sequence_number`, `speaker`, `text`, `phase` | P3 Agent |
| D15 | `interview_events` | `id`, `session_id`, `event_type`, `phase`, `sequence_number`, `metadata` | P3 Agent |
| D16 | `interview_consents` | `id`, `session_id`, `disclosure_language`, `disclosure_text` | P2.4 Live Session Support |
| D17 | `interview_checkpoints` | `id`, `session_id`, `current_phase`, `question_index`, `hints_used`, `followups_used`, `question_records`, `evaluation_signals`, `time_remaining_seconds` | P3 Agent |
| D18 | `evaluations` | `id`, `session_id` (1:1), `overall_score`, `recommendation`, `evidence_sufficiency`, `summary`, `detailed_overview`, `weighted_score`, `is_placeholder`, `override_suggested`, `override_reason` | P2.5 Results & Evaluation / P3 Agent |
| D19 | `scores` | `id`, `evaluation_id`, `criterion_id`, `criterion_key`, `score`, `overview`, `strengths`, `improvements`, `evidence_reference` | P2.5 Results & Evaluation / P3 Agent |

---

## 3. Level 0 — context diagram (already drawn)

One process, **Himma interview platform**, exchanging data with the 7 external entities in §1. No data stores shown at this level (standard DFD convention — stores only appear once the process is decomposed).

---

## 4. Level 1 — process decomposition

The Level-0 process splits into three deployed processes, and the backend further splits into five logical sub-processes (all in one FastAPI app, grouped by the router file that implements them).

```
P1  Frontend SPA                (Vercel)
P2  Backend API                 (Render)
 ├─ P2.1 Authentication & RBAC
 ├─ P2.2 Job & Content Authoring
 ├─ P2.3 Candidate Acquisition
 ├─ P2.4 Live Session Support API
 └─ P2.5 Results & Evaluation
P3  Agent Worker                (Railway)
```

For each process: **Inputs** (data flow name — source), **Outputs** (data flow name — destination), **Reads**, **Writes**.

---

### P1 — Frontend SPA (React/Vite, `frontend/src/`)

Not a data-transforming process itself — it's the UI layer that originates/renders every flow below. Listed separately from P2 because it is a distinct deployed artifact (static bundle on Vercel) with its own inputs/outputs.

- **Inputs**
  - `credentials` (email + password) — from HR admin
  - `application details` (name, email, resume file) — from Candidate, Flow A
  - `OTP code` — from Candidate, Flow B
  - `job/section/question edits` — from HR admin
  - `interview answers` (voice via LiveKit track, code submission, MCQ selection) — from Candidate
  - `job list`, `evaluation detail`, `presigned recording URL` — from P2 (API responses)
  - `LiveKit access token + URL` — from P2
- **Outputs**
  - `Supabase JWT` requests — to Supabase Auth directly (`supabase-js`, browser → Supabase, bypasses P2)
  - `Authorization: Bearer <token>` + REST calls — to P2 (`VITE_API_BASE_URL`)
  - `WebRTC room join` — to LiveKit Cloud directly (`livekit-client`, browser → LiveKit, bypasses P2 after token issuance)
- **Reads / writes**: none (no direct DB access; every persistent read/write goes through P2)

---

### P2.1 — Authentication & RBAC (`backend/backend/core/security.py`, `api/deps.py`)

- **Inputs**
  - `Bearer <JWT>` header on every authenticated request — from P1
- **Outputs**
  - `401 Invalid authentication credentials` / `403 Admin privileges required` — to P1
  - resolved `admin_id` / `candidate_profile_id` — internal, passed to whichever P2.x handler is actually serving the request
- **Reads**: D2 `users_roles` (role lookup by `user_id`), D3 `candidate_profiles` (profile resolution by `supabase_user_id`/email)
- **Writes**: D3 `candidate_profiles` (lazily creates a profile row the first time a new Supabase-authenticated candidate is seen)
- **External call**: fetches Supabase's JWKS (`SUPABASE_JWKS_URL`) to verify the JWT signature — cached client-side (`PyJWKClient`), not per-request

---

### P2.2 — Job & Content Authoring (`api/endpoints/admin.py`, job/section/question/criteria routes)

- **Inputs**
  - `job fields` (title, description, seniority, skills, responsibilities) — from HR admin
  - `section definitions` (type, order, time budget) — from HR admin
  - `"generate questions" request` (job context + section type + count) — from HR admin
  - `criteria edits` (label, weight, enabled) — from HR admin
  - `publish command` — from HR admin
- **Outputs**
  - `job/section/question/criteria records` — to P1 (rendered in JobDetailPage/SectionsEditor/QuestionEditor/CriteriaEditor)
  - `prompt` (job context, section type, question count) — to Groq
  - `generated questions` (title, competency, text, eval_criteria, config) — from Groq, to D8
  - `publish validation errors` (empty section / no time budget) — to P1
- **Reads**: D5 `jobs`, D6 `interview_definitions`, D7 `interview_sections`, D8 `interview_questions`, D9 `assessment_criteria`
- **Writes**: D5, D6, D7, D8, D9 (full CRUD except delete on published jobs with sessions)
- **External call**: Groq chat completion (`question_generator.generate_questions`, offloaded via `asyncio.to_thread`)

---

### P2.3 — Candidate Acquisition (`api/endpoints/public_apply.py`, `public_invitations.py`, `invitations.py`, `resumes.py`, `profiles.py`)

Two parallel candidate-entry flows:

**Flow A — public apply link** (`GET/POST /api/v1/apply/{token}`)
- **Inputs**: `job token` (URL) — from Candidate; `name, email, resume_id` (`PublicRegisterRequest`) — from Candidate
- **Outputs**: `PublicApplyContext` (job_title, description, seniority, instructions, duration) — to P1; `PublicRegisterResponse` (guest `access_token`, `session`, `livekit_token`, `livekit_url`) — to P1
- **Reads**: D6 `interview_definitions` (by `public_access_token`)
- **Writes**: D3 `candidate_profiles` (create), D10 `job_applications` (create), D12 `interview_sessions` (create, `status=CREATED`)

**Flow B — HR-sent invitation** (`GET/POST /api/v1/invitations/{token}` + admin-side `invitations.py`)
- **Inputs**: HR-side `create invitation` (application_id, candidate_email) — from HR admin; candidate-side `invite token` (URL) + `OTP` — from Candidate
- **Outputs**: `InvitationPublicContext` (job_title, description, invitation_status, candidate_email) — to P1; `RedeemResponse` (`session`, `livekit_token`, `livekit_url`) — to P1; OTP delivery — to Candidate (console/notification provider, `services/notifications/`)
- **Reads**: D10 `job_applications`, D11 `interview_invitations`
- **Writes**: D11 `interview_invitations` (status transitions `INVITED → OPENED → VERIFIED → STARTED`, OTP hash/expiry, attempt count), D12 `interview_sessions` (create on redeem)

**Resume handling** (`resumes.py`)
- **Inputs**: uploaded resume file — from Candidate
- **Outputs**: `extracted_text`, `extraction_status` — to D4, then surfaced to P2.2/P2.5 read paths
- **Reads/Writes**: D4 `resumes`
- **External call**: PyMuPDF (local, no external service) for text extraction; optionally Supabase Storage client (`resume_service.py`) — **known bug**: `create_client()` currently raises on this project's new-format `SUPABASE_SECRET_KEY`, so this path degrades to `supabase = None` (see `architecture-overview.md`'s known-issues section)

---

### P2.4 — Live Session Support API (`api/endpoints/livekit.py`, `internal.py`)

The bridge between P1/P3 and D12–D17 while an interview is actually running. `internal.py`'s routes are gated by `agent_auth` (a shared `AGENT_API_SECRET`, not a user JWT) — only P3 calls these, never P1 directly.

- **Inputs**
  - `session_id` — from P1 (`POST /api/v1/livekit/token`)
  - `session_id, agent_id` (load / lease renewal / checkpoint save / finalize) — from P3
  - `evaluation payload` (overall_score, recommendation, criterion_scores) — from P3
- **Outputs**
  - `livekit_token, livekit_url` — to P1 (signed via `livekit-api`, using `LIVEKIT_API_KEY`/`SECRET`)
  - `SessionLoadResponse` (role, level, language, questions, checkpoint state) — to P3
  - `lease renewal ack` — to P3
  - `room dispatch` — to LiveKit Cloud (implicit: the candidate's token grants room access, the agent is dispatched by LiveKit's own job dispatch to any registered worker)
  - `recording egress start command` — to LiveKit Cloud → Cloudflare R2 (background task, retried up to 10× 1s apart to outrun the room-not-yet-created race)
- **Reads**: D12 `interview_sessions`, D13 `interview_configurations`, D6/D7/D8 (question set), D17 `interview_checkpoints` (resume path)
- **Writes**: D12 (`active_agent_id`, `agent_lease_expires_at`, `recording_egress_id`, `recording_storage_path`, `status`, `final_result`), D13 (create), D14 `interview_messages`, D15 `interview_events`, D16 `interview_consents`, D17 `interview_checkpoints`, D18/D19 (evaluation upsert, shared with P2.5's `_upsert_evaluation`)
- **External calls**: LiveKit Cloud (token grant API, egress API)

---

### P2.5 — Results & Evaluation (`api/endpoints/admin.py`'s result routes)

- **Inputs**
  - `session_id` (view result / regenerate evaluation) — from HR admin
  - `override_suggested, override_reason` — from HR admin
  - `job_id` (list results) — from HR admin
- **Outputs**
  - `EvaluationDetailResponse` (transcript, question_records, technical_submission, scores, recommendation, `is_mock_data`, `recording_url`) — to P1
  - `JobResultsResponse` (per-candidate row + aggregate counts) — to P1
  - `prompt` (transcript + criteria) — to Groq, on regenerate
  - `presign request` — to Cloudflare R2 (short-lived GET URL, computed fresh per request, never stored)
- **Reads**: D12 (+ live fallback to D14/D17 when `final_result` is empty), D18 `evaluations`, D19 `scores`, D9 `assessment_criteria`, D8 `interview_questions`, D15 `interview_events` (integrity flags)
- **Writes**: D18, D19 (regeneration path only — `_upsert_evaluation`, shared with P2.4)
- **External calls**: Groq (`evaluation_generator.generate_evaluation`, offloaded via `asyncio.to_thread`), Cloudflare R2 (presign)

---

### P3 — Agent Worker (`agent/agent/`, LiveKit Agents SDK, Railway)

The only process that is itself a LiveKit *participant* (not just an API caller). Dispatched automatically by LiveKit Cloud whenever a candidate's room becomes active.

- **Inputs**
  - `room dispatch` — from LiveKit Cloud
  - `SessionLoadResponse` (questions, checkpoint, config) — from P2.4 (`GET /internal/{id}/load`)
  - `candidate audio track` (WebRTC) — from LiveKit Cloud (relayed from Candidate's browser)
  - `candidate data messages` (control events: skip, hint request, code/MCQ submission) — from LiveKit Cloud
- **Outputs**
  - `agent audio track` (synthesized speech) — to LiveKit Cloud → Candidate's browser
  - `checkpoint save` (phase, question_index, hints/followups used, question_records) — to P2.4 (`POST /internal/{id}/checkpoint`)
  - `lease renewal` — to P2.4, on an interval, to prove liveness and prevent another agent instance from taking over
  - `transcript turns` — to P2.4 (persisted as D14 rows as the interview proceeds)
  - `STT request` (candidate audio) — to Groq or Azure Speech (`TTS_PROVIDER`)
  - `TTS request` (agent's next line) — to Groq or Azure Speech
  - `finalize / evaluation submit` (transcript, question_records, technical_submission, criterion_scores) — to P2.4 (`POST /internal/{id}/evaluation`, `POST /internal/{id}/finalize`)
- **Reads**: nothing directly from Postgres — always through P2.4's internal API (this is the deliberate "frozen contract" boundary; the agent never touches the DB directly)
- **Writes**: nothing directly — same reason
- **External calls**: Groq (chat completion for LLM-driven interview control + STT/TTS), Azure Speech (STT/TTS fallback), LiveKit Cloud (RTC media)

---

## 5. End-to-end trace — one full interview (for sanity-checking the above)

1. Candidate opens invite link → **P1** → **P2.3** (`GET /invitations/{token}`) reads D11.
2. Candidate submits OTP → **P2.3** (`POST /redeem`) writes D11, D12; requests a LiveKit token from **P2.4**; returns `RedeemResponse` to **P1**.
3. **P1** joins the LiveKit room directly with that token. LiveKit Cloud dispatches **P3** to the same room.
4. **P3** calls **P2.4** `GET /load` → reads D12/D13/D6/D7/D8, returns question set + config.
5. **P3** conducts the interview: STT (Groq/Azure) → LLM control logic → TTS (Groq/Azure) → LiveKit audio, in a loop. Periodically calls **P2.4** to save checkpoints (D17) and transcript turns (D14), and to renew its lease (D12).
6. Candidate's audio/video is simultaneously recorded by LiveKit Egress into **Cloudflare R2**, started via **P2.4** when the room was first created.
7. Interview ends → **P3** calls **P2.4** `finalize` (D12 → `COMPLETED`, `final_result` JSONB) and `evaluation` (D18/D19, after a Groq call inside P3's own evaluation step or a placeholder if that fails).
8. HR admin opens the result → **P1** → **P2.5** reads D12/D18/D19/D15, presigns the D12.`recording_storage_path` against **Cloudflare R2**, returns `EvaluationDetailResponse`.
