# Verbal Section Flow — Structured Orchestration Plan

Status: **PLAN — awaiting sign-off.** Touches a frozen contract
(`agent/agent/interview/controller.py`), so per `CLAUDE.md` §2 nothing below
is implemented until explicitly approved. Written 2026-09-14 against Himma_v2.

> Path note: CLAUDE.md §2 lists `agent/app/interview/controller.py`; the file
> was renamed to `agent/agent/interview/controller.py` in the `app → agent`
> package move. Treated as the same frozen file. Flagging per the "if this
> conflicts with what you observe, STOP and ask" rule — please confirm.

---

## 1. Diagnosis (reproduced, not inferred)

**Symptom reported:** in VERBAL sections the candidate is sometimes not asked
the HR-approved questions; conversation drifts / runs on.

**Reproduced deterministically** with a scripted LLM against the real
controller (3 HR questions; LLM emits ASK, then FOLLOW_UP x4, then a
self-invented ASK):

| turn | LLM emitted | controller applied | followups_used | question index |
|---|---|---|---|---|
| 1 | ASK | ASK | 0 | 0 |
| 2 | FOLLOW_UP | FOLLOW_UP | 1 | 0 |
| 3 | FOLLOW_UP | FOLLOW_UP | 2 | 0 |
| 4 | FOLLOW_UP | **ACKNOWLEDGE** | 2 | 0 |
| 5 | FOLLOW_UP | **ACKNOWLEDGE** | 2 | 0 |
| 6 | ASK (own question) | **ACKNOWLEDGE** | 2 | **0** |

**Root cause.** The max-2 follow-up cap (CURRENT_DECISIONS.md; already
enforced in `process_candidate_input`) *stops* extra follow-ups but does not
*move on*: an over-cap FOLLOW_UP — and a drifted ASK, correctly reclassified
as FOLLOW_UP by the 2026-09-03 fix — is downgraded to `ACKNOWLEDGE`, which
never advances `current_index`. Progression to the next HR question depends
entirely on the LLM volunteering `TRANSITION`. When it does not, the session
sits in an acknowledge loop on the same question until the time tier hits
`very_limited` (< 120 s), the only backstop (`_must_force_transition`). The
controller's own comment at line ~421 names this exact gap.

**Secondary contributor.** Even on a voluntary `TRANSITION`, the voice path
(`voice_adapter.py` ~L768) only speaks the LLM's text and clears history — it
does not chain a new turn. The next HR question is asked only once the
candidate speaks again. A candidate who stays silent after "let's move on"
stalls the interview.

**Baseline for amendment B:** `time_remaining` is unchanged by follow-ups
today — no extension mechanism exists.

---

## 2. Design principles

1. **Deterministic over advisory.** The prompt already says "ask exactly this
   question" and "TRANSITION when follow-ups are exhausted." Prompts are
   hints; the controller must *enforce* the flow. Every guarantee below is
   controller-side.
2. **Reuse the proven paths.** Advancement goes through the existing
   `_advance_core_question()` and the section-boundary branching
   (WAITING_ROOM / CLOSING) that the CODING submit path already uses. No
   second state machine.
3. **Additive only.** New optional fields; no checkpoint schema change; no
   `/internal/*` change (see §5). Legacy (non-B2B) flow untouched.
4. **Scope: the ordered VERBAL core flow only.** MCQ/CODING have a 0 cap by
   decision and their own completion signals.

---

## 3. Amendment A — the agreed questions always get asked

### A1. Cap reached => deterministic advance (the fix)
In `process_candidate_input`, at the existing cap check: when the active
core section is VERBAL, the current question has been asked, and the action
is an over-cap FOLLOW_UP (including a reclassified ASK):

- convert the action to `TRANSITION`, `should_transition=True`;
- **replace** `action.response` (the LLM's would-be extra follow-up must not
  be spoken) with a short bridge line plus **the next HR question's
  `problem_statement`, verbatim** — e.g. *"Thank you. Let's move on to the
  next question. <question text>"* — localised via `SYSTEM_MESSAGES` (en/ar),
  matching the existing bridge copy style;
