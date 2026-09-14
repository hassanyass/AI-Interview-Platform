# Backend & Agent Flow Audit — Full Session Lifecycle

Not a numbered phase — a verification pass. Scope: confirm every stage of
the candidate journey works correctly on the BACKEND/AGENT side, and that
what it actually sends matches what the (confirmed-working) frontend
actually expects. No frontend changes. Frontend is confirmed working by
the user's own manual testing — this audit exists to verify the backend
side is genuinely solid underneath it, not to duplicate that testing.

## Verification standard for this audit
Live, real evidence — real DB, real backend, real agent worker, real data
channel — same standard as every high-stakes verification this project has
required (WR-C, Issue 6, the generate_ui_state fix). This is NOT the same
as "automated testing" in the CI/pytest sense: do not run the pytest
suite, do not write new permanent test files. DO drive real API calls and
a real agent worker to observe real behavior — that distinction matters,
don't collapse the two into "skip verification entirely."

## Full flow to verify, stage by stage

### 1. Job publish (re-confirm post-Plan-11)
A job with VERBAL + CODING + MCQ sections, real questions, real time
budgets, publishes successfully with no stopgap (already proven in Phase
9's own verification — just reconfirm nothing since then broke it).

### 2. Candidate obtains the link
`GET /apply/{token}` and `GET /invitations/{token}` — confirm real,
current response shape against what `ApplyPage.tsx`/`InvitePage.tsx`
actually read (field names, especially anything touched since — e.g.
`candidate_instructions`).

### 3. Registration
Guest: `POST /apply/{token}/register`. Personalized: OTP redeem flow.
Confirm real `CandidateProfile`/`JobApplication`/`InterviewSession` rows
created correctly, `job_id`/`definition_id`/`application_id` all set.

### 4. Intro screen's data contract
`GET /interviews/{id}` — confirm the REAL current response shape
(including Plan 11's new `candidate_name` field and `session.status`)
matches exactly what `IntroScreen.tsx`/`InterviewWorkspace.tsx` actually
read. This is the single most likely place for silent drift, since it was
just modified.

### 5. Session start → `/load`
`POST /livekit/token` → agent dispatched → `/internal/interviews/{id}/load`.
Confirm the real payload: `job_description`, `duration_minutes`,
`sections` (ordered, real `config` per CODING/MCQ, `time_budget_minutes`),
candidate profile data. Confirm `build_core_sections()` populates
`context.sections` correctly from this real payload.

### 6. Live section walk — the actual frontend-contract check
For each section type, confirm the REAL data-channel state payload
(`generate_ui_state()`'s output) matches EXACTLY what `VerbalSectionView`/
`CodingSectionView`/`McqSectionView` each read — field names, types,
`config` shape. This is the most important check in this whole audit:
confirm no drift between what the backend emits and what the frontend
components actually destructure, for all three types.

### 7. Section completion → waiting room → next section
Confirm `WAITING_ROOM` entry, correct next-section info broadcast, correct
clock reseed via `PROCEED_TO_NEXT_SECTION`, and the auto-timeout firing
correctly.

### 8. Guard regression check
Confirm `SKIP_QUESTION`/`SKIP_SECTION`/`MOVE_TO_TECHNICAL` are still
correctly blocked mid-core-section (Issue 6's fix), and
`END_SECTION_EARLY` still works as the one legitimate way to end a section
voluntarily.

### 9. Final section → CLOSING → COMPLETED
Confirm the real `DetailedEvaluation`/`final_result` generates and
persists correctly for a session with mixed VERBAL/CODING/MCQ questions
(per-type `eval_criteria` shapes), and `session.status` genuinely becomes
`COMPLETED` in the DB.

### 10. Result access lockdown (Plan 11's fix)
Confirm `GET /interviews/{id}/result` genuinely rejects a candidate/guest
token now and genuinely succeeds for an admin token, with real evidence
(not just reading the code — call it both ways for real).

### 11. Resume/reconnect at every stage
Mid-section, in `WAITING_ROOM`, and post-`COMPLETED` (the exact case Plan
11 fixed) — confirm each resumes correctly with real evidence, not just
"the code looks right."

### 12. Full contract drift check
Enumerate every field each frontend component actually reads from a
backend response or state payload (`IntroScreen`, `InterviewWorkspace`,
the three section views, `WaitingRoomScreen`, the closing screen) and
cross-check each against real current backend code. Flag ANY mismatch —
renamed field on one side, optional/required mismatch, type mismatch —
even if it happens to work today by coincidence (e.g. both sides
defaulting to the same falsy value).

## Report format
Per stage: ✅ confirmed with real evidence / ⚠️ found a real gap (describe
it precisely, don't fix yet) / — not yet checked. Do not mark anything ✅
without having actually driven it live and observed the real result.
