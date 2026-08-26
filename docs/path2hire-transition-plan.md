# Path2Hire — B2C → B2B Transition Plan
### Phased Scope + Anti-Hallucination Playbook for Antigravity-Assisted Development

Source of truth for this plan: `PATH2HIRE — TRANSITION READINESS & ARCHITECTURE AUDIT` and `Path2Hire — Transformation Flow` (Confirmed Decisions, Verbal AI Follow-Up spec). Nothing here overrides those docs — it sequences and bounds them.

---

## Part A — Why an AI coding agent hallucinates on THIS codebase specifically

Three structural facts make Path2Hire unusually easy to hallucinate on:

1. **A monolithic JSONB blob (`final_result`) and a 1:1 coupling (`InterviewConfiguration` ↔ `InterviewSession`)** — an agent asked to "add jobs" will often take the shortcut of stuffing new concepts into the existing JSONB rather than doing the real relational work, because that's the path of least resistance in the code it sees.
2. **A frozen, working Agent Worker contract** (`/internal/interviews/{id}/load`) that the LiveKit background worker depends on. This is not visible from the frontend or admin work you'll be doing in most phases, so an agent can break it without you noticing until a live interview fails.
3. **A long list of explicitly "Not Yet Decided" items** (Section 16 of doc 2). An agent under time pressure will *invent* an answer to these (e.g., decide candidates need password accounts) rather than flag them. That invented answer then becomes silently load-bearing in the schema.

### Guardrails to apply on every task, in every phase

| Guardrail | How to enforce it in Antigravity |
|---|---|
| **Ground truth doc lives in-repo** | Create `docs/CURRENT_DECISIONS.md` in your repo mirroring the Confirmed Decisions tables from doc 2. Reference this file explicitly in every prompt instead of re-explaining the product verbally — agents drift less when pointed at a static file than when given a paraphrase. |
| **Freeze naming** | Use exactly the names in the Current→Target Mapping table (`InterviewDefinition`, `CandidateInterviewSession`, `InterviewQuestion`, `Evaluation`). Tell the agent explicitly: "do not rename or introduce synonyms for these entities." |
| **Read-before-write** | For any task touching an existing model, require the agent to open and quote the actual current class/fields before proposing a diff. Don't let it "recall" the schema from a prior message — files may have been edited since. |
| **No unresolved decisions during implementation** | Before starting a phase, check it against Section 16 ("Not Yet Decided"). If a phase depends on one of those, resolve it explicitly first (Phase 1 below) — don't let the agent pick a default silently. |
| **Additive-only migrations** | Per the audit's own Phase 1–4 strategy: new tables and nullable FKs first, never a destructive rewrite of `interview_sessions` in one step. Reject any agent-proposed migration that drops/renames a column in the same PR that adds a feature. |
| **Contract isolation for the Agent Worker** | Anything touching `/internal/*` or `agent/app/interview/controller.py` gets its own reviewed diff, checked line-by-line against what the LiveKit worker actually consumes. Never bundle this with frontend or admin-API work. |
| **Plan before code** | For any task marked "higher risk" below, ask the agent to output the migration/model diff *as text* first, get your sign-off, then implement — don't let single-shot generation touch coupled tables. |
| **Verification gate per phase** | Each phase below has a "Definition of Done." Don't start the next phase until it's met — this is what stops compounding drift across a long agentic session. |

---

## Part B — Phased Plan

