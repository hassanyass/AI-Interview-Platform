# ADR 0001 — Ship a portable container stack, not a cloud-specific deploy

- **Status:** Accepted — implemented in H6-A
- **Decided:** 2026-09-17
- **Source:** `docs/production-hardening-plan.md` §0, decision S1

## Context

The prototype was deployed to Render (backend, agent) and Vercel (frontend), with a
`render.yaml` whose own header recorded that Blueprints ask for a credit card even for
free-tier services. Long-term hosting was explicitly undecided, and explicitly not
Render, Vercel or Railway.

## Decision

Make the deliverable a container stack that runs on any Docker host, mappable to
Kubernetes, with nothing provider-specific in the images or the compose files.

## Consequences

- No provider SDKs, no platform-specific build hooks, no `$PORT` gymnastics.
- TLS, ingress and secret storage become the operator's, documented rather than coded.
- A second compose file is needed: development and production have genuinely
  different needs (bind mounts and a dev server versus built images and restarts).

## How it turned out

`compose.prod.yaml` plus a built nginx image for the browser app (H6-A). `render.yaml`
and `DEPLOYMENT.md` were deleted; the two dated Render analyses were kept as history.
One thing the decision did not anticipate: Vite bakes `VITE_*` at build time, which
would have forced an image per environment. The web image writes `/config.js` from its
environment at start-up instead, so one artefact runs everywhere.
