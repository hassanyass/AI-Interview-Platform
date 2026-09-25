# ADR 0012 — Freeze controller.py; change it only in one approved sub-phase

- **Status:** Accepted — one sub-phase used (H2-C)
- **Decided:** 2026-09-17
- **Source:** `docs/production-hardening-plan.md` §0, decision S12

## Context

`agent/agent/interview/controller.py` is ~2,600 lines and holds the interview's
behaviour, tuned against live spoken sessions. The audit found real defects in it: an
`IM_READY` `NameError`, English fallback strings bypassing the language table, and
keyword intents that ended an interview directly from conversation.

## Decision

The file is frozen. Fixing those defects gets one scoped sub-phase with its own
line-level approval gate, and the wire contract does not change.

## Consequences

- Other phases test *around* the controller rather than editing it.
- The linter must not demand edits there either, so `ruff.toml` excludes it.
- Behaviour stays where it was proven, at the cost of some awkwardness elsewhere.

## How it turned out

Used once. H2-C changed 55 lines across seven hunks, each signed off individually,
with no contract change. The rule has held since: H5-B's `ui_command` allow-list went
into `voice_adapter.py`, and H4-B tested the controller's LLM-failure fallback without
touching it.
