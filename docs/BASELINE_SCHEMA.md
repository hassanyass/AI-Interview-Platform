# Baseline Schema Snapshot

This document captures the exact schema and endpoints at the start of Phase 0, before any new B2B tables (Jobs, InterviewDefinitions, etc.) are introduced, as read directly from the SQLAlchemy models and FastAPI routers.

## 1. Database Tables (7)

### `candidate_profiles`
- `id` (UUID, PK)
- `supabase_user_id` (UUID, Unique, Nullable)  # Added in Phase 3
- `full_name` (String)
- `email` (String, Unique)
- `education` (JSONB)
- `years_of_experience` (Integer)
- `skills` (JSONB)
- `programming_languages` (JSONB)
- `frameworks` (JSONB)
- `projects` (JSONB)
- `professional_title` (String)
- `recommended_level` (String)
- `confirmed_level` (String)
- `created_at` (DateTime)
- `updated_at` (DateTime)

### `resumes`
- `id` (UUID, PK)
- `profile_id` (UUID, FK -> `candidate_profiles.id`)
- `original_filename` (String)
- `storage_path` (String)
- `mime_type` (String)
- `file_size` (Integer)
- `extracted_text` (Text)
- `extraction_status` (String)
- `created_at` (DateTime)

### `interview_sessions`
- `id` (UUID, PK)
- `candidate_profile_id` (UUID, FK -> `candidate_profiles.id`)
- `role` (String)
- `level` (String)
- `language` (String)
- `status` (String)
- `created_at` (DateTime)
- `started_at` (DateTime, Nullable)
- `completed_at` (DateTime, Nullable)
- `active_agent_id` (String, Nullable)
- `agent_lease_expires_at` (DateTime, Nullable)
- `final_result` (JSONB, Nullable)

### `interview_configurations`
- `session_id` (UUID, PK, FK -> `interview_sessions.id`)
- `role` (String)
- `level` (String)
- `language` (String)
- `job_description` (Text, Nullable)
- `duration` (Integer)
- `thinking_time` (Integer)
- `configuration_metadata` (JSONB, Nullable)

### `interview_messages`
- `id` (UUID, PK)
- `session_id` (UUID, FK -> `interview_sessions.id`)
- `sequence_number` (Integer)
- `speaker` (String)
- `text` (Text)
- `phase` (String, Nullable)
- `metadata` (JSONB, Nullable)
- `created_at` (DateTime)

### `interview_events`
- `id` (UUID, PK)
- `session_id` (UUID, FK -> `interview_sessions.id`)
- `event_type` (String)
- `phase` (String, Nullable)
- `sequence_number` (Integer)
- `metadata` (JSONB, Nullable)
- `created_at` (DateTime)

### `interview_checkpoints`
- `id` (UUID, PK)
- `session_id` (UUID, FK -> `interview_sessions.id`)
- `schema_version` (Integer)
- `current_phase` (String)
- `current_question_id` (String, Nullable)
- `question_index` (Integer)
- `section` (String, Nullable)
- `hints_used` (Integer)
- `followups_used` (Integer)
- `background_questions_asked` (Integer)
- `competencies_evaluated` (JSONB, Nullable)
- `time_remaining_seconds` (Integer)
- `last_message_sequence` (Integer)
- `last_event_sequence` (Integer)
- `current_question_snapshot` (JSONB, Nullable)
- `section_progress` (JSONB, Nullable)
- `question_records` (JSONB, Nullable)
- `evaluation_signals` (JSONB, Nullable)
- `created_at` (DateTime)

## Phase 2 Additions

### `jobs`
- `id` (UUID, PK)
- `title` (String)
- `location` (String, Nullable)
- `status` (String) # DRAFT, ACTIVE, CLOSED
- `description` (Text)
- `requirements` (Text, Nullable)
- `required_skills` (JSONB)
- `preferred_skills` (JSONB)
- `responsibilities` (JSONB)
- `created_at` (DateTime)
- `updated_at` (DateTime)

### `interview_definitions`
- `id` (UUID, PK)
- `job_id` (UUID, FK -> `jobs.id`)
- `title` (String)
- `instructions` (Text)
- `duration_minutes` (Integer)
- `is_public` (Boolean)
- `public_access_token` (String, Unique, Nullable)
- `created_at` (DateTime)
- `updated_at` (DateTime)

### `interview_sections`
- `id` (UUID, PK)
- `definition_id` (UUID, FK -> `interview_definitions.id`)
- `order_index` (Integer)
- `title` (String)
- `description` (Text, Nullable)
- `time_limit_minutes` (Integer, Nullable)
- `focus_areas` (JSONB, Nullable)
- `created_at` (DateTime)
- `updated_at` (DateTime)

### `interview_questions`
- `id` (UUID, PK)
- `section_id` (UUID, FK -> `interview_sections.id`)
- `order_index` (Integer)
- `text` (Text)
- `expected_points` (JSONB, Nullable)
- `scoring_rubric` (JSONB, Nullable)
- `type` (String)
- `time_limit_minutes` (Integer, Nullable)
- `is_required` (Boolean)
- `created_at` (DateTime)
- `updated_at` (DateTime)

### `job_applications`
- `id` (UUID, PK)
- `job_id` (UUID, FK -> `jobs.id`)
- `candidate_profile_id` (UUID, FK -> `candidate_profiles.id`)
- `resume_id` (UUID, FK -> `resumes.id`, Nullable)
- `status` (String)
- `applied_at` (DateTime)
- `updated_at` (DateTime)

