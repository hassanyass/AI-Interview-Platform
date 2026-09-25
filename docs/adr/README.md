# Architecture decision records

The twelve architectural decisions the production-hardening initiative was
built on (S1–S12 of `docs/production-hardening-plan.md`), one file each,
with what each one turned out to mean now that all of them are implemented.

These cover **architecture**. `docs/CURRENT_DECISIONS.md` remains the
**product** decision log — anonymous versus authenticated candidates, the
email provider, retake policy, evaluation regeneration — and is not
duplicated here. Where a product decision constrains the architecture, the
ADR links to it.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-portable-container-stack.md) | Ship a portable container stack, not a cloud-specific deploy | Accepted — implemented in H6-A |
| [0002](0002-no-concurrency-target.md) | Size for 1000+ candidates in total, with no concurrency target | Accepted — measurement outstanding (U4) |
| [0003](0003-single-tenant.md) | Stay single-tenant, with one admin role | Accepted |
| [0004](0004-priority-order.md) | Order the work reliability → observability → tests → security | Accepted — followed through H5 |
| [0005](0005-provider-ports.md) | Fix the stack at FastAPI and React; put every vendor behind a port | Accepted — implemented in H1 |
| [0006](0006-inert-email-provider.md) | Build the email integration point, leave it inert | Accepted |
| [0007](0007-real-disposable-postgres.md) | Test against a real disposable Postgres, not mocks | Accepted — implemented in H0-A |
| [0008](0008-tracked-handover-docs.md) | Keep handover documentation tracked, in docs/handover/ | Accepted |
| [0009](0009-db-backed-task-queue.md) | Use a database-backed task queue, not Redis or Celery | Accepted — implemented in H2-F |
| [0010](0010-legacy-tests-moved-unchanged.md) | Move the phase-by-phase suites to tests/legacy/, unchanged | Accepted — implemented in H0 |
| [0011](0011-approved-cleanup.md) | Delete dead code and stray artefacts, with the list approved first | Accepted — implemented in H0-B |
| [0012](0012-frozen-controller.md) | Freeze controller.py; change it only in one approved sub-phase | Accepted — one sub-phase used (H2-C) |

Open questions that are deliberately *not* decided are tracked as U1–U5 in
the hardening plan. U1 (data retention) is the one that still blocks
shipped behaviour: the purge job exists and is switched off.
