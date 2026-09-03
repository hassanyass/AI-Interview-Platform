# Path2Hire — Current Decisions

Authoritative for Antigravity per AGENTS.md. Anything not listed here as decided is UNRESOLVED — do not assume an answer.

## Confirmed product decisions (from product spec)
| Area | Decision |
|---|---|
| Job fields | Title, description, seniority, required skills, preferred skills, responsibilities, location, candidate instructions, duration |
| Interviews per job | One standardized interview |
| Interview structure | Sections |
| MVP section types | Verbal, Coding, MCQ |
| Technical Q&A | Included inside Verbal |
| Section repetition | Not allowed — each section type once per definition |
| Section ordering | Admin can reorder; Verbal/Introduction suggested first by default |
| Question generation | AI-generated, HR-editable, individually regenerable |
| Candidate configuration | Same interview for all candidates on a Job |
| Candidate results | Individual per session |
| Public access | Supported |
| Personalized access | Supported |
| Bulk candidates | Future capability — not MVP |
| Follow-up limit | Max 2 AI follow-ups per core question, not mandatory |
| Core question integrity | Never skipped/replaced/reordered live |

## P0 — Candidate identity/access (RESOLVED)
**Public link path:** candidate provides name + contact info directly — no password, no OTP, no pre-existing account.
**Personalized invitation path:** candidate enters email, confirms via OTP sent to that email, then proceeds. Status (invited/opened/verified/started/completed) must be visible to Admin.
**Implementation note:** explore whether Supabase's native email OTP (`signInWithOtp`) can cover the personalized path before building a fully custom dual-JWT system — confirm during Transition Phase 3, do not assume the rewrite is required without checking.

## Phase 2 architecture confirmations (RESOLVED)
**Candidate profile identity:** ONE `CandidateProfile` per email, reused across job applications (unified identity) — NOT a new snapshot row per application. Per-application data (resume version, cover note, etc.) belongs on a separate join/application record that references the shared `CandidateProfile`, not on duplicated profile rows. `candidate_profiles.email` unique constraint should be reviewed/dropped only insofar as it currently ties uniqueness to Supabase `auth.users.id` — the email itself should remain the unique identity key for guests.

**Public link modeling:** the public-link access mode is a flag/token directly on `InterviewDefinition` (e.g. `is_public`, `public_access_token`), NOT a row in `InterviewInvitation`. `InterviewInvitation` is reserved strictly for the personalized, per-candidate-email + OTP flow. Do not conflate the two into one table/`access_mode` enum.

**OTP storage:** any OTP code must be stored hashed, with its own expiry and attempt-count columns — never as a plaintext `otp_code` string.

## P1 — Email provider (UNRESOLVED — deferred)
Not yet decided. Does not block Phase 2 or Phase 3. Build the invitation/notification layer provider-agnostic; plug in the concrete provider during Phase 6.

## P2 — Coding section for MVP (RESOLVED)
LLM-evaluated text/pseudo-code submission only. No sandbox execution for MVP.

## UI design pass (RESOLVED — deferred)
Visual/UX design is explicitly deferred to a later dedicated phase. All
frontend work from Phase 5C through Phase 6D (sections/question editor UI,
publish flow UI, invite/apply candidate-facing pages) must be built
**functional and plainly styled only** — reuse whatever base styling/
components already exist, no new design system work, no polish passes.
Do not treat this as license to skip building UI entirely — real, clickable
pages are still required so every flow can be verified end-to-end through
the actual app, not just via scripts. A dedicated future phase will apply
real visual design once all flows are functionally proven.

