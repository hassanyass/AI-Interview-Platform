# Verbal "Background" Subsection — Plan

Status: **PLAN — awaiting sign-off.** Touches two frozen contracts
(`agent/agent/interview/controller.py`, and one additive field on the
`/internal/*` load contract), so per `CLAUDE.md` §2 nothing is built until
approved. Written 2026-09-15 against Himma_v2, after the verbal-flow work
(`docs/verbal-section-flow-plan.md`) — this plan builds on that, and reuses
its machinery rather than adding a second one.

The picture being built: HR ticks "include background" on a VERBAL section
(default on). The candidate uploads a CV with their name when they arrive.
The interview's verbal section then opens with a short **Background**
conversation grounded in that CV (current/previous role, technologies,
a project), before moving to the HR-approved **Discussion** questions. The
candidate can see which part they are in and can skip the background. The
CV is weighed in the evaluation.

---

## 0. What exists today — research findings (with the one blocker)

| Area | Finding | Consequence |
|---|---|---|
| **CV upload** | `POST /api/v1/resumes/` exists (`resumes.py`): stores the PDF, extracts text (PyMuPDF), then Groq turns it into a structured profile written onto `CandidateProfile` (title, years, skills, languages, frameworks, projects, education). `JobApplication.resume_id` links the CV to the application. | The parsing pipeline we need already exists. |
| **BLOCKER** | `ResumeService.upload` requires the `supabase-py` storage client, which is `None` in this project (the SDK rejects the new `sb_secret_…` key format — same limitation hit for demo-account creation). Upload therefore returns **500 "Supabase client is not initialized"** today. | **CV upload is broken end-to-end.** Must be fixed first (§7 step 0). Also to check on implementation: `resumes.py` reads the file bytes and then `upload()` calls `file.read()` again — likely reads empty on the second pass. |
| **Candidate entry pages** | `ApplyPage`/`InvitePage` have **no CV upload** — deliberately deferred ("Sub-phase 6C's `resume_id`, once the upload-sequencing question is resolved"). `PublicRegisterRequest.resume_id` is already optional. | Sequencing is an **unresolved decision** (§5-Q2), not an oversight. |
| **What the agent receives** | `/internal/{id}/load` sends `candidate_profile` as the structured dict above (not raw CV text), plus sections as `SectionPayload{section_type, time_budget_minutes, questions}`. `InterviewSection.config` is **not** forwarded. | The agent already has the CV *content* it needs. An HR flag in `config` cannot reach it without one new field. |
| **Verbal flow** | Ordered core questions, now deterministic (verbatim first turn, cap 2, +2:00, forced advance, intro handshake). Questions carry `source` ("HR_APPROVED") and `competency`. | Background questions can ride the **same** machinery if they are simply more questions in the ordered list, tagged differently. |
| **Legacy background** | A free-form `BACKGROUND_PROMPT` ("understand the candidate's relevant experience efficiently", uses `{profile}`) exists but is bypassed for B2B sessions. | Its *intent* and wording are reusable for the generation prompt; its loop is not (advisory progression — the class of bug just fixed). |
| **Evaluation** | Neither evaluator (agent `generate_final_evaluation`, backend `evaluation_generator`) includes the candidate profile in its evidence. Criteria are `assessment_criteria` rows (TEMPLATE + per-job), each with a `weight`; `weighted_score` is computed from them. | Weighting the CV = add it to the evidence **and** add a criterion. No new scoring mechanism. |
| **Results** | Question-by-question review resolves `question_records[].question_id` → `InterviewQuestion`; a generated (non-HR) question resolves to `title/text = None` (acknowledged in `admin.py`). Checkpoint `question_records` is typed `List[dict]` — extra keys pass through untouched. | Background questions can carry their own text in the record, additively. |
| **Skip controls** | `SKIP_QUESTION` (one question, real skip) and `END_SECTION_EARLY` (whole section) already exist as UI commands in BACKGROUND. | A "skip background" is a new, *bounded* command between those two. |
| **HR authoring** | `SectionsEditor` edits `InterviewSection.config` (JSONB) — currently `time_budget_minutes`. `SectionUpdate.config: dict`. | The checkbox is a config key; **no migration**. |

---

## 1. Design — Background as the first subsection of VERBAL

**Core idea.** Background = *N per-candidate questions generated from the
parsed CV at session bootstrap*, prepended to the VERBAL section's ordered
question list and tagged `source="BACKGROUND"`. From that point on they are
ordinary core questions: verbatim first turn, follow-up cap, time grant,
forced advance, transcript, records — all the deterministic machinery
already shipped applies unchanged. The only new behaviours are at the
**edges**: generation at the start, a spoken bridge + UI change at the
Background→Discussion boundary, and a skip command that jumps that boundary.

