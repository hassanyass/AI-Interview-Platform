# ADR 0008 — Keep handover documentation tracked, in docs/handover/

- **Status:** Accepted
- **Decided:** 2026-09-17
- **Source:** `docs/production-hardening-plan.md` §0, decision S8

## Context

The richest operational context lived in `CLAUDE.md` and `AGENTS.md`, which are
deliberately git-ignored, and in session transcripts. Neither reaches whoever operates
this next.

## Decision

Everything an operator needs goes in a tracked `docs/handover/`: runbooks,
observability, security, deploy, the env matrix, ADRs.

## Consequences

- Written for a stranger, not as a reminder for whoever wrote the code.
- Each runbook is executed once when written, so the commands are real.
- Documentation that can drift should be generated; hand-written files decay.

## How it turned out

Nine runbooks, plus observability, security and deploy guides. The generated pair
(`env-matrix.md`, `data-model.md`) exists because the hand-written data model had
named three tables that never existed and omitted fifteen that did — a test now fails
when either drifts.