### Phase 0 — Stabilize & Groundwork *(no product behavior change)*
**Scope:**
- Fix the `app.core` module-path collision between `/backend/app` and `/agent/app` (flagged as HIGH technical debt in the audit).
- Get the existing test suite passing.
- Create `docs/CURRENT_DECISIONS.md` and `docs/BASELINE_SCHEMA.md` (snapshot today's 7 tables + API list) so every later phase has a diffable reference.

**Do not touch:** any model, any endpoint behavior.
**Definition of Done:** tests green; two reference docs exist in repo.
**Why first:** an agent working around import collisions will "fix" them differently in different sessions if you let this linger — it's a hallucination multiplier for everything after it.

---

### Phase 1 — Decision Lock *(no coding — product/you decide)*
Resolve these before any schema work, because they determine table shape:

- **P0** — Can candidates take an interview fully anonymously via link, or must they hold a Supabase Auth account? (Determines `Candidate` table design.)
- **P1** — Email provider (Resend / SendGrid / other) for invitations.
- **P2** — Is a real code-execution sandbox in scope for MVP Coding section, or LLM-evaluated pseudo-code only?

Also worth locking now since Phase 2 schema touches them: publishing vs. draft state, whether a published interview can be edited, single vs. multi-admin permissions.

**Deliverable:** answers recorded in `CURRENT_DECISIONS.md`. **Instruct the agent explicitly not to assume answers to any item still marked unresolved in that file.**

---

### Phase 2 — DB Schema Additions (additive only)
**Scope:**
- New tables: `Job`, `InterviewDefinition`, `InterviewSection`, `InterviewQuestion`, `users_roles` (or Supabase custom claim).
- Add nullable `job_id`, `definition_id` to `InterviewSession`.
- **Do not** drop or modify `InterviewConfiguration` yet — it must keep serving legacy sessions.

**Do not touch:** `controller.py`, `/internal/*` endpoints, frontend.
**Definition of Done:** legacy candidate flow still works end-to-end unchanged; new tables exist and are empty/unused in production paths.
**Guardrail:** this is the phase most likely to tempt an agent to "just reuse `InterviewConfiguration`'s JSON shape" for the new tables — explicitly reject that; the whole point is normalization (Section 25 of the audit).

---

### Phase 3 — RBAC / Auth
**Scope:**
- JWT custom claim or `users_roles` table distinguishing `admin` vs `candidate`.
- `Depends(require_admin)` on new admin routes (none exist yet — this phase just builds the dependency and tests it against a stub route).

**Definition of Done:** a stub `/admin/ping` route rejects non-admins; existing candidate routes unaffected.
**New test requirement (per audit §31):** candidate A cannot read candidate B's session; non-admin cannot hit admin routes.

---

### Phase 4 — Admin API: Job & Question Builder (backend only)
**Scope:**
- `/admin/jobs` (CRUD), `/admin/interviews` (definitions), `/admin/sections`, `/admin/questions`.
- AI question-generation endpoint: input = job info + seniority + skills + responsibilities + section config (exactly the context list in doc 2 §8) → output = draft `InterviewQuestion` rows.
- Editor-mode endpoints: edit / replace / delete / regenerate-one / add-manual (doc 2 §9).
- Enforce **section uniqueness** (Verbal/Coding/MCQ each appear at most once per definition) and **ordering** at the API layer, not just the frontend.

**No frontend yet.** Test via API client/Postman/pytest.
**Definition of Done:** an admin can, purely via API calls, create a job → generate questions → edit them → have a persisted, ordered `InterviewDefinition` with unique section types.

---

### Phase 5 — HR Frontend (Admin Panel)
**Scope:**
- Job creation form (fields from doc 2 §3).
- Section configuration UI: add/remove Verbal/Coding/MCQ, drag-reorder, default-order suggestion (Verbal first).
- AI question review/editor UI (edit, delete, regenerate, add).
- Publish action.
- New Role-context in frontend routing (Admin vs Candidate views), replacing `Dashboard.tsx`.

**Reuse:** `InterviewerCharacter.tsx` untouched — it belongs to Phase 7's candidate-facing side, not here.
**Definition of Done:** an HR user can complete the full create→configure→generate→review→publish flow in the UI, hitting Phase 4's real backend.

---

### Phase 6 — Invitation System
**Scope:**
- Public link flow: candidate opens link → provides email + CV → starts interview.
- Personalized flow: admin enters candidate email → Path2Hire sends invitation automatically (no manual URL copying, per doc 2 §11) → candidate opens → accesses interview.
- Candidate identity model resolved per Phase 1's P0 decision (this is exactly why P0 had to be locked first).
- `/invite/:token` public route (frontend), invitation table + expiry (finalize expiry policy here if not already decided).

**Definition of Done:** both public and personalized candidate entry paths reach a real `CandidateInterviewSession` tied to the correct `InterviewDefinition`.
**Explicitly out of scope here:** bulk invitations (100 candidates at once) — doc 2 §12 marks this a future capability; don't let the agent build it "while it's at it," since it changes the invitation data model.

---

### Phase 7 — Agent/Engine Context Injection *(highest risk — treat as its own mini-project)*
**Scope:**
- Modify `/internal/.../load` to serve the *approved* `InterviewQuestion` rows from the matched `InterviewDefinition`, instead of the agent generating questions live.
- Modify `agent/app/interview/controller.py` to consume `InterviewQuestions` from `InterviewRuntimeContext` rather than calling `planner.py`/`question_generator.py`.
- Implement the follow-up state machine exactly as specified in doc 2 (§4–§12 of the Verbal AI Follow-Up spec):
  - max 2 AI follow-ups per core question,
  - follow-ups must stay on the current competency,
  - core questions can never be skipped/replaced/reordered live,
  - time-awareness throttling (normal → up to 2 follow-ups; limited → 0–1; very limited → skip straight to next core question).
- **Mitigation required by the audit (§34):** build a legacy-format adapter so the `/load` payload shape the Agent Worker expects doesn't change even though the underlying data model did.

**Guardrail:** run this against a duplicated/staging LiveKit room first. Any change here that goes wrong fails silently mid-interview, not at build time — manual review of the adapter against `controller.py`'s actual consumption is mandatory, not optional.
**Definition of Done:** a candidate session running through the new pipeline produces the same conversational behavior as legacy, but sourced from HR-approved questions instead of live generation.

---

### Phase 8 — Results Normalization
**Scope:**
- Replace `final_result` JSONB with normalized `Evaluation` / `Score` tables (per candidate, per section, per question where relevant).
- Backfill/migrate historical sessions' JSON into the new tables (or leave legacy read-only via the old field — decide explicitly, don't let the agent silently choose).
- Build the HR-facing comparison/ranking view (candidates within one Job, sortable/filterable).

