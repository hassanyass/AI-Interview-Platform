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

1. Read ground truth first, every time — do not rely on memory from earlier in this conversation: AGENTS.md, docs/path2hire-transition-plan.md, docs/CURRENT_DECISIONS.md.
2. Locate the exact phase. Find "Transition Phase <N>" in the plan. This is the entire scope for this task. If the requested phase number doesn't clearly match a section, stop and ask which phase is meant rather than guessing.
3. Explore before proposing anything. Open and read the actual current contents of every file this phase touches. Re-read live files, don't rely on prior summaries. Check the plan's Part C "off-limits" table for this phase.
4. Cross-check decisions. If anything depends on an item still marked UNRESOLVED in docs/CURRENT_DECISIONS.md, stop and name it explicitly instead of assuming an answer.
5. Produce a plan, not code: files touched, models/migrations added or changed, a "Frozen Contracts Confirmation" section, and anything uncertain flagged rather than silently resolved.
6. Stop and wait for explicit approval of the plan before writing any code.
7. Execute only after approval.
8. Verify before declaring done: run the full test suite; if a DB schema change was made, generate and apply the Alembic migration to a dev/test database first and show that output too.
9. If new tables or endpoints were added, update docs/BASELINE_SCHEMA.md.

## Non-negotiables
- agent/agent/interview/controller.py and anything under /internal/* are frozen by default — modifications require an active, approved sub-phase plan that explicitly scopes touching them, same as any other file this skill governs.
- Never make a destructive migration in the same change as an additive feature, unless the phase explicitly says to (Phase 10 only).
- Never invent an answer to something listed as unresolved in docs/CURRENT_DECISIONS.md.
