# Deploying Path2Hire

Replaces the old `DEPLOYMENT.md` and `render.yaml`, both of which
described a Vercel/Render prototype deploy and were removed in H6-A. This
is a portable container stack: anything that runs Docker will run it, and
nothing here is specific to a hosting provider.

## What you need

- A Docker host (Linux, 2 vCPU / 4 GB is comfortable for one worker).
- A Postgres 15 database. A managed one is expected; the stack can run its
  own for a demo (see "Without a managed database").
- Accounts and credentials for: Supabase (auth + CV storage), LiveKit
  (real-time media + recording), Groq (LLM/STT/TTS), an S3-compatible
  bucket for recordings (Cloudflare R2 today).
- A TLS-terminating proxy in front. **The stack does not terminate TLS**,
  and both published ports bind to loopback on purpose.

Every setting is documented in `backend/.env.example`, `agent/.env.example`
and `frontend/.env.example`, each with a one-line comment. A generated
matrix (setting x environment, required or default) is H6-B.

## What is and is not swappable

Worth knowing before you plan a migration, because the answer differs by
concern.

| Concern | Port | Adapter today | Swappable |
|---|---|---|---|
| LLM / STT / TTS | `providers/llm` | `groq.py` | yes |
| Object storage (CVs, recordings) | `providers/storage` | `s3.py`, `supabase.py` | yes |
| Real-time media | `providers/realtime` | `livekit.py` | yes |
| Email | `providers/email` | `null.py` | yes — and **must** be, nothing is sent today |
| Notifications | `providers/notifications` | `console.py`, `email.py` | yes |
| Background jobs | `providers/queue` | `postgres.py` | yes |
| Database | — | PostgreSQL 15 via SQLAlchemy | any Postgres |
| **Authentication** | **none** | **Supabase Auth** | **no — see below** |

`runbooks/add-provider-adapter.md` is the procedure for the swappable ones.

### Authentication is a fixed dependency today

Supabase Auth is not behind a port. It is wired through
`backend/backend/core/security.py` (JWKS verification, `kid`-based
selection between Supabase and guest tokens), `core/config.py`,
`api/deps.py`, the `supabase_user_id` column on `candidate_profiles`, and
the frontend's `lib/supabase.ts` and `AuthContext`. Replacing it is a
project, not a setting.

This does **not** block a cloud migration: Supabase is a SaaS you can call
from any cloud, so the container stack still moves freely. It blocks a
*vendor* migration. If that becomes a requirement, the work is an `auth`
port with the same shape as the six above, plus a migration for the
profile column — plan it as its own phase, not as part of a move.

One more caveat on the ports that do exist: each has exactly one real
adapter. They are exercised by tests against fakes, which proves the seam
compiles and is honoured, not that a second vendor drops in cleanly.

## First deploy

```bash
git clone <this repo> && cd Himma_v2
cp backend/.env.example .env      # then fill it in
```

The backend refuses to start with a placeholder `SECRET_KEY`, an empty
`AGENT_API_SECRET` or LiveKit credential, or a `BACKEND_CORS_ORIGINS` that
is empty, contains `*` or still names localhost. That refusal is the
feature: a misconfigured deployment stops rather than serving.

```bash
docker compose -f compose.prod.yaml up -d --build
```

Order is enforced: `migrate` applies the Alembic chain and must exit 0,
then `backend` must pass `/ready`, then `agent` and `web` start.

Check it:

```bash
docker compose -f compose.prod.yaml ps
```

```bash
curl -s localhost:8001/ready && curl -s localhost:8080/healthz
```

```bash
docker compose -f compose.prod.yaml logs agent | grep -i "registered worker"
```

## The proxy in front

Terminate TLS and forward to the two loopback ports:

| Public path | Forward to | Notes |
|---|---|---|
| `https://hire.example.com/` | `127.0.0.1:8080` | the browser app |
| `https://api.hire.example.com/` | `127.0.0.1:8001` | the API |

Then:

- Set `BACKEND_CORS_ORIGINS` to the browser app's origin — exactly, with
  scheme, no trailing slash: `["https://hire.example.com"]`.
