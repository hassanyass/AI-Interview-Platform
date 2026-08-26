# Transition Phase 9 — Coding & MCQ Section Types
## Sub-Phase Breakdown

Per P2 (CURRENT_DECISIONS.md): LLM-evaluated text/pseudo-code submission
only for Coding — no sandbox execution. MCQ is multiple-choice with
auto-grading. Both follow the exact architectural pattern Phase 7 already
proved for Verbal: HR-approved content, ordered, ferried through /load into
context.sections, deterministically enforced by controller.py — not
regenerated from scratch per section type.

## Prerequisite: remove the Phase 7-era stopgap
Sub-phase 9A's first job is removing the temporary publish-block guard
added after Phase 7's Coding/MCQ gap was discovered, and re-enabling the
SectionsEditor.tsx dropdown options — but only once each type's actual
runtime support is confirmed working, not before. Do not remove the guard
prematurely just because Phase 9 has started.

## Sub-phases

### 9A — Schema bridge for Coding & MCQ (mirrors 7A's methodology exactly)
For each section type, determine what InterviewQuestion needs to carry that
it doesn't today, using the SAME evidence-based method 7A used (check real
usage sites, don't assume from field names):
- Coding: starter_code, test_cases/examples, supported_languages,
  constraints — do these need new columns, or can eval_criteria's JSONB
  carry a defined per-type shape? Check what Phase 4's AI generation
  prompt currently asks for, for ANY section type beyond Verbal — likely
  needs its own prompt variant per type, since question_generator.py's
  current prompt is Verbal-shaped.
- MCQ: options (list), correct_answer(s), single vs multi-select — this is
  structurally different enough from Verbal/Coding that it likely needs a
  clearly-defined eval_criteria shape at minimum, possibly new columns.
Output: finalized mapping tables (one per type), any migrations needed,
and Phase 4's question_generator.py prompt changes needed per type.

### 9B — Runtime model extension
Extend OrderedSectionProgress usage (built generically in 7B — confirm it
already supports non-Verbal section_type values, or needs adjustment) to
support CODING and MCQ walks. Decide: does each type need its own
controller.py phase-branch logic (mirroring _active_core_section's
BACKGROUND-only pattern, now for TECHNICAL/CODING phases), or can one
generalized "ordered core-question walk" method serve all three types with
type-specific prompt/evaluation plugged in? Recommend exploring
generalization given how much 7C/7D duplication a fully separate
per-type implementation would otherwise require.

### 9C — Candidate submission handling
- Coding: candidate submits text/pseudo-code via the existing SUBMIT_CODE
  data-channel command (per the audit, already wired to SOME evaluation
  path in CLOSING — explore its current real behavior before assuming).
  LLM evaluates the submission against the question's stored eval_criteria
  — no sandbox execution per P2.
- MCQ: candidate selects an answer via a new data-channel command (doesn't
  exist yet) or existing text-response path — explore what's simplest
  given the current LiveKit data-channel architecture before designing a
  new mechanism.

### 9D — Deterministic evaluation & follow-up rules per type
- Coding: does the 2-follow-up-max/time-tier system from Verbal apply
  identically, or does code review warrant different limits (e.g. no
  follow-ups on a submitted-code review, just pass/fail against criteria)?
  This is a product decision — flag, don't assume.
- MCQ: almost certainly no follow-ups at all (right/wrong is binary) —
  confirm this is the intended design, don't build follow-up logic for MCQ
  without checking first.

