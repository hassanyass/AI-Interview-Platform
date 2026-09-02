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

## Still unresolved (do not implement against these silently)
- Invitation expiration policy
- Whether public candidates need any email verification at all (currently: no, by design)
- Whether candidates can retake an interview
- Publishing vs. draft behavior for InterviewDefinition
- Editing an already-published interview
- Permissions / multiple Admin users
- Email templates (blocked on P1)