- Set `VITE_API_BASE_URL` to the API's public origin.
- Add HSTS **at the proxy**, not in the container: it depends on where TLS
  terminates and is hard to undo in a browser.
- **Do not expose `/metrics`.** It is unauthenticated by design. Allow it
  only from your scrape network, or set `METRICS_ENABLED=false` here and
  scrape a separate replica.
- **Consider closing `/docs` and `/openapi.json`.** They are public today
  (`security.md` §7, item 9).
- uvicorn runs with `--proxy-headers`, so rate limiting sees the real
  client address — but only if your proxy sets `X-Forwarded-For`. If it
  does not, every caller shares one bucket.

## One image, every environment

The `web` image is built once with placeholder values and writes
`/config.js` from its own environment at start-up, so the artefact you
tested in staging is the one that runs in production. Change
`VITE_API_BASE_URL` and restart the container — no rebuild:

```bash
docker compose -f compose.prod.yaml up -d --force-recreate web
```

Only `VITE_*` variables are written, and everything written reaches the
browser: put nothing secret there.

## Upgrading

1. Back up the database — `runbooks/restore-from-backup.md`.
2. Pull, then `docker compose -f compose.prod.yaml up -d --build`.
3. Verify `/ready`, `/healthz`, a registered worker, and no errors:
   `docker compose -f compose.prod.yaml logs --since 5m backend agent | grep '"level": "ERROR"'`.

Migrations are additive-only, so the previous release runs against the
newer schema and rollback is `git checkout` plus step 2.

**Once, when upgrading past H5-C:** the agent now runs unprivileged, and a
volume created by the older root image keeps root's ownership. If the
agent logs `Permission denied` under `/var/lib/himma-agent`, remove the
volume — both the TTS cache and the key-rotation index rebuild themselves:

```bash
docker compose -f compose.prod.yaml down && docker volume rm himma_agent_state
```

## Without a managed database

```bash
POSTGRES_PASSWORD=... docker compose -f compose.prod.yaml --profile with-db up -d --build
```

Point `DATABASE_URL` at `postgresql+asyncpg://postgres:...@postgres:5432/himma`.
The data lives in the `postgres_data` volume and is **not** backed up by
anything — set up `pg_dump` per `runbooks/restore-from-backup.md`.

## Scaling, and what does not scale

- `backend` scales horizontally: the disconnect sweep takes a Postgres
  advisory lock, finalization locks its row, and the task worker claims
  rows with `SKIP LOCKED`. Remove the fixed port mapping first — put the
  proxy on the compose network instead.
- Rate limits are **per process**: N replicas enforce N times the limit
  (`core/ratelimit.py` names the swap).
- `agent` scales by running more workers; LiveKit distributes jobs. How
  many live interviews one worker sustains has **not been measured** —
  that is U4 and `capacity.md`.
- `migrate` must never run more than once at a time.

## What the checks prove

These are the specific things that broke while this image was being built,
so they are worth re-running after any change to the nginx config:

```bash
curl -s -o /dev/null -w "%{http_code} %{content_type}\n" localhost:8080/admin/jobs/123
```

Must be `200 text/html` — the SPA fallback. A `types { }` block in the
nginx config replaces the whole MIME map and turns this into
`application/octet-stream`.

```bash
curl -s -o /dev/null -w "%{content_type}\n" localhost:8080/mediapipe/wasm/vision_wasm_internal.wasm
```

Must be `application/wasm`, or MediaPipe cannot instantiate and face
detection silently stops working.

```bash
curl -sI localhost:8080/ | grep -ciE "x-content-type|x-frame|referrer|permissions-policy|content-security"
```

Must be `5`. nginx replaces rather than merges `add_header`, so a location
block that sets its own Cache-Control drops every server-level security
header unless the snippet is included there too.

## Related

- `security.md` — what to close, what deletes personal data.
- `observability.md` — logs, metrics, health.
- `runbooks/` — start/stop, migrations, secrets, stuck sessions, outages,
  restores.
