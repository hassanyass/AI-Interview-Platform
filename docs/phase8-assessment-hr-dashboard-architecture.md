# Phase 8 — Assessment Criteria & HR Results Dashboard

This activates the long-deferred "Phase 8: results normalization" item
from the original transition plan, now with real, expanded scope: HR-
defined assessment criteria (set during job/question setup), criteria-
aware scoring with justification, and an HR-facing results dashboard
linked to each Job. Reference this doc directly — not part of the original
numbered Transition Phase sequence, but follows the same discipline.

## Standing rules for this whole effort
1. **NO automated testing, no live browser flow-driving.** Verify at the
   code/isolated level only (direct function calls, real API calls, log/DB
   inspection). Full manual end-to-end testing happens later, done by the
   user — do not attempt to substitute for it.
2. **Every sub-phase gets explore → plan → my review → execute**, same as
   every other major feature this project has built (Phase 7, Phase 9, the
   waiting room, Plan 11). This phase touches scoring logic candidates and
   HR will both rely on — treat it with at least that much care.
3. **`controller.py`/`/internal/*` stay frozen** unless a sub-phase's
   plan explicitly justifies touching them, same sign-off requirement as
   always.
4. **Don't guess at product decisions — surface them.** This phase has
   several genuine open questions (criteria granularity, what "suggested
   candidate" means, how behavioral assessment actually gets measured from
   a transcript). Each sub-phase below names what it must ask before
   building, not assume.

## Sub-phases

### 8A — Exploration: audit the real current evaluation pipeline
Ground truth before designing anything. Read and report on, with real
evidence:
- `EVALUATOR_PROMPT` and `DetailedEvaluation`'s actual current shape (this
  was already found once to be mismatched with what it's prompted to
  produce, per Phase 7D's fix — confirm that fix's current state).
- `DetailedEvaluation.recommendation` — what does it actually contain
  today (a free-text string? an enum? how is it populated by the LLM)?
  Does this already partially cover the "suggested candidates" concept, or
  is it unrelated?
- `generate_final_evaluation()` in `controller.py` — the real evidence
  dict it builds today (per 9D's work: `question_records`, `transcript`,
  per-question `eval_criteria`). Confirm current state, don't assume it's
  unchanged since 9D.
- Where `final_result` is stored, and its exact current JSONB shape in
  live DB rows (query real data, not just the Pydantic model).
- What Plan 11's `AdminResultView.tsx` (parked, unwired) currently
  displays — is any of it directly reusable for 8F's dashboard, or built
  around the old shape?

Report findings only — no schema or plan proposal yet.

### 8B — Product & schema design: assessment criteria model
Real open questions to resolve explicitly, not assume:
1. **Granularity** — do HR-defined criteria live at the Job level (one set
   applies to the whole interview), the Section level (different criteria
   per VERBAL/CODING/MCQ), or both (job-wide criteria plus optional
   section-specific ones)?
2. **Behavioral criteria** — the user wants things like "clarity of
   thought," "organization," "communication" assessed alongside content
   correctness. These aren't answerable from `eval_criteria`'s existing
   per-question rubric (which grades correctness/approach) — they're
   properties of HOW the candidate communicated across the whole
   transcript. Propose how these get captured: a fixed, curated set HR
   can toggle on/off per job (simpler, more consistent, recommended
   starting point) vs. fully custom HR-authored behavioral criteria
   (much more flexible, much harder to keep the evaluator prompt
   reliable against). Flag this choice explicitly, don't default silently.
3. **"Suggested candidates"** — is this a score-threshold-based
   computation (e.g. overall_score >= X), a distinct LLM-generated
   recommendation category (yes/no/maybe), or an admin-manual flag set
   after reviewing? Depends partly on 8A's finding about the existing
   `recommendation` field.
4. **Structured schema** — propose real `Evaluation`/`Score` tables (or
   equivalent) replacing/supplementing the `final_result` JSONB blob,
   capturing: per-criterion score, justification text (tied to specific
   evidence — a transcript excerpt or question_record reference, not just
   a vague LLM sentence), overall score, and whatever "suggested"
   mechanism gets decided in item 3.

This is a real, consequential design decision — present options with
trade-offs per the established pattern (like the Phase 7B time-tier
design, the Phase 9A schema choices), don't silently pick one.

### 8C — Backend: criteria-aware evaluation generation
Once 8B is approved: rework the evaluator (likely `EVALUATOR_PROMPT` +
`generate_final_evaluation()`) to consume the HR-configured criteria for
that specific job/section and produce real, evidence-grounded per-
criterion scores and justification — not a generic fixed rubric anymore.
This touches `controller.py` (frozen) — needs explicit sign-off as its own
step, same as every prior frozen-file change this project has made.

### 8D — Backend: HR dashboard data endpoints
- Per-candidate detailed result endpoint (admin-only — building on Plan
  11's already-shipped lockdown, not reopening it).
- Per-job aggregate endpoint: total candidates, completed vs. in-progress,
  suggested-candidate count (per 8B's chosen mechanism), whatever else 8B's
  schema naturally supports.

### 8E — Frontend: HR criteria-authoring UI
Added into the existing Job/Section/Question admin flow (Phase 5/9G's
surfaces) — where HR actually defines what matters for a given job,
including behavioral-focus toggles per 8B's decision. Same "functional,
Himma-styled, no over-design" bar as every other admin surface, same
"error-friendly messaging" standard.

### 8F — Frontend: HR Results Dashboard
Per-job candidate list (scores, status, suggested flag), drill-in to a
detailed per-criterion justification view — reusing `AdminResultView.tsx`
from Plan 11 if 8A confirms it's compatible with the new shape, rebuilding
if not. Aggregate stats view per job (candidate counts, etc.). Real UX
work per the rebrand's design system — this is a genuinely new, important
surface, not a quick bolt-on.

### 8G — Integration verification (deferred)
Full verification happens later, manually, by the user. This sub-phase is
a placeholder for whenever that full pass happens — not to be started
proactively.