## Interview language (RESOLVED)
`language` is a Job-level property, set by the Admin during job setup —
NOT a per-candidate choice at invitation/registration time. Options: `en`,
`ar` (matching the legacy engine's existing supported values). One language
per Job; all candidates for that Job interview in that language. This avoids
the unsupported ripple of needing per-language question sets, since AI
question generation is pre-generated once per section per the existing
"AI-generated, HR-editable" decision.

## Follow-up limits per section type (RESOLVED — refined)
- VERBAL: up to 2, time-tier throttled (per Phase 7).
- MCQ: 0 — binary right/wrong, submit and grade. No live interaction during
  answering beyond selecting an option.
- CODING: 0 POST-SUBMISSION follow-ups (no Verbal-style "let me probe your
  answer further" after the candidate submits) — but this is NOT a silent
  submit-and-grade box like MCQ. CODING questions are live problem-solving,
  LeetCode-interview-style: the candidate thinks aloud, the AI is present
  throughout, and the candidate can request hints / discuss their approach
  DURING solving, same as the legacy engine's existing hint mechanism
  (`_provide_hint()` / `REQUEST_HINT`) already does for the single hardcoded
  question — this needs to be ported to the new ordered-question flow, not
  rebuilt from scratch. The AI must not give away the answer outright when
  a hint is requested — graduated hints only.
- CODING evaluation must be partial-credit-aware, not strict pass/fail: a
  candidate with the right approach but imperfect/incomplete pseudocode
  should score meaningfully better than one who's simply wrong. The
  existing excellent/good/adequate/poor eval_criteria rubric (already
  confirmed working in 9A's live generation output) is the right mechanism
  for this — "0 follow-ups" must not be misread as "binary pass/fail
  grading." Confirm this explicitly during 9D's evaluation-logic build.

## Section pacing & waiting room (RESOLVED — new feature, not yet built)
- Waiting room time between sections is FREE/UNCLOCKED — the interview
  clock pauses entirely while a candidate waits there. It is not counted
  against the section that ended or the one about to start.
- Auto-proceed after a timeout (handles an abandoned/AFK session) — exact
  duration TBD, default proposed 5 minutes, must be easily configurable
  (env var, matching this codebase's existing pattern for STT/timing
  constants), not hardcoded.
- Admins set each section's time budget directly. The job's total
  interview duration becomes the SUM of section budgets — there is no
  separate, independently-set overall cap. This means
  Job/InterviewDefinition.duration_minutes changes from an admin-set input
  to a DERIVED/computed value, recalculated whenever a section's budget or
  the set of sections changes. See docs/section-pacing-architecture.md.

## Candidate can end a section early (RESOLVED — partial reversal of an earlier decision)
**This partially reverses the original product spec's "core question
skipping: not allowed" rule and Issue 6's SKIP_SECTION fix — deliberately,
confirmed explicitly with the user, not an oversight.**

- A candidate MAY voluntarily end the CURRENT section early, at any point,
  with a confirmation dialog — moving to the waiting room (or CLOSING if
  it was the last section) with any remaining unanswered questions in that
  section marked not-attempted, not silently dropped from the record.
- What does NOT change: Issue 6's SKIP_QUESTION fix stays exactly as-is —
  a candidate still cannot skip one individual core question while staying
  in the same section. This is a SECTION-level "I'm done, move on"
  affordance, not a return of question-level skipping.
- Implementation should use a new, dedicated control action (e.g.
  END_SECTION_EARLY), distinct from the legacy SKIP_SECTION mechanism
  (which stays disabled for active core sections per Issue 6 — this is a
  new, purpose-built mechanism, not a resurrection of the old one).

## Scoring mechanism upgrade (RESOLVED — partial reopening of Phase 8B)
Phase 8B's fixed-criteria-set decision stays correct and is NOT reversed —
audit confirmed it was a deliberate, well-reasoned choice (LLM category-
attribution inconsistency with open-ended criteria). Two amendments,
resolved 2026-09-01:

1. **Hybrid scoring**: `overall_score` stays exactly as-is — the LLM's
   independent holistic judgment, unchanged. A NEW, separate, genuinely
   computed field is added: a real weighted aggregate of `criterion_scores`,
   computed by code (not the LLM), shown alongside `overall_score` on the
   dashboard, clearly labeled as distinct (e.g. "Holistic Assessment" vs.
   "Criteria-Weighted Score"). Null/insufficient-evidence criterion scores
   must be excluded and weights re-normalized among the scored criteria,
   not treated as zero — matching the existing evidence-sufficiency
   principle from Phase 8B/8D.

2. **Expand the curated set, do not open to free-text**: add a small
   number of additional fixed, curated criteria (proposed and reasoned by
   whoever implements this, reviewed before adding) — still no fully
   custom/HR-authored criteria. Preserves the exact reliability guardrail
   Phase 8B's investigation established.

New requirement not previously scoped: HR needs a way to set a WEIGHT per
enabled criterion (no such field exists anywhere today, confirmed by
audit) — design needed for default weighting, input UI, and how it
interacts with enabled/disabled state.

## Proctoring PR-D scope decision (RESOLVED)
Face/gaze detection (real-time computer-vision signal source) is being
built now, as originally scoped in docs/proctoring-architecture.md - not
deferred. Confirmed 2026-09-01, after PR-B (fullscreen/tab events) and
PR-C (video recording) were both verified working in production first.
This is the third and final signal source; aggregation + dashboard display
(combining all three: fullscreen/tab events, face/gaze signals, and the
video recording for human review) follow once this is built.

## Proctoring aggregation & dashboard display (RESOLVED — Part 1 implemented)
Following a live manual test (2026-09-02) that found fired PR-B/PR-D
signals produced no visible change anywhere in the admin UI, this closes
that gap — docs/proctoring-architecture.md's PR-F ("HR Dashboard
redesign") integrity-timeline scope, built now rather than deferred
further:

1. **Flagging rule — Option A (confirmed)**: ANY integrity event at all
   (`FULLSCREEN_EXITED`, `TAB_HIDDEN`, `WINDOW_BLURRED`, `NO_FACE_DETECTED`,
   `MULTIPLE_FACES_DETECTED`) marks a session `flagged_for_review = true`.
   No severity weighting or count threshold — HR sees the underlying
   evidence and judges it themselves, same philosophy as the scoring
   override rather than a system pre-judging via a threshold.
2. **Per-candidate view** (`CandidateResultPage.tsx`): a new "Integrity
   Timeline" section lists every flagged moment (type, phase, approximate
   video offset); clicking a row seeks the existing recording player to
   that moment rather than duplicating a second video experience.
3. **Per-job view** (`JobResultsPage.tsx`): a "Flagged for Review" stat
   tile plus a per-candidate "Integrity" column, alongside the existing
   suggested/completed counts.
4. **No schema change needed** — this reads the existing `interview_events`
   table (`admin.py`'s `INTEGRITY_EVENT_TYPES` allowlist / `_get_integrity_
   events`); no migration in this pass.

**Explicitly NOT part of this pass** — deferred, not decided against:
head-pose/gaze detection (looking down at a phone with the face still
visible went unflagged in the same manual test). Scoped in discussion but
not approved for building; do not start it without explicit sign-off. Open
questions when it is picked up: `FaceLandmarker` vs. extending
`FaceDetector`, the pitch-angle/duration thresholds, and whether a
per-candidate calibration step is needed to keep the false-positive rate
acceptable across camera angles/lighting.

## Proctoring Part 2 — head-pose detection scope (RESOLVED, build approved)
A second live manual test (2026-09-02) reproduced the exact gap above
(face stayed visible while looking down at a phone) — confirmed as the
known gap, not a regression in Part 1/PR-D. Approved to build now:

- **New event**: `HEAD_DOWN_SUSPECTED`, decomposed from `FaceLandmarker`'s
  `outputFacialTransformationMatrixes` (real, confirmed API —
  `node_modules/@mediapipe/tasks-vision/vision.d.ts`), not
  `FaceDetector`'s face-count-only output.
- **Replaces, not adds to, PR-D's detector**: `FaceLandmarker` can also
  report face count (`faceLandmarks.length`), so it replaces
  `FaceDetector` entirely inside `useFaceDetectionMonitor` rather than
  running two WASM models in the same tab — `NO_FACE_DETECTED`/
  `MULTIPLE_FACES_DETECTED` keep their exact existing behavior, now
  computed from the landmarker's output instead.
- **Phase scope (confirmed, deliberately not narrowed)**: runs during
  every phase the existing `monitoringActive` gate already covers,
  including `CODING` — explicitly considered and rejected narrowing to
  verbal-only phases only, despite the real risk that looking down at a
  keyboard/second reference while coding reads the same as looking down
  at a phone. Revisit if live CODING-phase data shows an unacceptable
  false-positive rate.
- **Thresholds — validate before locking in**: starting proposal is 25°
  downward pitch sustained for 3 consecutive ~4s samples (~12s) — longer
  than face-absence's 2-sample/8s window, since a glance down is far more
  common/benign than disappearing. To be confirmed against real decomposed
  pitch angles logged from an actual test session, same evidence-first
  approach as PR-D's own debounce tuning — not committed as final numbers
  yet.
- **No per-candidate calibration step for v1** — added complexity/UX
  friction deferred unless real testing shows the fixed threshold is
  unusable for some camera angles.
- `controller.py`'s `process_ui_command` allowlist needs one more string
  added (frozen file) — same category of one-line, already-proven-branch
  change as PR-D's two-string addition; requires its own explicit sign-off
  before that specific edit, per AGENTS.md's frozen-contract rule.

**Built (2026-09-02), sign-off obtained, status: calibration pending real
data, not yet a finished/trusted threshold:**
- `face_landmarker.task` fetched and confirmed real (HTTP 200, genuine
  zip-format task bundle, ~3.6MB) from Google's public model storage;
  replaces PR-D's `blaze_face_short_range.tflite` in
  `useFaceDetectionMonitor`, which now derives NO_FACE/MULTIPLE_FACES from
  `FaceLandmarker` too (one detector, not two running side by side).
- Matrix-to-Euler-angle math (`headPose.ts`) verified against
  hand-constructed synthetic rotation matrices for each axis — pitch/yaw/
  roll each cleanly isolate the corresponding pure rotation with correct
  sign, confirming the linear algebra itself is correct.
- **What real-world calibration still owes us**: whether MediaPipe's
  actual matrix layout/axis convention matches the column-major
  assumption `headPose.ts` documents, and which sign of pitch means
  "down" vs. "up" — this sandbox's Browser pane blocks camera access
  (same limitation PR-D hit), so this can only be confirmed via a real
  live test. `useFaceDetectionMonitor.ts` logs every decomposed angle to
  the console (`VITE_HEAD_POSE_DEBUG`, on by default) and the trigger
  condition checks `Math.abs(pitch)` in both directions until that's
  confirmed. Do not treat HEAD_DOWN_SUSPECTED as a calibrated signal until
  a real test confirms the axis/sign and the 25°/3-sample defaults hold up.
- The LiveKit agent worker (`python -m agent.main dev`) does NOT hot-reload
  in dev mode (`in-process auto-reload has been removed`, per its own
  startup warning) — it must be manually restarted to pick up this
  controller.py change before a live test will actually persist
  HEAD_DOWN_SUSPECTED events.

## Results display for non-naturally-completed sessions (RESOLVED, implemented 2026-09-03)
Audit request ("ensure answers are being recorded, scoring works, results
are shown clearly") found a real, confirmed bug, fixed the same day:
`get_candidate_result`'s `transcript`/`question_records`/
`technical_submission` were read ONLY from `InterviewSession.final_result`
— a JSONB snapshot written ONLY by the agent's own natural end-of-
interview path (`build_final_result` -> `save_completion`). Any session
ending a different way (candidate/HR-terminated, the idle-disconnect
sweep, an agent crash) never got that snapshot, even though every
individual turn was already durably persisted in `InterviewMessage` as it
happened. Real DB evidence at the time: 4 real TERMINATED sessions with
1-8 real messages each, all showing an empty transcript on the results
page.

**Fix**: `admin.py`'s `get_candidate_result` now falls back to a live
`InterviewMessage` query for `transcript`, and to the latest
`InterviewCheckpoint` row's `question_records`/`technical_submission`,
whenever `final_result` didn't carry them. Verified against all 4 real
affected sessions post-fix — each now returns its real, previously-hidden
transcript/question_records; a naturally-completed session's
already-correct `final_result` data is unaffected (confirmed unchanged
before/after).

**Separately verified, not a bug**: the scoring mechanism itself
(`internal.py`'s `submit_evaluation`, weighted-score computation) is
correct — proven with a real, direct end-to-end invocation (`overall_score`,
`weighted_score`, and real per-criterion `Score` rows all landing together
correctly in one call; the test write was reverted immediately after).
**Flagged, not fixed (separate, larger scope)**: no retry mechanism exists
today for a session whose `submit_evaluation()` call fails for an
unrelated reason (network blip, backend restart mid-flight) — it's
permanently stuck on the generic placeholder evaluation with no automatic
recovery path.

## Evaluation regeneration for placeholder sessions (RESOLVED — scoped 2026-09-03, not yet built)
Follow-up to the above, scoped in detail with real DB evidence before any
code: **149 of 220 (68%) terminal sessions are stuck on the generic
placeholder evaluation** — 112/112 (100%) of TERMINATED sessions
(structural: `_finalize_live_session` never attempts evaluation at all,
not a flaky failure) and 37/108 (34%) of COMPLETED sessions (genuine
submission failures). 138 of the 149 have real, recoverable transcript
data (via the fix above) a real evaluation could be generated from.

**Confirmed decisions:**
1. **Trigger — on-demand, one session at a time.** An HR-clicked
   "Regenerate Evaluation" button on the candidate result page, not an
   automatic background sweep and not a bulk per-job action. Matches this
   project's existing philosophy (HR judges, the system surfaces evidence
   — same spirit as the scoring override) and avoids background-job
   scheduling/backoff design this project doesn't otherwise have.
2. **TERMINATED sessions ARE eligible** — a real AI evaluation should be
   generated from whatever partial evidence exists (the existing
   `evidence_sufficiency` field already exists precisely to flag this as
   partial), not withheld by session status. Excluding TERMINATED would
   have addressed only 37 of the 149 real cases.

**Design, not yet built**: host evaluation generation in the **backend**,
not the agent — an agent worker only exists transiently per live call, so
there's no idle agent to hand a retroactive job to. Confirmed feasible by
reading `EVALUATOR_PROMPT` directly: it's one self-contained structured
LLM call over a plain JSON evidence blob (role/level/transcript/
question_records/technical_submission/question_eval_criteria/criteria),
nothing LiveKit/voice/agent-specific, and every piece of that evidence is
already backend-accessible. Follows the exact precedent of
`backend/services/question_generator.py` (the existing admin-side AI
question generation), which is explicitly documented as not depending on
agent code — this is the same pattern applied to a second use case, not
new architecture. Plan: a new `evaluation_generator.py` service, a new
`POST .../regenerate-evaluation` endpoint, a small additive
`Evaluation.is_placeholder` boolean (replacing fragile string-matching on
the exact placeholder text) migration, sharing `internal.py`'s existing
weighted-score/upsert logic rather than duplicating it, and a frontend
button gated on `is_placeholder` + real transcript existing.

## Still unresolved (do not implement against these silently)
- Invitation expiration policy
- Whether public candidates need any email verification at all (currently: no, by design)
- Whether candidates can retake an interview
- Publishing vs. draft behavior for InterviewDefinition
- Editing an already-published interview
- Permissions / multiple Admin users
- Email templates (blocked on P1)
