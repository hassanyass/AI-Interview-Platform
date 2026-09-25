# ADR 0010 — Move the phase-by-phase suites to tests/legacy/, unchanged

- **Status:** Accepted — implemented in H0
- **Decided:** 2026-09-17
- **Source:** `docs/production-hardening-plan.md` §0, decision S10

## Context

Twenty `test_phase*.py` and `verify_9*.py` files sat at the repository root. They are
real regression coverage of the B2B transition, written against the live database, and
not in the style the project now uses.

## Decision

`git mv` them under `tests/legacy/` with no edits, point them at the test database,
and keep them green as regression coverage rather than rewriting or deleting them.

## Consequences

- They are collected on every run and must keep passing.
- Editing one needs explicit consent (AGENTS.md §7), which has been asked for and
  granted narrowly a handful of times.
- Two styles of test coexist, which is the price of not throwing away coverage.

## How it turned out

They repaid it. When H5-A first required a verified email before linking an identity,
three `test_phase6b` tests failed immediately and showed that personalised
invitations depend on that link — the finding that reshaped the whole design. No
hand-written new test would have caught it.