**Definition of Done:** HR dashboard can list and sort candidates for a given Job by score, with individual transcripts still viewable per candidate.

---

### Phase 9 — Coding & MCQ Sections
**Scope:** these are **currently unimplemented** per the audit (§14–15) — this is genuinely new build, not migration.
- Coding: candidate environment + evaluation flow. Scope depends entirely on Phase 1's P2 decision (real sandbox like Judge0/Docker vs. continued LLM evaluation of submitted text).
- MCQ: question type, answer capture, auto-grading.

**Definition of Done:** both section types are selectable in the Phase 5 UI, executable by a candidate, and produce scoreable results feeding Phase 8's tables.

---

### Phase 10 — Cutover & Deprecation
**Scope:**
- Make `definition_id` mandatory on `InterviewSession`.
- Drop `InterviewConfiguration` and the candidate self-serve `/interviews/new` endpoint.
- Remove any legacy-format adapter from Phase 7 once nothing depends on it.

**Definition of Done:** system is B2B-only; no code path can create an interview without going through a Job → Definition → Invitation.

---

## Part C — Quick-reference: what NOT to let the agent touch, per phase

| Phase | Off-limits |
|---|---|
| 0 | Any schema, any endpoint behavior |
| 2 | `controller.py`, `/internal/*`, frontend, dropping `InterviewConfiguration` |
| 3 | Any existing candidate-facing route's behavior |
| 4 | Frontend, `agent/app/*` |
| 5 | Backend logic beyond wiring to Phase 4 endpoints |
| 6 | Bulk-invitation data model (future scope) |
| 7 | Anything outside `controller.py` + `/internal/load` + its adapter |
| 8 | Live interview engine / state machine |
| 9 | Scope creep beyond what Phase 1's P2 decided |
| 10 | Don't run until Phases 2–9 are all verified in production for a full cycle |

---

## Part D — One habit that will save you the most debugging time

At the start of each Antigravity session, paste in:
1. The specific section of this plan you're working on (not the whole doc).
2. The current, actual content of the specific files being touched (have the agent `cat`/open them, don't paraphrase from memory).
3. The relevant row(s) of `CURRENT_DECISIONS.md`.

This keeps the agent's context anchored to what's real in your repo *today*, rather than to its own prior summary of the codebase, which is where drift and hallucination compound over a long build.
