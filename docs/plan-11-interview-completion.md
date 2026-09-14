# Plan 11 — Interview Completion & Closing Flow

Not a numbered Transition Phase — reference this doc directly. Scope:
close the full candidate journey (apply/invite → intro → sections →
waiting room → **closing**) for real, fixing the bug where finishing the
last section loops back into the Verbal view instead of a dedicated
completion screen.

**Explicitly OUT of scope for this plan, deliberately deferred:** the HR
results dashboard (viewing/comparing candidate evaluations). That is a
separate, future initiative — log it as a placeholder, do not design or
build any part of it here. This plan closes the CANDIDATE side of the
experience only.

## The core product rule this plan enforces (ties back to the still-open Issue 7)
Candidates never see their own evaluation, score, or feedback — only a
polite confirmation that their interview was received and HR will follow
up. Full evaluation is admin/HR-only, whenever that dashboard eventually
gets built. This plan is where that rule finally gets enforced for real,
not just stated.

## Sub-phases

### 11A — Audit: root-cause the loop-back bug, confirm real current state
Before any fix: read `InterviewWorkspace.tsx`'s actual current mode-
selection logic (the `switch`/ternary chosen by `sections_progress?.
current_section_type`). Confirm precisely: what does `current_section_type`
actually become once the LAST section completes and the interview
transitions through `CLOSING` → `COMPLETED`? Is it `null`/`undefined`
(falling through to the VERBAL default, matching the reported bug), or
something else? Get real evidence, don't assume the mechanism from the
symptom alone.

Also confirm, with real evidence, not assumption:
- Does `GET /interviews/{id}/result` currently reject a candidate/guest
  token, or is it still reachable (Issue 7 was scoped months ago but
  completion was never confirmed back to the user — check the real code,
  not the old plan).
- What does `FinalResult.tsx` (classified REDESIGN back in RB-A, still in
  the codebase) currently do, and is it still reachable via any route? Is
  this the file to redesign into the new closing screen, or should it be
  retired in favor of a fresh component?
- Where does the candidate's display name (`full_name`) actually live in
  whatever context/state the frontend has at this point in the flow — is
  it already available, or does something need to fetch it?
- Does resuming a session that disconnected right at/after `COMPLETED`
  correctly reach the same closing screen, or does resume have its own
  version of this same routing gap?

Report all of this before proposing any fix.

### 11B — Backend: lock down candidate access to results, for real
Based on 11A's findings: if `GET /interviews/{id}/result` (or any
equivalent) is still reachable by a candidate/guest token, block it now —
admin-only from this point forward (reuse `get_current_admin`, matching
every other admin-gated endpoint's pattern). This is the backend half of
the "candidates never see their own feedback" rule — do not rely on the
frontend simply not calling it; enforce it server-side, matching this
project's established pattern of not trusting UI-only enforcement for
anything access-control-related.

Confirm the actual evaluation (`final_result`/`DetailedEvaluation`) still
generates and persists correctly server-side regardless of this change —
blocking candidate *access* to it must not affect whether it gets *created*
at all, since that data still needs to exist for the future HR dashboard.

### 11C — Frontend: the closing/thank-you screen
New component (or `FinalResult.tsx` repurposed — 11A's finding decides
which). Visual language consistent with `WaitingRoomScreen.tsx` and the
post-11-consolidation header/card treatment (one clear header, one clear
card — not a new pile of small boxes; apply the same radius/shadow/spacing
scale already established). Content:
- Personalized: "Thank you, {candidate's first name}."
- Clear, warm confirmation: interview received/submitted, HR will review
  and follow up. No score, no evaluation, no "how you did" language of any
  kind — this screen must not accidentally imply feedback is coming from
  the app itself.
- No action needed beyond acknowledgment — this is a terminal screen, not
  one with further controls (no Repeat/Hint/etc. — those belong to an
  active interview, not a finished one).
- RTL-correct (per the rebrand's standing RTL requirement) and bilingual,
  matching every other candidate-facing screen.

### 11D — Frontend: fix the actual routing gap
Add the missing branch(es) in `InterviewWorkspace.tsx` (or wherever 11A
finds the real mode-selection logic lives) for `CLOSING`/`COMPLETED`
phases, rendering 11C's screen instead of falling through to
`VerbalSectionView`. Also fix the resume-path version of this gap if 11A
found one. Confirm this is a real phase-aware branch, not another default
fallthrough case that happens to work today and breaks again later.

### 11E — Integration & live verification
Full walkthrough, live browser, real candidate: apply/invite → intro →
section 1 → waiting room → section 2 (last) → **closing screen showing the
thank-you message, not a loop back to Verbal**. Confirm via the network
tab that the frontend never even attempts to call the result endpoint for
a candidate session. Also verify the resume-into-completed case from 11A.

## Explicitly deferred (log only, do not build)
**Plan 12 (placeholder name) — HR results dashboard.** Viewing/comparing
candidate evaluations, per-job candidate lists, score displays. Real,
substantial future work — ties into the still-deferred Phase 8 (results
normalization). Do not start any part of this now; this plan exists
specifically to close the candidate-side experience first, cleanly, before
that work begins.

## Non-negotiables (carried over from the whole project)
- No automated testing — manual/live browser verification only, shown, not
  described, per current standing instruction.
- `controller.py`/`/internal/*` stay frozen unless 11A's findings reveal a
  genuine need to touch them (unlikely — this looks like a frontend
  routing gap, not a backend one) — if so, that needs the same explicit
  sign-off as every other frozen-file change this project has required.
- Apply the Himma design system and the post-consolidation
  header/card/radius standard already established — do not introduce a
  new one-off visual style for this screen.
- Track this as its own clean unit — don't let HR-dashboard scope creep
  into 11A-11E under the assumption "we're already in here."