### 9E — Prompt engineering per type
New prompt templates (mirroring CORE_QUESTION_PROMPT's approach) for Coding
review and MCQ presentation, in agent/agent/llm/prompts.py.

### 9F — Publish validation update
Remove the Phase 7 stopgap guard for whichever type(s) are now genuinely
supported. If Coding ships before MCQ (or vice versa), the guard should be
updated incrementally, not removed wholesale — don't re-open the silent-
failure window for the type that isn't done yet.

### 9G — HR frontend: type-specific question authoring
QuestionEditor.tsx needs type-aware fields when generating/editing
Coding (starter code, test cases) or MCQ (options, correct answer) questions
— currently fully Verbal-shaped. "Functional only, no design" bar applies,
same as every prior frontend sub-phase.

### 9H — Candidate frontend: submission UI
Code editor component (or plain textarea, per P2's no-sandbox scope — don't
over-build a real code editor if a textarea satisfies "text/pseudo-code
submission") and MCQ selection UI on the candidate-facing interview page.

**Blocker — RESOLVED 2026-08-26 (Part 1 of the 9H rebrand-work plan).**
`generate_ui_state()` in `agent/agent/interview/controller.py` now mirrors
`_provide_hint()`'s exact `core_section.current_question if core_section is
not None else self.context.current_question` pattern, and `q_data` gained
one new key: `"config": q.config` — the real, un-coerced
`CodingConfig`/`MCQConfig` dict (empty `{}` for VERBAL/legacy questions).
`build_core_sections()` in `agent/agent/main.py` now sets
`coding_required=True` for CODING sections (was hardcoded `False` for
every type) and copies `supported_languages` directly. `starter_code`/
`constraints` are deliberately left at their legacy `Dict[str,str]`/
`List[str]` empty defaults rather than coerced — `config.starter_code`
(a plain string) and `config.constraints` (a plain string) are the real
source of truth the frontend now reads instead.

**Live-verified with real captured `state_update` payloads**, not just
"code compiles" — two real published test jobs (bypassing `publish_job`'s
stopgap temporarily and disclosedly, reverted immediately after each
publish, same pattern as WR-C's own verification), two real candidate
sessions, real agent worker (a stale already-running worker process from
before the edit had to be restarted to actually pick up the fix — flagged
as the same class of dev-server pitfall already documented in
`PROJECT_STATUS.md`'s known debt section). Captured via a non-invasive
`JSON.parse` observation hook in the browser (not a script):

MCQ (`sections_progress.current_section_type: "MCQ"`):
```json
"config": {
  "options": [{"id":"opt-1","text":"O(n)"},{"id":"opt-2","text":"O(log n)"},{"id":"opt-3","text":"O(n^2)"}],
  "correct_answers": ["opt-2"],
  "is_multi_select": false
}
```

CODING (`sections_progress.current_section_type: "CODING"`):
```json
"coding_required": true,
"supported_languages": ["python","javascript","java"],
"starter_code": {}, "constraints": [],
"config": {
  "hints": ["Check divisibility by both 3 and 5 first."],
  "constraints": "O(n) time.",
  "starter_code": "def fizzbuzz(n):\n    pass",
  "supported_languages": ["python","javascript","java"]
}
```

### 9H candidate submission UI — built and live-verified (2026-08-26)
`frontend/src/features/interview-session/InterviewWorkspace.tsx`:
- **Real bug found and fixed alongside the above**: `isTechnical` only
  checked the legacy `TECHNICAL_INTRO`/`TECHNICAL`/`CODING` *phase* values
  — but Phase 9's ordered CODING/MCQ questions run under phase
  `BACKGROUND` (see `_active_core_section()`'s docstring), so the code
  editor never rendered for an ordered CODING question even with
  `current_question` correctly populated. Fixed by also checking
  `sections_progress.current_section_type === "CODING"`.
- CODING: the existing code-editor UI is repointed to prefer
  `question.config.starter_code`/`.constraints` (the real string shape)
  over the legacy `Dict[str,str]`/`string[]` typed fields, which stay
  empty for the ordered flow by design (see above). Language switching no
  longer tries a per-language dict lookup when the config-string shape is
  in use (there's one shared snippet, not one per language).
- MCQ: built from scratch — options rendered as radio buttons
  (`is_multi_select: false`) or checkboxes (`true`), selection state reset
  per question, `SUBMIT_MCQ_ANSWER` sent with the exact
  `{ selected_option_ids: string[] }` shape `controller.py`'s handler
  expects.
- Live-verified end-to-end for both: a real CODING submission (real code
  typed into the real editor, `SUBMIT_CODE` sent, agent acknowledged and
  advanced) and a real MCQ submission (correct option selected, agent
  replied "Got it, I've recorded your answer," section correctly advanced/
  closed). Both interviews reached `COMPLETED` and the report screen
  normally afterward.

**Part 4 — DONE (2026-08-26), both types, per explicit user go-ahead.**
`publish_job`'s per-type 409 stopgap in `admin.py` is permanently removed
(not a temporary bypass — the block itself is gone, comment updated to
explain why and to note it should be restored if a genuine regression is
ever found). `SectionsEditor.tsx`'s `comingSoon` flag was already `false`
for both types from 9G; its stale top-of-file comment (still describing
the stopgap as active) was corrected to match. Live-verified for real: a
fresh job with a CODING section and a VERBAL section, no code edit and no
bypass, published successfully (`POST .../publish` → `200 OK`,
`status: "PUBLISHED"`) through the actual admin UI. Phase 9 (CODING/MCQ
section types) is now genuinely shippable, not just internally verified
under test conditions.

### 9I — Integration verification (mirrors 7F)
Full simulated interviews for each type, same deterministic mock-LLM
controller-test pattern established in Phase 7 — no live LLM calls, no
wall-clock waits.

## Non-negotiables carried over
- Every sub-phase gets its own explore -> plan -> review -> execute -> verify
  cycle, no exceptions given this phase's size.
- Coding and MCQ genuinely may ship at different times — don't force a
  single "Phase 9 done" milestone if one type is structurally harder than
  the other. Track them as semi-independent tracks under one phase number.

## Phase 9 standing rules — apply to every sub-phase automatically
These were established during 9A's review and apply for the rest of the
phase without needing to be repeated per sub-phase:

1. **Any new structurally load-bearing field (grading data, IDs referenced
   elsewhere, anything code will branch on) must be validated at every
   write path that can create or modify it** — AI generation, regenerate,
   manual create, manual update — not just the "main" path. A Pydantic
   shape that exists but isn't actually called to validate incoming data
   at each endpoint does not count as validation.
2. **Referential integrity within a single JSONB blob is not automatic.**
   If one field inside a config references another (e.g. `correct_answers`
   referencing `options[].id`), that cross-reference must be explicitly
   checked in code — Pydantic's shape validation alone won't catch a
   dangling reference.
3. **Live verification means pasted raw request/response from the real
   running server**, not a description of using Swagger UI or a narrated
   "should work." This has been the standard since Phase 5 and applies
   here without exception, especially for anything touching the AI
   generation endpoints (Groq's real output shape is the thing actually
   being verified, not the code that requests it).
4. **New section types (CODING, MCQ) must not silently regress VERBAL.**
   Every sub-phase's test plan includes an explicit VERBAL-unaffected
   regression check, not just new-type-specific tests.
5. **Coding and MCQ are separate tracks.** A sub-phase plan touching one
   type does not need to also solve the other unless explicitly stated.
   State clearly, per sub-phase, which track(s) it covers.
6. **The Phase 7 stopgap publish-block (CODING/MCQ rejected at publish,
   see CURRENT_DECISIONS.md) stays in place per-type until that type's own
   9F sub-phase explicitly confirms it's safe to remove** — do not remove
   it early "since Phase 9 has started," and do not remove both types at
   once if only one is actually done.
7. **A plan's explicit WARNING/open-question block is a hard stop.** A
   generic "proceed" from the user does not answer a named, flagged
   decision — if a plan contains one, execution must wait for that specific
   question to be answered, not treat forward momentum as implicit consent
   to pick a default. If ever genuinely ambiguous whether "proceed" covers
   a flagged question, ask explicitly rather than assume it does.
8. **Every sub-phase should explicitly check whether a new "the LLM
   shouldn't do X" instruction has a deterministic code-level enforcement,
   not just prompt text** — this exact gap has now been found and fixed
   three times in this phase (7C's follow-up cap, 7D/7F's first-turn skip,
   9E's CODING/MCQ transition guard). Advisory-only prompt instructions for
   anything consequential should be treated as a red flag by default, not
   the norm.

## Sub-phase kickoff — this is the whole prompt, every time
Once a sub-phase's plan is approved and executed, kick off the next one with
exactly this and nothing else needs to be added:

> Use the transition-phase skill for Transition Phase 9, sub-phase <9X>.
> Explore first, give me a plan. Wait for approval before executing.

The skill auto-loads this doc (per its own step 2a) and the standing rules
above apply automatically. Only add extra context in a kickoff prompt if
something genuinely new and unplanned needs flagging (like 9A's original
config-validation gap) — routine sub-phase progression doesn't need it.
