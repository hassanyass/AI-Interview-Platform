# Capacity baseline

What the HTTP layer sustained when measured, what that number is worth, and
the one measurement that is still missing.

Produced by `scripts/load_baseline.py` (`make load-baseline`). Re-run it
after any change to the request path, and **re-run it on the machine you
actually deploy to** — the section below on what these numbers are worth is
not a disclaimer, it is the main finding.

## How it was measured

The script drives the path a real applicant takes: the public job preview,
registration, an authenticated session read, and the room token. At each
concurrency level it fires a fixed number of requests and reports what the
client observed.

Two things are arranged so the measurement is about this system rather than
about someone else's:

- **Recordings are off.** `R2_*` is unset, so `storage.configured` is false
  and `start_recording_egress` returns immediately. No LiveKit egress is
  started and nothing is written to R2. Token *minting* is local JWT
  signing, so it costs nothing either.
- **The CV gate is satisfied by seeding the resume row**, not by uploading a
  CV. The real upload runs a Groq extraction, which would make this a
  measurement of Groq's latency.

Rate limiting is disabled for the run (`RATE_LIMIT_ENABLED=false`);
otherwise registration caps at 20/minute per address and a local run is one
address. That the limits work is covered separately — `test_rate_limit.py`,
and the live check in the hardening plan §24.

### The environment these numbers come from

| | |
|---|---|
| Host | Windows 11 laptop, Docker Desktop |
| Backend | one `uvicorn` worker, no reload, `--log-level warning` |
| Database | `postgres:15` in Docker Desktop (the disposable `postgres-test`), pool 5 + 10 overflow |
| Load generator | the same laptop, one Python process |
| Also running | the frozen v3 demo stack (five containers) |
| Date | 2026-09-25 |

## What was measured

Client-observed, 120 requests per endpoint per level. Every response was a
2xx: **zero errors at every level**, including 40 concurrent.

| Concurrency | `GET /apply/{token}` p50 / p95 | `POST /register` p50 / p95 | `GET /interviews/{id}` p50 / p95 | `POST /livekit/token` p50 / p95 | req/s |
|---|---|---|---|---|---|
| 1 | 64 / 116 ms | 207 / 368 ms | 109 / 195 ms | 67 / 107 ms | 3.5 – 5.3 |
| 5 | 165 / 394 ms | 478 / 696 ms | — | — | 7.1 |
| 10 | 355 / 1485 ms | 1154 / 3878 ms | 656 / 2016 ms | 430 / 716 ms | 5.5 – 8.0 |
| 20 | 820 / 4412 ms | 1920 / 2736 ms | 1114 / 3977 ms | 777 / 1427 ms | 5.7 – 7.7 |
| 40 | 3018 / 6836 ms | 2472 / 6400 ms | 1573 / 4466 ms | 846 / 2716 ms | 6.1 – 12.1 |

Floor, for reference: `GET /health` (touches nothing) — 200 requests at 20
concurrent, p50 **390 ms**, 41 req/s.

## What these numbers are worth

**Read this before quoting any of the above.**

Throughput is flat at roughly 6–12 req/s from concurrency 1 to 40 while
latency rises in proportion. That is the signature of a serialised
bottleneck, not of a capacity limit — and with zero errors, nothing was
saturating. So the next question is where the time goes, and the server's
own histogram answers it:

| Route | Server-measured mean | |
|---|---|---|
| `GET /health` | **4.0 ms** | FastAPI itself, no database |
| `POST /livekit/token` | 523 ms | database |
| `GET /apply/{token}` | 775 ms | database |
| `GET /interviews/{id}` | 967 ms | database |
| `POST /apply/{token}/register` | 1083 ms | database, several writes and a commit |

The framework costs ~4 ms. Everything else is waiting on the database. At
concurrency 1 a single round trip to the Dockerised Postgres measured
~28 ms — on Docker Desktop for Windows, where database traffic crosses a
virtual network — and registration performs several of them. Under load,
the pool (5 + 10 overflow) then queues 40 concurrent requests into batches
of 15.

