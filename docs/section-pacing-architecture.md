# Section Pacing & Waiting Room
## Architecture Plan

New feature, not a bug fix. Builds on top of Phase 7/9's ordered
core-question walk. Reference this doc directly — not a numbered
Transition Phase.

## Resolved decisions (see CURRENT_DECISIONS.md for the source record)
1. Waiting room time is free/unclocked — the interview clock pauses
   entirely while a candidate waits there.
2. Auto-proceed after a timeout — default 5 minutes, must be configurable
   (env var), not hardcoded. Confirm the exact default with the user before
   shipping if 5 minutes feels wrong once built and tested live.
3. Admins set each section's time budget directly. Total interview
   duration becomes the SUM of section budgets — no separate overall cap
   set independently.

## Critical context: this reverses part of Phase 9B's design, on purpose
Phase 9B generalized `_active_core_section()` so `BACKGROUND` executes
ALL core sections in sequence, **invisibly** — moving from one section to
the next was deliberately built to skip `_transition_to()` entirely
(`BACKGROUND -> BACKGROUND` was explicitly not modeled as a transition).
This feature requires the opposite: a real, candidate-visible, clock-
pausing stop between every section. Do not treat this as a small addition
to `_advance_core_question()` — it changes what happens at the exact
boundary 9B made invisible. Explore 9B's actual current implementation
fresh before designing anything; don't assume the old behavior described
here is still accurate without checking.

## Real open items for exploration (not decided — explore first)
1. **Does `InterviewSection.config` (JSONB) already exist and go unused
   for timing?** The original Phase 2 schema described this column's
   purpose as "e.g., duration limit, coding language." If it exists and
   is empty/unused today, that's the natural home for a per-section
   `time_budget_minutes` — confirm before adding a new column.
   **Confirmed (exploration pass): yes — exists, and already fully wired
   through `SectionCreate`/`SectionUpdate`/`SectionResponse` and
   `admin.py`'s section CRUD. All 686 current rows read back as `None`.
   Flag for whatever WR-A actually builds: at the SQL level every one of
   those 686 rows has an explicit JSONB `null` written (not a true SQL
   NULL) — `SectionCreate.config` defaults to Python `None`, which
   SQLAlchemy's JSONB type serializes as the JSON `null` literal rather
   than leaving the column untouched. A future `WHERE config IS NULL`
   query would miss all of them (it needs `WHERE config IS NULL OR config
   = 'null'::jsonb`, or an application-level check after decoding).**
2. **New `InterviewPhase` needed.** This is the first feature in the
   project requiring an actual `state_machine.py` change (7D explicitly
   confirmed none was needed for the original design — this is different).
   Propose the new phase (e.g. `SECTION_BREAK` or `WAITING_ROOM`) and its
   `VALID_TRANSITIONS`/`VALID_ACTIONS_PER_PHASE` entries: entering it at
   the end of any core section (whether completed normally or the section
   was the last one before CLOSING — CLOSING itself doesn't need a waiting
   room), and the transition out once the candidate proceeds or the
   auto-timeout fires.
3. **Auto-timeout mechanism.** How does a timer-based auto-transition get
   implemented in this codebase's existing async/event-driven controller
   architecture — is there an existing pattern for a delayed/scheduled
   action (check `_candidate_endpoint_delay`'s scheduling mechanism from
   the real-time hardening work as a possible model), or does this need
   something new?
4. **Derived `duration_minutes` recalculation.** Where does the sum-of-
   sections recalculation actually happen — on every section CRUD
   operation (create/update/delete/reorder), computed live at read time
   instead of stored, or both (stored as a cache, recomputed on writes)?
   Consider: does this affect anything that currently reads
   `duration_minutes` expecting an admin-set value (e.g. Phase 7's
   `time_remaining_seconds = duration_minutes * 60` initialization,
   `InterviewPlan.time_tiers` thresholds which are currently WHOLE-
   INTERVIEW based, not per-section) — the time-tier system likely needs
   to become per-section-aware too, not just the waiting room. Flag this
   explicitly, don't silently leave the tiers computing against a now-
   meaningless whole-interview clock when sections have independent
   budgets.
5. **Resume/reconnect behavior.** If a candidate disconnects while in the
   waiting room, does resuming put them back in the waiting room (with a
   fresh timeout), or somewhere else? Existing checkpoint/resume logic
   needs to account for this new phase.
6. **JobCreatePage's existing `duration_minutes` field.** Per decision 3,
   this field's role changes — does it get removed from job creation
   entirely (duration is now purely a byproduct of section configuration,
   set later in SectionsEditor), or kept as a read-only computed display?

## Suggested sub-phases (adjust once exploration answers the above)
- **WR-A** — Schema + time-tier rework, designed together. Per-section
  time budget (reusing `config`, confirmed available), derived
  `duration_minutes` recalculation, AND the `_total_duration_sec`/
  `get_remaining_time()`/`_time_tier()` rework to become per-section-
  relative. Merged from the original separate WR-A/WR-D split — the
  per-section budget shape has to be designed against how the timer
  subsystem will actually consume it from the start, not retrofitted
  once the schema already exists. See the approved plan for the exact
  design.
- **WR-B** — State machine: the new phase, transitions, auto-timeout
  mechanism design.
- **WR-C** — Controller: entry/exit logic for the waiting room, breaking
  9B's invisible section-to-section transition at exactly this boundary
  (and nowhere else — the within-section walk logic itself is untouched).
- **WR-D** — Frontend: SectionsEditor's per-section time input UI
  (replacing/supplementing the job-level duration field), the waiting-room
  screen itself (friendly message, next-section info, proceed button,
  countdown-to-auto-proceed if shown to the candidate).
- **WR-E** — Integration verification, mirroring 7F/9I's pattern:
  deterministic mock-LLM tests proving a multi-section walk now stops at
  each boundary, resumes correctly, and the auto-timeout fires correctly
  — plus a live verification given this is a real UX/timing feature.

## Non-negotiables
- `controller.py`/`state_machine.py` changes need the same explicit
  sub-phase sign-off as every other frozen-file touch this project has
  required — no exception for this being "just a UX feature."
- Do not silently change how within-section question order/follow-up/
  time-tier logic works while implementing this — scope strictly to the
  section-boundary behavior and the derived-duration mechanics.
- Live browser + live agent-worker verification required before any
  sub-phase is considered done — this is exactly the kind of feature where
  a passing mock test and an actually-working candidate experience could
  diverge, same lesson as Issue 6.