**Why generate on the agent, not the backend.** The agent already receives
the structured profile via `/load`; generating there (exactly the existing
`[TECH-GEN]` precedent) needs **no** new load data for the questions
themselves. Generating in the backend at upload time would need per-session
question storage *and* changes to the frozen `/load` handler — strictly more
frozen surface for no benefit. Rejected.

**The one thing that must travel: HR's flag.** `config.include_background`
has to reach the agent → one **additive, optional** field
`SectionPayload.include_background: bool = False`. This is the single
`/internal/*` touch in the plan (§4).

**Tagging over new structures.** No new "subsection" model: a background
question is `Question(source="BACKGROUND", competency="background:<topic>")`.
`_active_core_section()` etc. are untouched; the boundary is detected as
"current question's source changed from BACKGROUND to HR_APPROVED".

---

## 2. Data flow, end to end

### HR (authoring)
`SectionsEditor` → VERBAL section gets a checkbox **"Start with a background
conversation based on the candidate's CV"** (default **checked** for new
VERBAL sections) → saved as `config.include_background`. Publish validation
unchanged. `/load` forwards it as `SectionPayload.include_background`.

### Candidate (entry)
Both landing pages (`ApplyPage` = public link, `InvitePage` = invitation)
gain a CV step: name (already there) + **PDF upload** (drag/drop, ≤ 5 MB) →
`POST /resumes` with the guest/candidate token the page already holds after
register/redeem → extraction runs → `CandidateProfile` fields +
`JobApplication.resume_id`. Sequencing recommended: *register/redeem → upload
→ start*; the token issued by register/redeem is what authorises the upload.
Show a short "what we read" summary (title, years, top skills) so the
candidate sees the CV was understood. Sequencing itself is §5-Q2.

### Agent (bootstrap)
`build_core_sections` (`main.py`): when the VERBAL payload has
`include_background` **and** `candidate_profile` is non-empty, call the new
`background_generator` (Groq, structured JSON — same shape as HR questions:
title, competency, text, eval_criteria bands) with the profile, role and job
description, asking for N questions across: current/most recent role and
responsibilities; technologies/tools actually used; one project in depth.
Prepend them to the VERBAL list. No CV → §5-Q1 (recommend: 2 generic
role-based background questions, never block the interview).

### Live flow (controller — frozen)
- Questions walk as today. **Boundary bridge:** when a forced/voluntary
  advance moves from the last `BACKGROUND` question to the first
  `HR_APPROVED` one, the composed utterance is *"Thanks, that gives me a good
  picture of your background. Now let's move to the discussion questions.
  <Q1 verbatim>"* (en/ar `SYSTEM_MESSAGES`). Same composition point as the
  A1 forced advance; one extra branch.
- **Skip background:** new candidate control `SKIP_BACKGROUND` (UI command +
  allowed in BACKGROUND while a background question is current). Records
  every remaining background question `SKIPPED` via `_advance_core_question
  (outcome_override=SKIPPED)` in a loop, then speaks the bridge + Q1
  verbatim. Per-question `SKIP_QUESTION` keeps working inside background.
- **UI state (additive fields):** `verbal_subsection: "BACKGROUND" |
  "DISCUSSION" | null`, `background_total`, `background_index` (1-based),
  and `SKIP_BACKGROUND` appears in `allowed_controls` only during background.
- **Records:** for `source="BACKGROUND"` questions, the `QuestionRecord`
  dict written to the checkpoint gains `question_title`, `question_text`,
  `competency`, `subsection: "BACKGROUND"` (additive keys in the existing
  `List[dict]`; backend stores as-is).

### Evaluation
- **Evidence:** add `candidate_profile` to the evidence dict in **both**
  evaluators (agent `generate_final_evaluation`, backend
  `evaluation_generator`) — today neither sees the CV at all.
- **Criterion:** one new TEMPLATE `assessment_criteria` row (additive seed
  migration, same pattern as the 8 existing): `cv_alignment` /
  "CV & Experience Alignment" / kind `content` / weight 5 — *"Does the
  candidate's spoken account of their experience substantiate and align
  with their CV, and is that experience relevant to the role? Flag gaps
  between what the CV claims and what the candidate could actually
  discuss."* HR toggles/weights it per job in the existing
  `CriteriaEditor`; `weighted_score` picks it up with zero mechanism change.
- **Evaluator prompts:** an instruction block for that criterion in both
  evaluator prompts.

