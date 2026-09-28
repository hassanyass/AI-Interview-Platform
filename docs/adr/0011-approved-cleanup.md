# ADR 0011 — Delete dead code and stray artefacts, with the list approved first

- **Status:** Accepted — implemented in H0-B
- **Decided:** 2026-09-17
- **Source:** `docs/production-hardening-plan.md` §0, decision S11

## Context

The repository carried dead frontend code, stray root artefacts, a `test_5c.cjs` and a
`New Avatar/` directory. Any of them might have been load-bearing.

## Decision

Show the exact list for approval before removing anything, and remove nothing that is
merely suspected of being unused.

## Consequences

- A round trip before deletion.
- Deletions are recorded in the phase's verify record, so any of them can be undone.

## How it turned out

Applied again later and found something worth finding: the `blaze_face_short_range`
model was safely removable (229 KB, dead by the code's own comment), while the 35 MB
of WASM around it was not — three variants MediaPipe chooses between at runtime.
