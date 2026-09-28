# ADR 0002 — Size for 1000+ candidates in total, with no concurrency target

- **Status:** Accepted — measurement outstanding (U4)
- **Decided:** 2026-09-17
- **Source:** `docs/production-hardening-plan.md` §0, decision S2

## Context

The load is a single organisation's hiring: on the order of a thousand candidates in
total, not a consumer product. No simultaneous-interview target was given.

## Decision

Do no autoscaling work. Measure a baseline instead — how many concurrent live
interviews one agent worker sustains — and record it for the operator to judge.

## Consequences

- In-process solutions are acceptable where a distributed one would be premature:
  the rate limiter and the task worker both live in the API process.
- Whether the measured number is *enough* is a product call, kept open as U4.

## How it turned out

Still open. H6-C measures the HTTP side; the agent-concurrency half needs a staging
LiveKit project and real provider spend, so it is written up as a procedure rather
than guessed. One number arrived unasked-for during H5-B: the Supabase pooler
refuses connections past 15 in session mode, which is a lower ceiling than anything
in the application.