- let the existing `_apply_action -> _handle_automatic_transition ->
  _advance_core_question()` perform the advance (it already resets
  `followups_used` and records the outcome as COMPLETED);
- after apply, mark the *new* current question `current_question_asked =
  True`, since the controller itself just spoke it. Subsequent LLM turns are
  then correctly "subsequent turns" of the new question.

Edge: last question of the section => bridge only (no next question); the
existing branching takes it to WAITING_ROOM (another section remains) or
CLOSING (none). Unchanged.

### A2. The acknowledge loop becomes unreachable for VERBAL
With A1, the over-cap ACKNOWLEDGE downgrade can no longer occur for a VERBAL
core question. It is kept as-is for the legacy flow.

### A3. (Optional — recommended) Speak the first-turn question verbatim
Today the LLM *voices* the HR question from a prompt instruction ("do not
paraphrase"). To turn "the agreed question is asked" into a hard guarantee:
on the first turn of a VERBAL core question, the controller composes the
spoken text as *LLM lead-in (one sentence, kept) + verbatim question text*
instead of trusting the LLM's rendering. Trade-off: marginally less
conversational blend; gain: zero paraphrase drift. A1 alone fixes the
reported stall; A3 hardens the wording.

### A4. Prompt alignment (`llm/prompts.py` — not frozen)
Update `CORE_QUESTION_PROMPT`'s SUBSEQUENT TURNS block to state the truth:
follow-ups are capped at `{max_followups}`; when exhausted **the system moves
on automatically** — stop probing, do not invent new questions. Fewer wasted
turns; the model stops fighting the controller.

---

## 4. Amendment B — +2 minutes per follow-up, presented well

### B1. Agent-side grant
In `_apply_action`, where `FOLLOW_UP` increments `followups_used`: if the
active core section is VERBAL, add `VERBAL_FOLLOWUP_TIME_BONUS_SECONDS`
(env var, default `120`, per the codebase's "configurable, not hardcoded"
convention) to `_total_duration_sec`. `get_remaining_time()` is
`total - elapsed`, so remaining grows by exactly the bonus. Track
`followup_time_bonus_seconds_total` on `InterviewRuntimeContext` (new field,
default 0 — additive).

Bound: naturally <= 2 x bonus per question (the cap is 2). See §6-Q1 on
whether a section-level ceiling is wanted.

Interaction with time tiers (deliberate): a follow-up granted at the
`limited` tier may lift the tier back to `normal`, re-enabling the second
follow-up. That *is* the "dynamic interview" — and it is bounded by the cap.

### B2. Resume/reconnect safety — no persistence change needed
On resume the controller seeds `_total_duration_sec` from
`context.time_remaining_seconds` (controller.py L62), which already includes
any granted bonus. The extension therefore survives reconnect **without** a
new checkpoint field => `/internal/*` is not touched.

### B3. UI signal (data-channel `state_update` — additive)
Two optional fields on the UI state payload (`generate_ui_state`, mirrored
in `types/realtime.ts`):
- `time_bonus_granted_seconds: number | null` — set only on the update that
  follows a grant (transient), otherwise null;
- `time_bonus_total_seconds: number` — running total for the section.
Unknown fields are ignored by other clients. Preferred over inferring "the
countdown jumped up" client-side, which is fragile against ordinary drift.

### B4. Frontend presentation
One shared `TimeBonusIndicator` component, mounted at the header timer in
`InterviewWorkspace.tsx` and in `VerbalSectionView.tsx`:
- The countdown already re-seeds its deadline on every
  `time_remaining_seconds` update (L267), so the number itself simply jumps.
  What is added is the *moment*.
- **Grant moment:** a small "+2:00" chip rises in beside the timer, holds
  ~2.5 s, fades; the timer digits get one soft pulse. One orchestrated
  moment, not a scattered effect; respects `prefers-reduced-motion`.
- **Persistent tally:** while `time_bonus_total_seconds > 0`, a quiet
  "+4:00 added" tag sits beside the timer so the candidate can see their
  section grew.
- Colour: the positive signal uses the existing `secondary` (maroon) token —
  the e& grey/red/maroon palette — not a green "success" flash. Identical
  treatment in header and section view.

### B5. Candidate-facing copy
Where the section budget is stated (intro / waiting room), note that
follow-ups can add time ("up to +2 min per follow-up"), so the expectation is
set before the first grant lands. Copy only.

---

## 5. Files touched

| File | Frozen? | Change |
|---|---|---|
| `agent/agent/interview/controller.py` | **YES — needs sign-off** | A1 forced advance at the cap check; A3 (optional) first-turn verbatim compose; B1 bonus grant in `_apply_action`; B3 two UI-state fields |
| `agent/agent/interview/models.py` | no | `followup_time_bonus_seconds_total: int = 0` on the runtime context |
| `agent/agent/llm/prompts.py` | no | A4 prompt wording; en/ar bridge strings in `SYSTEM_MESSAGES` |
| `agent/agent/main.py` (or config) | no | read `VERBAL_FOLLOWUP_TIME_BONUS_SECONDS` |
| `frontend/src/types/realtime.ts` | no | B3 optional fields |
| `frontend/src/features/interview-session/TimeBonusIndicator.tsx` | new | B4 |
| `.../InterviewWorkspace.tsx`, `.../VerbalSectionView.tsx` | no | B4 mount; B5 copy |
| `agent/test_skip_regressions.py` (or new `test_verbal_flow.py`) | test | §7 |
| **Not touched:** `/internal/*`, checkpoint schema, any DB migration | — | see B2 |

---

## 6. Decisions I am NOT making (CLAUDE.md §5) — please rule

1. **Section-level ceiling on granted time?** The natural bound is +4 min per
   question (2 follow-ups x 2 min); a 5-question section could grow by up to
   +20 min over budget. (a) accept, no extra ceiling — simplest, matches
   "dynamic"; (b) cap total bonus per section (e.g. <= 50 % of budget).
   Recommend (a) for the demo, with an env-configurable ceiling later if
   needed.
2. **A3 — controller speaks the first-turn question verbatim?** Hard
   guarantee vs. a touch less natural. Recommend yes.
3. **Bonus for the legacy (non-B2B) BACKGROUND flow?** Recommend no — it is
   slated for retirement (Phase 10) and has its own limits.
4. **Advertised duration semantics.** `InterviewDefinition.duration_minutes`
   is the *sum of section budgets* (decided). With bonuses, actual runtime
   may exceed it. Recommend keeping the derived value and presenting it to
   candidates as a minimum via B5. No schema change.

---

## 7. Verification (CLAUDE.md §4.4)

Deterministic tests, same harness as the reproduction:
- **T1** cap reached => `current_index` advances; response contains Q2's
  text verbatim; new question marked asked; `followups_used` reset to 0.
- **T2** cap reached on the *last* question => WAITING_ROOM (another section
  exists) / CLOSING (none); bridge only, no question text.
- **T3** drifted ASK past the first turn at cap => same advance as T1.
- **T4** each FOLLOW_UP adds exactly the bonus to remaining; ASK/ACKNOWLEDGE
  add nothing; at most two grants per question; MCQ/CODING never grant.
- **T5** UI state carries `time_bonus_granted_seconds` on the grant update
  only, plus a correct running total.
- **T6** resume after a grant keeps the extended remaining (round-trip via
  `MockPersistence`).
- **Existing suite** stays green (no legacy-flow behaviour change).
- **Live run** (this project's own standard): one real VERBAL interview with
  a 3-question section; confirm Q1 -> Q2 -> Q3 are asked verbatim, the
  "+2:00" moment renders, and the section ends in WAITING_ROOM/CLOSING
  correctly.

## 8. Rollout order
1. A1 + A4 + T1–T3 — fixes the reported bug; smallest frozen-file diff.
2. B1–B3 + T4–T6 — agent side of the time grant.
3. B4–B5 — presentation.
4. A3, if approved.

Each step is independently shippable and verifiable.