### `interview_invitations`
- `id` (UUID, PK)
- `application_id` (UUID, FK -> `job_applications.id`)
- `definition_id` (UUID, FK -> `interview_definitions.id`)
- `token` (String, Unique)
- `status` (String)
- `expires_at` (DateTime, Nullable)
- `created_at` (DateTime)
- `updated_at` (DateTime)

### `users_roles`
- `id` (UUID, PK)
- `user_id` (UUID, Supabase Auth ID)
- `role` (String)
- `created_at` (DateTime)

## Phase 8C Additions

### `assessment_criteria`
- `id` (UUID, PK)
- `job_id` (UUID, FK -> `jobs.id`, Nullable — NULL together with `section_id` = system TEMPLATE row)
- `section_id` (UUID, FK -> `interview_sections.id`, Nullable)
- `key` (String)
- `label` (String)
- `kind` (String) # "behavioral" | "content"
- `enabled` (Boolean, default True)
- `guidance_text` (Text, Nullable)
- `source` (String, default "CUSTOM") # "TEMPLATE" | "CUSTOM"
- `created_at` (DateTime)
- Unique: `(job_id, section_id, key)`; partial unique index on `key` where `job_id IS NULL AND section_id IS NULL` (the template tier)
- Seeded with 5 TEMPLATE rows (behavioral): `clarity_of_thought`, `organization_structure`, `communication`, `confidence_composure`, `professionalism`

### `evaluations`
- `id` (UUID, PK)
- `session_id` (UUID, FK -> `interview_sessions.id`, Unique — one per session)
- `overall_score` (Integer, Nullable)
- `recommendation` (String, Nullable) # "Hire" | "Consider / Mixed" | "No Hire"
- `evidence_sufficiency` (Float, Nullable)
- `summary` (Text, Nullable)
- `detailed_overview` (Text, Nullable)
- `created_at` (DateTime)
- `updated_at` (DateTime, Nullable)
- Additive only — `interview_sessions.final_result` (JSONB) is untouched and stays the sole record for every pre-8C session (no backfill).

### `scores`
- `id` (UUID, PK)
- `evaluation_id` (UUID, FK -> `evaluations.id`)
- `criterion_id` (UUID, FK -> `assessment_criteria.id`, Nullable, `SET NULL` on delete)
- `criterion_key` (String — denormalized, durable even if the criterion is later edited/deleted)
- `score` (Integer, Nullable)
- `overview` (Text, Nullable)
- `strengths` (JSONB, Nullable)
- `improvements` (JSONB, Nullable)
- `evidence_reference` (Text, Nullable)

---

## 2. API Routes

**Resumes (`/resumes`)**
- `POST /`
- `GET /`

**Profiles (`/profiles`)**
- `POST /`
- `GET /me`
- `PATCH /me`

**Interviews (`/interviews`)**
- `POST /`
- `POST /public/register`
- `GET /`
- `GET /{session_id}`
- `POST /{session_id}/terminate`
- `GET /{session_id}/transcript`
- `GET /{session_id}/events`
- `GET /{session_id}/result`

**Admin (`/admin`)**
- `GET /ping`
- *(Phases 4/5/9G's Job/Section/Question CRUD routes predate this doc's last update and aren't listed here — pre-existing staleness, not touched by this pass.)*
- `GET /interviews/{session_id}/result` — Phase 8D. Per-candidate detailed result: legacy `final_result` JSONB (transcript/question_records/technical_submission) + normalized `Evaluation`/`Score` rows in one response. `409` if the session has no `Evaluation` row yet (distinct from `404` if the session itself doesn't exist). Admin-only; does not touch `GET /interviews/{id}/result`'s existing candidate-access lockdown (Plan 11B).
- `GET /jobs/{job_id}/results` — Phase 8D. Per-job aggregate stats (`total_candidates`, `completed_count`, `in_progress_count`, `suggested_count`) + per-candidate list, joined from `InterviewSession`/`Evaluation`/`CandidateProfile`. `suggested` is computed per-request from `settings.SUGGESTED_EVIDENCE_SUFFICIENCY_FLOOR` (env var, default `0.5`), not stored.

**LiveKit (`/livekit`)**
- `POST /token`

**Internal Agent API (`/internal/interviews`)**
- `GET /{session_id}/load`
- `POST /{session_id}/renew-lease`
- `PATCH /{session_id}/status`
- `POST /{session_id}/messages`
- `POST /{session_id}/events`
- `POST /{session_id}/checkpoints`
- `POST /{session_id}/evaluation` — Phase 8C. Upserts the normalized `Evaluation`/`Score` rows for a session (idempotent on `session_id`).

---

## 3. Agent Load Contract
Currently, `agent/agent/main.py` reads from `GET /internal/interviews/{session_id}/load` to populate the `InterviewRuntimeContext`: it consumes session identity/configuration (`role`, `level`, `language`, `duration_minutes`, `candidate_profile`, `job_description`), the `latest_checkpoint` (to restore `current_phase`, `section_progress`, `question_records`, `current_question_snapshot`, and timer/sequence state), and `recent_messages` (to restore the `conversation_history` array). Phase 8C added `criteria` (resolved `AssessmentCriterion` rows for the session's `job_id` — job-scoped enabled rows if any exist, else the enabled TEMPLATE tier as an interim default) into `InterviewRuntimeContext.criteria`, consumed by `generate_final_evaluation()`.
