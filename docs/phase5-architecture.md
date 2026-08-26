# Transition Phase 5 — HR Frontend (Admin Panel)
## Architecture, Flow, and Sub-Phase Execution Plan

This document is authoritative for Phase 5's structure and flow. It exists so
Antigravity does not need to re-derive decisions already made, and does not
explore/guess at things that should instead be verified once and reused.
Reference this file directly in every Phase 5 prompt.

---

## 0. One-time setup: snapshot the real Phase 4 API contract

Before ANY sub-phase below, run this once and never repeat it:

> Read backend/backend/api/endpoints/admin.py and
> backend/backend/schemas/admin.py IN FULL (the real, current files — Phase 4
> may have implemented details slightly differently than its plan). Create
> docs/PHASE4_API_CONTRACT.md listing: every admin endpoint (method, path,
> request body shape, response shape, status codes for error cases like 403/
> 409/422), exactly as they exist in code. This file becomes the single
> reference for all Phase 5 sub-phases — they should read THIS file, not
> re-read admin.py/schemas/admin.py every time.

This is the single biggest token-saver for this phase: every sub-phase below
reads `docs/PHASE4_API_CONTRACT.md` instead of re-exploring the backend.

---

## 1. Scope recap
Job creation form, section config UI (add/reorder/enforce uniqueness), AI
question review/editor UI, publish flow, and role-aware routing so HR and
candidate views don't collide. No backend changes except the one explicit
exception noted in Sub-phase 5A.

## 2. Off-limits for this entire phase
- `backend/backend/api/endpoints/admin.py`, `schemas/admin.py`,
  `services/question_generator.py` — consume only, do not modify.
- `agent/agent/interview/controller.py`, anything under `/internal/*` —
  frozen until Phase 7.
- Any existing candidate-facing page/component still used by the legacy
  flow (candidates on old sessions still need these to work until Phase 10).
- `InterviewerCharacter.tsx` — untouched.

## 3. Directory & routing architecture (target shape)
```
frontend/src/
  context/
    RoleContext.tsx          [NEW]
  routes/
    admin/
      AdminLayout.tsx         [NEW] — nav shell, role-guarded
      JobsListPage.tsx        [NEW] — GET /admin/jobs
      JobCreatePage.tsx       [NEW] — POST /admin/jobs
      JobDetailPage.tsx       [NEW] — houses SectionsEditor + QuestionEditor
      SectionsEditor.tsx      [NEW]
      QuestionEditor.tsx      [NEW]
  api/
    adminClient.ts            [NEW] — thin wrapper over PHASE4_API_CONTRACT.md endpoints
```
Do not invent additional top-level admin pages beyond this list without
flagging it first — if a sub-phase reveals a real need for one, name it
explicitly in that sub-phase's plan rather than adding silently.

## 4. Role determination (decide, don't assume)
Before Sub-phase 5A, explicitly answer: how does the frontend know a logged-in
user is an Admin?
- **Preferred approach:** attempt a lightweight admin-only GET (e.g.
  `GET /admin/jobs`) on app load; a 200 means admin, a 403 means candidate.
  No new backend endpoint required.
- If this doesn't work cleanly in practice (e.g. because of how errors are
  surfaced), the alternative is a small new `GET /admin/me` endpoint — but
  this is a backend change, so it must be flagged and confirmed before
  building, not added silently.
State which approach was used in the Sub-phase 5A plan.

## 5. Sub-phases (execute and verify each before starting the next)

### 5A — Foundation: role-aware routing shell
- `RoleContext.tsx`, `AdminLayout.tsx`, route guards per section 4 above.
- Before writing any component, check whether the frontend already has a
  test runner configured (vitest/jest/testing-library in package.json) —
  report what you find; don't assume either way.
- **Stop condition:** an admin-role test user sees an empty admin shell with
  nav; a candidate-role user is redirected/blocked from `/admin/*`. Verify
  this manually or via test if tooling exists. Report before continuing.

### 5B — Job creation & list
- `JobsListPage.tsx`, `JobCreatePage.tsx`.
- Form fields: exactly the 9 fields from `docs/CURRENT_DECISIONS.md` (title,
  description, seniority, required_skills, preferred_skills, responsibilities,
  location, candidate_instructions, duration). Check `PHASE4_API_CONTRACT.md`
  for whether skills/responsibilities are arrays or strings in the real
  schema — build the form to match exactly, don't assume.
- **Stop condition:** creating a job via the UI produces a real row
  (confirm via `GET /admin/jobs`), with its nested `definition` object
  present in the response per Phase 4's contract.

### 5C — Section configuration UI
- On `JobDetailPage.tsx`: add Verbal/Coding/MCQ sections (enforce one each,
  matching the backend's own uniqueness constraint — UI should prevent it,
  but don't rely on UI alone since the backend already enforces it at the DB
  level), reorder them.
- **Dependency decision required:** check `frontend/package.json` for any
  existing drag-and-drop library before adding one. If none exists, default
  to simple up/down arrow-button reordering (no new dependency) rather than
  introducing a drag-and-drop library — flag if you believe a real drag
  library is warranted instead, and wait for confirmation before adding a
  new dependency.
- **Stop condition:** sections can be added, reordered, and a second
  attempt at the same section type is rejected (both by UI and by hitting
  the real backend constraint).

### 5D — Question review/editor
- Trigger AI generation per section, list generated questions, and wire
  edit/replace/delete/regenerate/add-manual actions to their respective
  Phase 4 endpoints from `PHASE4_API_CONTRACT.md`.
- **Stop condition:** a full loop works — generate, edit one question,
  delete one, regenerate one, add one manually — verified against the real
  backend (not mocked).

### 5E — Publish flow
- Publish button: `PATCH` job status DRAFT→PUBLISHED. After publish, all
  structural edit UI (add/edit/delete section or question) becomes disabled
  in the UI, reflecting the backend's 409 enforcement from Phase 4.
- Add a confirmation dialog before publishing (irreversible per Phase 4's
  rules — no un-publish exists yet).
- **Stop condition:** publishing a job blocks further structural edits in
  both UI and backend; attempting one via direct API call still correctly
  returns 409 (this proves the frontend isn't the only thing preventing it).

## 6. What "done" looks like for Phase 5
An HR user can, entirely through the UI: create a job → add and order
sections → generate and edit questions → publish. Every step calls the real
Phase 4 backend, nothing is mocked in the final state.
