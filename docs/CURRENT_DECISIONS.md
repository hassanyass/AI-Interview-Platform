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
- At the time this was written: Issue 6's SKIP_QUESTION fix stayed exactly
  as-is — a candidate could not skip one individual core question while
  staying in the same section. **This has since changed — see "Candidate
  can skip an individual core question" below, a second, later reversal.**
  This was a SECTION-level "I'm done, move on" affordance, not
  question-level skipping, at the time it was made.
- Implementation should use a new, dedicated control action (e.g.
  END_SECTION_EARLY), distinct from the legacy SKIP_SECTION mechanism
  (which stays disabled for active core sections per Issue 6 — this is a
  new, purpose-built mechanism, not a resurrection of the old one).

## Candidate can skip an individual core question (RESOLVED — second reversal, 2026-08-27)
**This further reverses Issue 6's SKIP_QUESTION fix — deliberately,
confirmed explicitly with the user (asked directly: reword the rejection
message vs. make Skip actually work; user chose "make Skip actually
work"), not an oversight. The section above ("Candidate can end a section
early") already reversed the original spec's section-level skipping; this
extends that same reversal down to the individual question level, which
that earlier decision explicitly still ruled out at the time.**

- `SKIP_QUESTION` now genuinely skips the CURRENT ordered core question
  (any section type — VERBAL/CODING/MCQ) — marks it `SKIPPED` (a distinct
  outcome from `COMPLETED`/`TIME_EXPIRED`/`NOT_ATTEMPTED`, preserving the
  real reason it wasn't answered) and advances to the next question, or
  ends the section/interview exactly the way `SUBMIT_CODE`/
  `SUBMIT_MCQ_ANSWER` already do when it's the last question in a section.
- Scoped narrowly to genuinely-active core questions only (BACKGROUND
  phase, a real `current_question` present) — a `SKIP_QUESTION` sent during
  `BRIEFING`/`WELCOME`, before any core question has actually started, is
  still rejected exactly as Issue 6 originally intended (there's nothing
  concrete yet to skip). That original repro case is unaffected.
- `SKIP_SECTION` stays fully blocked for ordered core sections, unchanged
  — this reversal is per-QUESTION only. `END_SECTION_EARLY` remains the
  one mechanism for "skip the whole section."
- `generate_ui_state()`'s `allowed_controls` now advertises `SKIP_QUESTION`
  again for an active ordered core section (previously stripped, correctly,
  back when it was still a no-op) — `SKIP_SECTION`/`MOVE_TO_TECHNICAL`
  stay stripped there, matching their still-blocked status.

## Intro screen's "end" control (RESOLVED)
The post-registration intro/greeting screen's "end" affordance sends
`END_INTERVIEW` only (its REST equivalent, `POST /interviews/{id}/terminate`,
since no live LiveKit/data-channel session exists yet at that point) —
never `END_SECTION_EARLY`. This is a UI-only choice; no
`state_machine.py`/`controller.py` change was made or needed.

**Low-priority future cleanup, not urgent:** `VALID_CANDIDATE_CONTROLS_PER_PHASE`
in `agent/agent/interview/state_machine.py` still technically permits
`END_SECTION_EARLY` during `BRIEFING`/`WELCOME` (before any core section is
active), and `_handle_end_section_early()` in `controller.py` has real,
intentional-looking handling for that case: it marks the *entire first
section* as `NOT_ATTEMPTED` and jumps to `WAITING_ROOM`/`CLOSING`, rather
than doing nothing. This is currently unreachable — no UI anywhere sends
`END_SECTION_EARLY` pre-section — but the state machine's own gating
doesn't match this doc's "END_SECTION_EARLY requires an active core
section" framing. Worth tightening `VALID_CANDIDATE_CONTROLS_PER_PHASE`
(drop `END_SECTION_EARLY` from `BRIEFING`/`WELCOME`) in a future pass, as a
frozen-file change requiring its own sign-off — not a current risk since
nothing reaches it today.

## Phase 9H blocker (RESOLVED — 2026-08-26)
Was: `generate_ui_state()` only read `ctx.current_question` (legacy flow),
never `core_section.current_question` (Phase 9's ordered-section flow), so
CODING/MCQ questions never reached the frontend's `current_question` field.
Fixed by mirroring `_provide_hint()`'s existing core_section-aware pattern
exactly, plus adding one new `"config"` key carrying the real, un-coerced
`CodingConfig`/`MCQConfig` dict. `build_core_sections()` in `main.py` also
fixed: `coding_required` now reflects the real section type,
`supported_languages` copies directly; `starter_code`/`constraints` stay at
their legacy typed-field defaults on purpose (shape mismatch with
`CodingConfig`'s string fields) — `config` is the real source of truth the
frontend now reads instead. Live-verified with real captured
`state_update` payloads for both a real CODING and a real MCQ question
(see `docs/phase9-architecture.md`'s 9H section for the evidence and exact
diff). `controller.py`/`main.py` changes were reviewed and approved before
being made, per this file's own frozen-contract rule.

## Phase 8C: Recommendation enum values (RESOLVED — deliberate, 2026-08-31)
`agent/agent/interview/models.py`'s new `Recommendation` enum (replacing the
previous unconstrained free-text `recommendation` string) deliberately kept
the existing values verbatim — `"Hire"`, `"Consider / Mixed"`, `"No Hire"` —
including the slightly awkward `"Consider / Mixed"` string, instead of
cleaning them up to something like `CONSIDER`/`NO_HIRE`-style plain enum
names. This was for backward compatibility: `evaluations.recommendation`
(DB), every existing `final_result.evaluation.recommendation` JSONB value,
and `agent/test_skip_regressions.py`'s ~7 `DetailedEvaluation(recommendation=
"Hire", ...)` call sites all already use these exact strings. **Do not "fix"
this cosmetically in a future pass** — renaming the enum values is a breaking
schema/data change (every existing DB row and JSONB blob would need
migrating), not a free cleanup.

## Still unresolved (do not implement against these silently)
- Invitation expiration policy
- Whether public candidates need any email verification at all (currently: no, by design)
- Whether candidates can retake an interview
- Publishing vs. draft behavior for InterviewDefinition
- Editing an already-published interview
- Permissions / multiple Admin users
- Email templates (blocked on P1)
- `voice_adapter.py`'s `start(resume=True)` unconditionally speaks a
  "Welcome back, continuing from {phase}" message with no exclusion for
  `phase === COMPLETED` — nonsensical and audible if a finished session's
  resume path is ever reached (currently avoided by the new dedicated
  `loadedAlreadyCompleted` flag in `InterviewSession.tsx`, which bypasses
  this path entirely for the initial-load case, but the underlying bug in
  `voice_adapter.py` is still real and unfixed). Low priority, frozen
  file, found during Plan 11's flow-audit follow-up.
