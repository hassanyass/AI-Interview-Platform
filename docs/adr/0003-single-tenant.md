# ADR 0003 — Stay single-tenant, with one admin role

- **Status:** Accepted
- **Decided:** 2026-09-17
- **Source:** `docs/production-hardening-plan.md` §0, decision S3

## Context

One organisation, one hiring flow. Multi-tenancy, white-labelling and a richer
permission model were all raised and all deferred.

## Decision

No tenancy column, no organisation entity, no RBAC expansion. The existing `admin`
role in `users_roles` stays as the only privileged role.

## Consequences

- Every admin can see every job and every candidate; there is no per-job scoping.
- Adding tenancy later means a schema change on nearly every table, which is a
  reason to decide it before there is production data rather than after.

## How it turned out

Held throughout. The auth matrix has exactly four classes (admin, candidate, agent,
public), which is what made `test_auth_matrix.py` able to assert on the whole route
table rather than a list of special cases.