### Results (admin)
- Question-by-question review groups rows under **Background** and
  **Discussion**; for background rows, `title/text/competency` come from the
  record's own keys when the id does not resolve (`admin.py`, not frozen).
- The CV alignment criterion shows in the criteria breakdown automatically.

---

## 3. Presentation (candidate side)

- **Where they are:** in the verbal title strip, a two-segment indicator
  **Background · Discussion** — active segment filled (secondary/maroon per
  the e& palette), inactive outlined; under it "question 2 of 3" for the
  active subsection. Driven purely by the new UI-state fields.
- **Boundary moment:** when the subsection flips, the indicator animates
  the fill across (motion-safe), and the interviewer's spoken bridge does
  the rest — no modal, no interruption.
- **Skip:** "Skip background" as a secondary control in the controller bar,
  visible only while `allowed_controls` includes `SKIP_BACKGROUND`; a
  one-line confirm ("Skip straight to the discussion questions?"), same
  pattern as End Section.
- **CV step (entry pages):** an upload card with the file name, a subtle
  progress state while extraction runs (a few seconds — Groq call), then the
  "what we read" summary; "Continue without a CV" per §5-Q1/Q2.

---

## 4. Files touched

| File | Frozen? | Change |
|---|---|---|
| `backend/backend/schemas/persistence.py` | **YES (/internal)** | `SectionPayload.include_background: bool = False` |
| `backend/backend/api/endpoints/internal.py` | **YES (/internal)** | forward `config.include_background` into that field |
| `agent/agent/interview/controller.py` | **YES** | boundary bridge; `SKIP_BACKGROUND` command; 3 UI-state fields; record enrichment for background questions; profile in evaluation evidence |
| `backend/backend/services/resume_service.py` | no | **prerequisite** — replace the dead storage client (§5-Q5) |
| `backend/backend/api/endpoints/resumes.py` | no | double-`read()` check |
| `backend/alembic/versions/<new>_seed_cv_alignment_criterion.py` | no | additive seed |
| `backend/backend/services/evaluation_generator.py` | no | profile in evidence + prompt block |
| `backend/backend/api/endpoints/admin.py` | no | results grouping + record-text fallback |
| `agent/agent/interview/background_generator.py` | new | Groq generation (mirrors question_generator's shape) |
| `agent/agent/main.py` | no | prepend generated questions when flagged |
| `agent/agent/interview/state_machine.py` | no | `SKIP_BACKGROUND` control in BACKGROUND |
| `agent/agent/interview/models.py` | no | `CandidateControlAction.SKIP_BACKGROUND`; `Question.source="BACKGROUND"` usage |
| `agent/agent/llm/prompts.py` | no | generation prompt; bridge strings (en/ar); evaluator block |
| `frontend/.../SectionsEditor.tsx` | no | checkbox |
| `frontend/src/pages/ApplyPage.tsx`, `InvitePage.tsx` | no | CV step |
| `frontend/src/types/realtime.ts` | no | 3 fields + control name |
| `frontend/.../VerbalSectionView.tsx`, `InterviewController.tsx` | no | indicator; skip button |
| `frontend/src/routes/admin/CandidateResultPage.tsx` | no | grouping |
| tests: `agent/test_skip_regressions.py` (+ backend test for the seed/evidence) | test | §6 |

Not touched: DB schema beyond the additive seed; checkpoint contract shape
(extra JSON keys only); the deployed AI-Interview-Platform project.

---

## 5. Decisions I am NOT making (CLAUDE.md §5) — please rule

1. **No CV uploaded.** (a) Skip background silently; (b) ask 2 generic
   role-based background questions; (c) require a CV to start. Recommend
   **(b)** — never block an interview on a file.
2. **CV upload sequencing** (the deferred 6C question). Recommend: after
   register/redeem (that token authorises the upload), before the room
   token is issued; **optional with a nudge** for the demo, mandatory later
   if HR wants it.
3. **Background sizing.** Question count (env `VERBAL_BACKGROUND_QUESTION_
   COUNT`, default 3), follow-up cap for background questions, and whether
   the +2:00 grant applies to them. Recommend **3 / cap 1 / grant applies**
   (keeps background brisk; consistent clock behaviour).
4. **CV weight.** Fixed, or the same HR-adjustable weight (default 5) as
   every other criterion? Recommend **HR-adjustable, default 5** — it is
   just another criterion.
5. **Storage fix.** Supabase Storage via a direct REST call (as done for the
   demo-account auth call) vs **Cloudflare R2** (the client already works
   for recordings). Recommend **R2** — one storage system, one working
   client.
6. **Shared profile overwrite.** One `CandidateProfile` per email (decided);
   a second CV for a different job overwrites skills/projects on the shared
   profile (the per-application CV is still linked via `resume_id`).
   Recommend **accept for the demo**, note it.
7. **Skip granularity.** Whole background only (`SKIP_BACKGROUND`), or also
   per-question inside it (`SKIP_QUESTION`, which already exists). Recommend
   **both**.

---

## 6. Verification

Deterministic (existing harness, scripted LLM/generator):
- ordering: background questions precede HR questions; `source` tags correct;
  none generated when the flag is off or the profile is empty (per Q1).
- boundary: advancing off the last background question speaks the bridge +
  HR Q1 verbatim; `verbal_subsection` flips; `background_index/total`
  correct throughout.
- `SKIP_BACKGROUND`: remaining background questions recorded SKIPPED; lands
  on HR Q1 verbatim; control absent from `allowed_controls` in Discussion.
- records: background `QuestionRecord` dicts carry title/text/competency/
  subsection; checkpoint round-trip keeps them.
- evaluation: evidence includes `candidate_profile` in both evaluators;
  seed migration adds exactly one enabled TEMPLATE criterion.
- results: fallback text used when a record id does not resolve.
- existing suite stays green.
Live: one full run with a CV — upload, "what we read", background questions
grounded in the CV, bridge, discussion, results grouped, CV alignment scored.

## 7. Rollout order
0. **Prerequisite:** fix CV upload storage (§5-Q5) + the double-read; verify
   `POST /resumes` works. Nothing else is testable without it.
1. HR flag → contract field → agent generation + ordering + tags (tests).
2. Candidate CV step on both entry pages.
3. Live-flow UX: bridge, indicator, skip.
4. Evaluation evidence + criterion seed + results grouping.


---

## 8. The four pipelines, confirmed (addendum 2026-09-15)

| Pipeline | Actor / when | Produces | Consumed by |
|---|---|---|---|
| **P-HR — authoring** | HR, at job creation | On the VERBAL section: `include_background` (default on), `background_time_budget_minutes` (default 5), `background_question_count` (default 3); the HR discussion questions with their `eval_criteria` bands; the job's assessment criteria and their **weights** (incl. the new `cv_alignment` criterion, HR-toggleable/weightable). | Interview agent (flag, budgets, questions) and Evaluation (criteria, weights). |
| **P-CV — candidate intake** | Candidate, on arrival | PDF → text → structured profile (title, years, skills, languages, frameworks, projects, education) on `CandidateProfile`; `JobApplication.resume_id`. | Interview agent (to generate background questions) and Evaluation (as the reference the spoken account is checked against). |
| **P-Interview — runtime** | Agent, per session | Background questions generated from the profile (bounded, §10); the ordered walk Background → Discussion; a transcript and per-question records, every turn/record **tagged with its subsection**. | Evaluation. |
| **P-Eval — scoring** | Agent at completion (and backend on regenerate) | Per-criterion scores + `overall_score` (holistic) + `weighted_score` (criteria × HR weights); `evidence_sufficiency`. | Results page. |

The two input pipelines never talk to each other; they meet only in the
agent (to *ask*) and in evaluation (to *judge*). HR decides whether/how long
a background exists; the CV decides what it is about.

## 9. How scoring is affected — precisely

**Mechanism unchanged.** No new formula. Scoring stays: HR criteria, each
scored 0–100 by the evaluator, combined by HR's weights into
`weighted_score`; `overall_score` remains the evaluator's holistic view;
null scores are excluded from the weighted average (existing convention:
null = insufficient evidence, never "scored zero").

**What changes is the evidence, and the instructions.**
1. **Evidence gains the profile** (both evaluators). Today the CV is invisible
   to scoring; after this it is the reference document.
2. **Evidence is subsection-tagged.** Every transcript turn and question
   record carries `BACKGROUND` or `DISCUSSION`. The evaluator is instructed:
   - *Background evidence* primarily supports **`cv_alignment`** (does what
     they said about their roles/technologies/projects substantiate the CV;
     is the experience relevant to this role) and the **behavioural**
     criteria (communication, clarity, structure — which apply to any
     speech).
   - *Discussion evidence* (the HR questions, with their HR-authored bands)
     is the **primary** evidence for role-competency judgements and for
     `overall_score`. Background is context, not the assessment.
   This keeps HR's questions as the thing the candidate is actually scored
   on, while the CV conversation stops being wasted.
3. **HR controls the CV's weight** exactly like every other criterion:
   `cv_alignment` weight 0–10 (default 5), or disabled → the CV plays no
   part in `weighted_score` at all. Nothing HR does not opt into.
4. **Skipped / short background → no penalty.** If the candidate skipped
   background or it timed out with little said, the evaluator returns
   `cv_alignment = null` (insufficient evidence). Null is excluded from the
   weighted average — it neither helps nor hurts. This is explicit in the
   prompt, not left to the model.
5. **Time is not a scoring input** (today or after). It shapes *how much*
   evidence exists, which surfaces through `evidence_sufficiency` and
   through null criterion scores — never as a penalty for being slow.
6. **The HR questions' own bands are untouched.** Generated background
   questions carry their own generated bands so the evaluator can read
   the answer, but those bands only ever inform the two evidence roles in
   (2) — they never stand in for an HR question's band.

## 10. Time engineering — background is bounded by construction

Background must be a brisk warm-up, not a second interview. Four
independent bounds, any one of which ends it:

| Bound | Setting | Default |
|---|---|---|
| Questions | `background_question_count` (HR, per section; env fallback) | 3 |
| Follow-ups | cap **1** per background question (vs 2 for discussion) | fixed |
| Time | `background_time_budget_minutes` (HR, per section) — a **sub-clock** started when background begins; when it expires, the controller bridges to Discussion at the next turn boundary, gracefully (*"Thanks — that gives me a good picture. Let's move to the discussion questions. <Q1>"*), same deterministic path as the forced advance | 5 |
| Candidate | `SKIP_BACKGROUND` (whole) or `SKIP_QUESTION` (one) | — |

**The +2:00 grant does NOT apply during background** (changes the earlier
Q3 recommendation). The grant exists so probing on the *assessed* questions
never eats the promised time; background is a fixed-size warm-up, and a
grant there would defeat the bound above.

**Where the minutes come from — carve-out, not add-on.** The background
budget is carved *out of* the VERBAL section's budget: a 20-minute verbal
section with a 5-minute background guarantees the discussion **at least**
15 minutes. Whatever background does not use (skipped, or finished early)
flows to the discussion. HR sees this in the editor as *"Verbal 20 min —
up to 5 min background, at least 15 min discussion"*. The job's advertised
duration (sum of section budgets, decided) stays exactly truthful; nothing
is added on top. Editor validation: background budget ≤ 50 % of the section
budget.

**Latency at the start.** Background generation is one Groq call
(~2–4 s, same as the existing TECH-GEN call, which it *replaces* for B2B
sessions rather than adding to). It runs concurrently with the greeting
turn, so the candidate never waits on it. If generation fails or returns
nothing usable → background is skipped silently, logged, and the interview
proceeds to the discussion; it never blocks.

**What the candidate sees.** The Background segment of the indicator shows
its own small countdown (*"Background · 3:40 left"*), so the sub-clock is
visible and the transition is expected, not abrupt. The header clock keeps
showing the section total.

**Decisions updated by this addendum:** Q3 → count 3 / cap 1 / **no grant
during background** / HR-set background budget with a 5-min default,
carved out of the section budget. Everything else in §5 stands.


---

## 11. Rulings (2026-09-15) — the plan is now fully decided

| Decision | Ruling |
|---|---|
| Q1 No CV | **Require a CV to start.** The interview does not begin until a CV exists for this application. Implications, engineered in: a clear inline error + retry on a failed upload (never a dead end); PDF only at first (the existing extractor is PDF; DOCX can follow); an invited candidate whose application **already** has a CV (`JobApplication.resume_id` set) is offered "use the CV we have" or replace — never forced to re-upload; the "what we read" summary shown before Start so a bad parse is visible, not silent. |
| Q2 Sequencing | Register/redeem → **mandatory** upload → Start. The register/redeem token authorises the upload; the room token is only issued once `resume_id` is set on the application. |
| Q3 Sizing | Count 3 (HR-settable), follow-up cap 1, **no +2:00 during background**. |
| Q4 CV weight | HR-adjustable `cv_alignment` criterion, default weight 5. |
| Q5 Storage | **Supabase Storage via direct REST** (httpx, service key as bearer) — keeps the existing `resumes` bucket and `users/{id}/resumes/{id}.pdf` paths; bypasses the SDK the same way demo-account creation does. |
| Q6 Shared profile | Accept for the demo; noted. |
| Q7 Skip granularity | Both `SKIP_BACKGROUND` and per-question `SKIP_QUESTION`. |
| Background time | **HR sets it per section** (`background_time_budget_minutes`, default 5, validated ≤ 50 % of the section budget), carved out of the section budget. |
| Clocks | **Both**: header keeps the section total; the Background segment shows its own countdown. |