So these figures measure **this laptop**, not the application:

- The ~4 ms framework overhead and the *shape* of the curve transfer.
- The absolute latencies and the 6–12 req/s ceiling do **not**. On a Linux
  host with the database on a local socket or a low-latency network, the
  same per-request work costs single-digit milliseconds, and the same pool
  serves an order of magnitude more.
- The load generator shared the machine with the server and with five demo
  containers, which inflates everything including the 390 ms `/health` p50
  (server-measured: 4 ms).

**To get a number you can size a deployment from:** run the script from a
separate host against a Linux deployment with the real managed database,
and raise `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` from their defaults if the
pool is the queueing point.

## The ceiling that does transfer

One production limit is already known and is not about host speed. During
H5-B, 40 concurrent registrations against the **Supabase pooler** produced:

```
asyncpg.exceptions.InternalServerError: (EMAXCONNSESSION)
max clients reached in session mode - max clients are limited to pool_size: 15
```

That is the managed pooler's own ceiling, and it is lower than anything in
this application. Two consequences:

- A rate-limit burst the API permits (`RATE_LIMIT_PUBLIC_REGISTER`, 20 by
  default) can exceed the number of database clients available. Choose the
  two together for a given deployment.
- That failure surfaces as an unhandled **500**, not a 503. Mapping it is
  recorded as open in `security.md` §7 (item 4).

## Still unmeasured: interviews per agent worker (U4)

The number that actually decides how many candidates can interview at once
is **not** in this document, and cannot be produced from this repository.
`agent/agent/interview/simulator.py` — which the hardening plan expected to
use — is an interactive CLI text simulator with `MockPersistence` and no
LiveKit at all. It cannot drive a room.

A real measurement needs, and this is the procedure:

1. **A staging LiveKit project**, separate from production. Two workers
   registered to one project both receive jobs, so this must not share with
   anything live — including the booth demo.
2. **Clients that publish real audio.** A room with a participant that
   sends no audio exercises none of the STT, turn-taking or TTS path.
   Either N headless browsers against a published job, or a LiveKit client
   script publishing a recorded WAV on a loop.
3. **Groq budget.** Every simulated interview consumes STT, LLM and TTS.
   Estimate from `[LLM-METRICS]`/`[STT-METRICS]`/`[TTS-METRICS]` in the
   agent log for one real interview before running many.
4. **One worker, rising session count.** Start at 1 and add sessions until
   one of these degrades:
   - `[STT-METRICS] duration_ms` or `[TTS-METRICS] ttfb_ms` climbing — the
     candidate hears the interviewer get slower;
   - `Lease renewal failed` in the agent log — it is losing its grip on
     sessions, and after `LEASE_ERROR_SHUTDOWN_AFTER` it stops driving one;
   - `sweep_finalized_total` rising on `/metrics` — sessions are being
     abandoned and cleaned up rather than finishing;
   - worker RSS approaching `JOB_MEMORY_LIMIT_MB`, if that is set.
5. **Record the last count at which all four stayed clean**, and the
   provider cost per interview. That number, against expected concurrent
   demand, is the U4 acceptance question — a product call, not a technical
   one.

Until that is done, the honest answer to "how many candidates can interview
simultaneously?" is that nobody has measured it. Scale the agent by replica
count and watch the four signals above.

## Reproducing this

```bash
make load-baseline
```

Which is, in full:

```bash
docker compose up -d --wait postgres-test
cd backend && DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/himma_test \
  RATE_LIMIT_ENABLED=false R2_ENDPOINT= R2_ACCOUNT_ID= R2_ACCESS_KEY_ID= \
  R2_SECRET_ACCESS_KEY= R2_BUCKET_NAME= TASK_WORKER_ENABLED=false \
  python -m uvicorn backend.main:app --host 127.0.0.1 --port 8002 --log-level warning
# then, in another shell:
python scripts/load_baseline.py --base-url http://127.0.0.1:8002
```

The script refuses to run against a Supabase host, and deletes every
profile, session and job it creates.
