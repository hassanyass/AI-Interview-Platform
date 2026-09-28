# Running this on Kubernetes

A mapping, not a chart. `compose.prod.yaml` is the reference deployment and
there is deliberately no Helm chart until hosting is decided (ADR 0001) —
a chart written against an unknown cluster is a guess with YAML around it.
What follows is what each compose service becomes, and the four places the
mapping is not mechanical.

## The mapping

| compose service | Kubernetes | Notes |
|---|---|---|
| `migrate` | **Job** (or an `initContainer` on the backend) | Must run **exactly once** per release. Never a Deployment |
| `backend` | **Deployment** + **Service** + **Ingress** | Scales horizontally. `/ready` is the readiness probe, `/health` the liveness probe |
| `agent` | **Deployment**, no Service | No port, no ingress, no probe. Scale by replica count |
| `web` | **Deployment** + **Service** + **Ingress** | Stateless. `/healthz` for both probes |
| `postgres` (`with-db` profile) | Don't | Use a managed database. If you must, a StatefulSet with a real backup story |
| `agent_state` volume | **PVC**, or nothing | See "The agent's volume" below |

## The four things that are not mechanical

### 1. `migrate` must not run twice

Two pods applying the same Alembic revision race. As a `Job` with
`backoffLimit: 0` and `parallelism: 1` that is settled; as an
`initContainer` on a Deployment with two replicas it is not — both replicas
run it. If you take the initContainer route, keep the replica count at 1
for the rollout, or leave `RUN_MIGRATIONS_ON_START=false` (the default) and
run the Job.

The backend must not start before it finishes. In compose that is
`depends_on: service_completed_successfully`; in Kubernetes it is a Job you
wait on, or an initContainer.

### 2. The agent has nothing to probe

It binds no port. It proves it is alive by registering with LiveKit and
renewing session leases — neither of which a kubelet can see. Options, in
order of honesty:

- **No probes.** The container exits on a fatal error and the restart policy
  handles it. This is what the compose stack does.
- A liveness probe on process presence (`exec: pgrep -f agent.main`), which
  tells you the process exists, not that it is working.
- Do **not** invent an HTTP endpoint for the probe's benefit. A worker that
  answers a health check while failing to renew its lease is worse than one
  with no probe, because it looks fine.

Watch `sweep_finalized_total` and the agent's own log stream instead
(`observability.md`).

### 3. Draining an agent takes as long as an interview

A rolling update terminates agent pods. A pod handling a live interview
ends that candidate's session: the teardown writes `DISCONNECTED`, the
candidate sees the reconnect screen, and the sweep finalises it after
`DISCONNECT_AUTO_FINALIZE_MINUTES`.

Set `terminationGracePeriodSeconds` to longer than a whole interview (the
default is 30 seconds — an interview is 15–45 minutes) if you want in-flight
interviews to finish. Otherwise deploy the agent when nobody is
interviewing. There is no drain-and-wait mechanism in the worker; LiveKit
stops dispatching to a worker that unregisters, but the job it already has
keeps running.

### 4. Rate limits multiply by replica count

The token buckets live in process memory (`core/ratelimit.py`). Three
backend replicas enforce three times every limit in `env-matrix.md`. Either
divide the configured limits by the replica count, or replace the store —
the module says how. Nothing else in the backend has this property: the
sweep takes an advisory lock, finalization locks its row, and tasks are
claimed with `SKIP LOCKED`.

## The agent's volume

`AGENT_STATE_DIR` holds the Groq key-rotation index and the TTS cache. Both
rebuild themselves, so a PVC is an optimisation rather than a requirement:

- **No volume** — simplest. Each pod re-warms its own TTS cache, and key
  rotation restarts at the first key on every restart, which is fine unless
  you are near a daily quota.
- **A PVC per pod** (StatefulSet, or `volumeClaimTemplates`) — keeps both
  across restarts. **Not** one `ReadWriteMany` claim shared by replicas: two
  workers writing one rotation-state file overwrite each other, which is the
  failure the per-namespace state files exist to avoid.

The image runs as uid 10001 and owns that directory; a volume mounted over
it needs `fsGroup: 10001` in the pod security context, or the same
permission failure the compose upgrade note describes.

## Configuration and secrets

`env-matrix.md` marks which settings are required and which are
fail-closed. Split them:

- **ConfigMap** — everything non-secret: `ENVIRONMENT`, `LOG_FORMAT`,
  timeouts, limits, model names, `BACKEND_CORS_ORIGINS`.
- **Secret** — `SECRET_KEY`, `AGENT_API_SECRET`, `DATABASE_URL`,
  `SUPABASE_SECRET_KEY`, `LIVEKIT_API_*`, `R2_*`, `GROQ_API_KEY*`,
  `AZURE_SPEECH_KEY`.

The backend and the agent need the *same* `AGENT_API_SECRET`; mount it from
one Secret rather than defining it twice.

The `web` pod takes only `VITE_*` values, all of which reach the browser —
a ConfigMap, never a Secret. Changing one needs a pod restart, not a
rebuild (the container writes `/config.js` at start-up).

## Ingress

Two hostnames, matching `deploy.md`:

| Host | Service | Port |
|---|---|---|
| `hire.example.com` | `web` | 8080 |
| `api.hire.example.com` | `backend` | 8001 |

Then:

- TLS at the ingress. Add HSTS there, not in the container.
- **Do not expose `/metrics`** — unauthenticated by design. Deny it at the
  ingress and scrape the pod directly, or set `METRICS_ENABLED=false` on
  public replicas.
- Consider denying `/docs` and `/openapi.json` (`security.md` §7, item 9).
- Forward `X-Forwarded-For`, or every caller shares one rate-limit bucket.
  The backend already runs uvicorn with `--proxy-headers`.

## Probes, concretely

```yaml
# backend
readinessProbe:
  httpGet: { path: /ready, port: 8001 }
  initialDelaySeconds: 10
  periodSeconds: 10
livenessProbe:
  httpGet: { path: /health, port: 8001 }   # never touches the database
  periodSeconds: 20

# web
readinessProbe:
  httpGet: { path: /healthz, port: 8080 }
```

`/ready` reports the database, so it is the readiness probe; `/health`
deliberately does not, so a database blip restarts nothing (H2-B).

## What is still missing for a real cluster

Stated plainly rather than implied: no manifests, no chart, no
`NetworkPolicy`, no `PodDisruptionBudget`, no HPA, and no capacity numbers
to size one from (U4). This document is the mapping; the manifests belong
to whoever knows the cluster.
