# ADR 0006 — Build the email integration point, leave it inert

- **Status:** Accepted
- **Decided:** 2026-09-17
- **Source:** `docs/production-hardening-plan.md` §0, decision S6

## Context

Invitations are logged to the console rather than sent. Choosing an email vendor is a
product decision (P1 in `CURRENT_DECISIONS.md`) that was not ready to be made, but
the shape of the gap was known.

## Decision

Ship the `EmailProvider` port with a `NullEmailProvider` that logs and reports
not-sent. Behaviour does not change: the composer's Send button keeps its current
outcome.

## Consequences

- Adding a vendor later is an adapter, not a redesign.
- Anything that depends on real email stays blocked: invitation delivery, and the
  email-verification round trip a self-service address change would need.

## How it turned out

Still inert. It constrained a later decision in a way nobody predicted: H5-A wanted
to require re-verification before a candidate could change their profile email, and
could not — so the field was removed from the update schema instead.
