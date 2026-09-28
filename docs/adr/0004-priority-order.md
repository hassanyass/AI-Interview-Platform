# ADR 0004 — Order the work reliability → observability → tests → security

- **Status:** Accepted — followed through H5
- **Decided:** 2026-09-17
- **Source:** `docs/production-hardening-plan.md` §0, decision S4

## Context

The audit found problems in every category at once. Doing them in an arbitrary order
risked building tests around behaviour that was about to change, or hardening code
paths that error handling had not yet reached.

## Decision

Reliability and error handling first, then observability and operations, then tests
and CI, then security and compliance — after two foundation phases (a runnable test
database, and typed configuration with provider ports) that everything depends on.

## Consequences

- Security work lands last, which is uncomfortable to write down but correct: the
  rejection paths H5 hardened did not exist in their final shape until H2.
- Each phase gets its own examine → plan → confirm → verify cycle.

## How it turned out

Followed exactly: H0, H1, H2 (A–F), H3, H4 (A–B), H5 (A–C), H6 (A–). The order paid
off most visibly in H4: the auth matrix could be written against a route table that
H2-A had already made consistent.
