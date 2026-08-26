# Transition Phase Workflow

Invoke as: /transition-phase <N>
(e.g. "/transition-phase 3" or "/transition-phase Transition Phase 3")

## Steps

1. Read AGENTS.md, docs/path2hire-transition-plan.md, and
   docs/CURRENT_DECISIONS.md in full before doing anything else.

2. Locate the "Transition Phase <N>" section in
   docs/path2hire-transition-plan.md. This is the ONLY scope for this task.
   If the phase number given doesn't clearly match a section in the plan,
   stop and ask which phase is meant — do not guess.

3. EXPLORE: read the actual, current contents of every file this phase's
   scope says it will touch. Do not rely on prior summaries, the original
   audit document, or your own memory of these files from earlier in the
   session — re-read them now. Also note this phase's "Off-limits" items
   from the plan's Part C table.

4. Cross-check against docs/CURRENT_DECISIONS.md. If anything this phase
   needs depends on an item still marked UNRESOLVED there, stop and name
   it explicitly instead of assuming an answer.

5. PLAN: produce a written implementation plan only — no code yet. Include:
   - files touched
   - models/migrations added or changed
   - an explicit "Frozen Contracts Confirmation" section stating which of
     AGENTS.md's frozen files you are, and are not, touching
   - anything you're uncertain about or that conflicts with an earlier
     decision — flag it rather than silently picking an interpretation

6. STOP. Do not proceed to execution until the plan is explicitly approved
   in a follow-up message.

7. Once approved: execute the plan.

8. VERIFY: run the full test suite. If this phase included any DB schema
   change, also generate the Alembic migration and apply it to a dev/test
   database first. Paste all output — do not declare the phase complete
   without this step.

9. If new tables or endpoints were added, update docs/BASELINE_SCHEMA.md
   so it stays an accurate live snapshot for future phases.
