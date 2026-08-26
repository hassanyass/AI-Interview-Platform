---
name: transition-phase
description: Runs one phase of the Path2Hire B2C-to-B2B transition (docs/path2hire-transition-plan.md). Use whenever the user asks to work on "Transition Phase N", references the transition plan, or asks to continue the B2B migration. Enforces explore-then-plan-then-execute-then-verify, and checks CURRENT_DECISIONS.md before assuming any product decision.
---

# Path2Hire Transition Phase Skill

This skill governs how to execute any numbered phase of the B2C→B2B transition. It exists because this codebase has coupled, high-risk areas (the LiveKit Agent Worker contract, the InterviewSession/CandidateProfile coupling) where an unreviewed change can silently break a working feature.

## When to use this skill
- The user says "Transition Phase N", "let's do phase N", or similar, referencing docs/path2hire-transition-plan.md.
- The user asks to continue the B2B migration work generally.

## How to run a phase

1. **Read ground truth first, every time** — do not rely on memory from earlier in this conversation:
   - `AGENTS.md`
   - `docs/path2hire-transition-plan.md`
   - `docs/CURRENT_DECISIONS.md`

2. **Locate the exact phase.** Find "Transition Phase <N>" in the plan. This is the entire scope for this task — nothing more. If the requested phase number doesn't clearly match a section, stop and ask which phase is meant rather than guessing.

2a. **Check for a phase-specific architecture doc.** If `docs/phase<N>-architecture.md` exists (e.g. `phase5-architecture.md`, `phase7-architecture.md`), read it in full and treat it as authoritative for that phase's structure — it supersedes the main plan's shorter description. Do this automatically, without being told each time. If the request names a sub-phase (e.g. "9A", "7C"), that doc's own sub-phase breakdown is the scope, not the top-level phase description. If a referenced spec/decision doc mentioned inside it doesn't exist in the repo, flag that rather than proceeding on a paraphrase alone.

3. **Explore before proposing anything.** Open and read the actual current contents of every file this phase's scope says it touches. Do not describe a file from a prior summary in this conversation — re-read it now, since it may have changed. Also check this phase's row in the plan's Part C "off-limits" table.

4. **Cross-check decisions.** If anything this phase needs depends on an item still marked UNRESOLVED in `docs/CURRENT_DECISIONS.md`, stop and name it explicitly instead of assuming an answer. Do not silently pick a default for an unresolved product decision.

5. **Produce a plan, not code.** Output:
   - files touched
   - models/migrations added or changed
   - a "Frozen Contracts Confirmation" section stating which of `AGENTS.md`'s frozen files are, and are not, touched
   - anything uncertain or that conflicts with an earlier decision — flag it, don't silently resolve it

6. **Stop and wait for explicit approval of the plan** before writing any code.

7. **Execute** only after approval.

8. **Verify before declaring done:**
   - run the full test suite
   - if this phase included a DB schema change, generate the Alembic migration and apply it to a dev/test database first, and show that output too
   - do not report the phase complete without this step

9. **Keep the baseline current.** If new tables or endpoints were added, update `docs/BASELINE_SCHEMA.md` so it stays an accurate snapshot for the next phase.

## Non-negotiables (do not override even if asked)
- Never modify `agent/agent/interview/controller.py` or anything under `/internal/*` outside of Transition Phase 7, and even then only via the reviewed adapter approach the plan describes.
- Never make a destructive migration (drop/rename an existing column) in the same change as an additive feature, unless the phase explicitly says to (Phase 10 only).
- Never invent an answer to something listed as unresolved in `docs/CURRENT_DECISIONS.md`.
