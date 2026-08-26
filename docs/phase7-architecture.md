# Transition Phase 7 — Agent Context Injection
## Sub-Phase Breakdown (post-exploration)

This supersedes the original transition plan's single-unit description of
Phase 7. The exploration report (session of [date TBD when committed]) found
the actual scope is substantially larger than "swap the question source" —
see docs/PROJECT_STATUS.md for the summary. This document splits the real
work into reviewable sub-phases, matching the pattern used for Phases 5/6.

## Reconstructed spec (the missing "Verbal AI Follow-Up" document)
This was never committed to the repo — only pasted into chat early in the
project. Reconstructing the load-bearing rules here so they have a real home:

- Core questions (from InterviewQuestion, HR-approved) are mandatory: never
  skipped, replaced, or reordered live, regardless of how the conversation
  flows.
- AI follow-ups are conversational probes around the CURRENT core question
  only — max 2 per core question, not mandatory (LLM decides if 0, 1, or 2
  are actually needed based on answer completeness).
- Follow-ups must stay relevant to the current question's competency —
  clarify, elaborate, request an example, probe reasoning. Must not
  introduce unrelated topics (e.g. salary questions during a technical
  probe).
- A candidate's answer to one question may surface info relevant to a LATER
  core question — that information can be recorded, but the later question
  must still be explicitly asked. No auto-completing future questions.
- Time-awareness: three tiers, exact thresholds NOT specified anywhere
  precise (only "normal / limited / very limited" naming) — normal: up to 2
  follow-ups; limited: prefer 0-1; very limited: skip straight to next core
  question. Exact remaining-time cutoffs for each tier need to be decided
  during 7B, informed by what already exists (today's 180s/120s binary
  cutoffs are a reasonable starting anchor, not a given).
- Interview engine (state machine), not the LLM, controls actual
  progression — the LLM proposes, the deterministic code enforces.

## Sub-phases

### 7A — Schema bridge: what InterviewQuestion needs to actually carry
Before any runtime work, resolve the field-mapping gaps the exploration
found. For each missing field (difficulty, expected_concepts, hints,
follow_up_topics, time_budget_minutes): decide per-field whether it (a)
can be derived from existing eval_criteria JSONB with a defined shape, (b)
needs a new column, or (c) isn't needed for verbal-section MVP and can be
deferred (coding-specific fields almost certainly fall here, given Phase 9
is unbuilt). Explore eval_criteria's actual current shape (what does Phase
4's AI generation actually put in it today?) before deciding — don't assume
it's empty. Output: a finalized InterviewQuestion → runtime Question mapping
table, and any additive migration needed.

### 7B — Runtime model: N ordered questions per section
Extend InterviewRuntimeContext/SectionProgress to track "current position in
an ordered, pre-approved question list" per section, replacing the
hardcoded target_questions=max_questions=1 assumption. This is the
structural change enabling everything else. Decide the exact time-tier
thresholds here (informed by, not bound by, today's 180s/120s cutoffs).

### 7C — Deterministic follow-up enforcement
Make the follow-up cap (max 2) an actual enforced check against
context.followups_used before allowing another FOLLOW_UP action, rather
than advisory-only prompt text. Wire in the time-tier throttle from 7B.

### 7D — /load pipeline: Job/Definition/Section/Question → SessionLoadResponse
Build the actual new payload path: session's job_id/definition_id ->
sections -> ordered questions -> mapped via 7A's table into the shape 7B's
runtime model expects. This is the genuinely new "source" the original plan
described — now correctly sequenced after the model can actually hold what
it delivers.

**Open item carried in from 7C, must be resolved here, not discovered mid-
implementation:** 7C reuses the existing `BACKGROUND` phase for the ordered
Verbal question walk rather than introducing a new phase value. 7D must
explicitly decide and state what phase the interview transitions to once
that walk completes — likely requires a `state_machine.py` VALID_TRANSITIONS
change to go straight to CLOSING, skipping TECHNICAL_INTRO/TECHNICAL/CODING
for B2B sessions. Not resolved in 7C on purpose.

### 7E — Legacy adapter
Per the original plan's migration-risk mitigation: ensure sessions still on
the legacy InterviewConfiguration path continue working unchanged. Given
7B's structural change, re-verify this adapter requirement against the NEW
runtime model, not just the original single-question one.

### 7F — Integration verification
End-to-end: a real HR-approved 3-question Verbal section, run through a
full simulated interview via agent/auto_test.py or equivalent, confirming
question order enforcement, follow-up cap enforcement, time-tier behavior,
and correct final transcript/evaluation persistence.

**Provisional value to sanity-check here, not just carry forward:** 7B's
`TimeTierThresholds.normal_min_seconds = 300` was sized by estimate (2
follow-up round-trips at ~60-90s each, plus buffer), not measured. 7F must
confirm it against a real timed run before it's treated as final — don't let
it become silently load-bearing on the strength of the 7B estimate alone.

**Required test scenarios, added after 7C/7D shipped (not originally
scoped, found to be real gaps):**
- **Adversarial first-turn skip — FIXED as a small addendum before 7F, not
  deferred into it.** `OrderedSectionProgress` gained `current_question_asked:
  bool`, set True only when an ASK action actually lands for the current
  core question, reset False on advance. `_should_allow_transition()`'s
  core-question branch now gates on that flag instead of returning `True`
  unconditionally; a premature TRANSITION is downgraded to ASK with the
  real question text substituted in (`_question_problem_text`), not
  whatever text the LLM generated for the rejected attempt. A question that
  reaches `_advance_core_question()` still unasked (only reachable via
  `_must_force_transition()`'s time-pressure override now) is recorded as
  `TIME_EXPIRED`, not `COMPLETED`. Regression test:
  `test_adversarial_first_turn_transition_cannot_silently_skip_core_question`
  in `agent/test_skip_regressions.py`. Full suite: 76/76 passing after the
  fix, including an update to 7D's own ordered-walk test, which had been
  unknowingly relying on the exact gap this closed (TRANSITION-only mock
  LLMs now need a real ASK turn first, matching actual intended behavior).
- **Zero-question VERBAL section at publish time — CLOSED, not carried as an
  accepted gap.** `publish_job` (backend/backend/api/endpoints/admin.py) now
  rejects (409) publishing a `Job` whose `InterviewDefinition` has any
  section with zero questions. Deliberately narrow — does NOT require at
  least one section to exist at all, and does NOT decide whether
  `CODING`/`MCQ` sections should be publishable given Phase 9 is unbuilt;
  both stay separate, undecided questions. Distinguished from
  `CURRENT_DECISIONS.md`'s unresolved "Publishing vs. draft behavior for
  InterviewDefinition" item (that's about editability semantics — can a
  published definition change; this is content-completeness, a correctness
  check, not a product-taste decision) so fixing it didn't require resolving
  that item. Regression coverage: `test_phase5_publish_validation.py` (a
  Phase 5 file/concern — fixed here because it was found during 7F's
  scoping, not because it belongs to Phase 7). 7F's fixture no longer needs
  a disclaimer about unproven authoring-pipeline coverage on this point.

## Non-negotiables carried over from AGENTS.md, restated for this phase
- Every sub-phase gets its own explore -> plan -> review -> execute -> verify
  cycle. No plan is approved sight-unseen given this phase's stakes.
- The legacy /internal/load payload shape must keep working for existing
  sessions until 7E confirms the adapter — do not break it mid-phase.
- No sub-phase silently invents an answer to something this document marks
  as undecided (especially the exact time-tier thresholds in 7B).
