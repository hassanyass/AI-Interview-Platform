"""Measure what the HTTP layer sustains (H6-C).

    python scripts/load_baseline.py --base-url http://127.0.0.1:8002

Drives the candidate-facing path a real applicant takes -- the public
preview, registration, the room token and an authenticated read -- at
rising concurrency, and reports per-endpoint percentiles and error
breakdowns. The output is meant to be pasted into
`docs/handover/capacity.md` verbatim.

**What this does not measure.** The agent. How many simultaneous live
interviews one worker sustains is U4, needs a staging LiveKit project and
real audio, and is written up as a procedure in capacity.md rather than
guessed at here. Nor does it measure the LLM paths: an actual CV upload
runs a Groq extraction, so this seeds the resume row directly and leaves
the measured code path untouched.

**Run it against a disposable database.** Pointing this at a shared
Postgres writes hundreds of profiles and sessions into real data and eats
the connection pool everyone else is using. It refuses to start against a
Supabase host, the same rule conftest.py enforces for the test suites.

Setup and teardown are not measured: the fixture (a published public job)
is created before the run and everything created is deleted after.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

import httpx  # noqa: E402

DEFAULT_DB = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/himma_test"
LEVELS = (1, 5, 10, 20, 40)
REQUESTS_PER_LEVEL = 200


# ── results ───────────────────────────────────────────────────────────────

@dataclass
class Samples:
    label: str
    durations_ms: list[float] = field(default_factory=list)
    statuses: dict[int, int] = field(default_factory=dict)

    def record(self, status: int, duration_ms: float) -> None:
        self.durations_ms.append(duration_ms)
        self.statuses[status] = self.statuses.get(status, 0) + 1

    def percentile(self, p: float) -> float:
        if not self.durations_ms:
            return 0.0
        ordered = sorted(self.durations_ms)
        index = min(int(round(p / 100 * (len(ordered) - 1))), len(ordered) - 1)
        return ordered[index]

    @property
    def ok(self) -> int:
        return sum(count for status, count in self.statuses.items() if 200 <= status < 400)

    def row(self, elapsed_s: float) -> str:
        n = len(self.durations_ms)
        rps = n / elapsed_s if elapsed_s else 0.0
        statuses = " ".join(f"{status}×{count}" for status, count in sorted(self.statuses.items()))
        return (
            f"| {self.label} | {n} | {rps:.1f} | "
            f"{self.percentile(50):.0f} | {self.percentile(95):.0f} | {self.percentile(99):.0f} | "
            f"{max(self.durations_ms, default=0):.0f} | {statuses} |"
        )


async def timed(client: httpx.AsyncClient, samples: Samples, method: str, url: str, **kwargs):
    start = time.perf_counter()
    try:
        response = await client.request(method, url, **kwargs)
        status = response.status_code
    except Exception:  # noqa: BLE001 -- a transport failure is a data point, not a crash
        samples.record(0, (time.perf_counter() - start) * 1000)
        return None
    samples.record(status, (time.perf_counter() - start) * 1000)
    return response


# ── fixture ───────────────────────────────────────────────────────────────

async def create_fixture(database_url: str) -> dict:
    """A published, public job with one verbal question. Direct inserts:
    this is setup, and going through the admin API would need a real admin
    credential."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import backend.db.base  # noqa: F401
    from backend.models.interview import (
        InterviewDefinition, InterviewQuestion, InterviewSection, Job,
    )

    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    token = secrets.token_urlsafe(32)
    async with session_factory() as db:
        job = Job(title="Load Baseline Job", seniority="mid", status="PUBLISHED",
                  required_skills=["Python"], language="en")
        db.add(job)
        await db.flush()
        definition = InterviewDefinition(
            job_id=job.id, duration_minutes=10, is_public=True, public_access_token=token,
        )
        db.add(definition)
        await db.flush()
        section = InterviewSection(
            definition_id=definition.id, section_type="VERBAL", order_index=0,
            config={"time_budget_minutes": 10},
        )
        db.add(section)
        await db.flush()
        db.add(InterviewQuestion(
            section_id=section.id, order_index=0, title="Q", text="Tell me about a service you built.",
        ))
        await db.commit()
        ids = {"job_id": job.id, "token": token}
    await engine.dispose()
    return ids


async def attach_resumes(database_url: str, emails: list[str]) -> int:
    """Satisfy the CV gate without a Groq call. The gate reads
    `application.resume_id`; the upload endpoint that normally sets it runs
    an LLM extraction, which would make this a measurement of Groq."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import backend.db.base  # noqa: F401
    from backend.models.interview import JobApplication
    from backend.models.profile import CandidateProfile, Resume

    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    attached = 0
    async with session_factory() as db:
        profiles = (await db.execute(
            select(CandidateProfile).where(CandidateProfile.email.in_(emails))
        )).scalars().all()
        for profile in profiles:
            resume = Resume(
                profile_id=profile.id, original_filename="baseline.pdf",
                storage_path=f"users/{profile.id}/baseline.pdf", extraction_status="COMPLETED",
            )
            db.add(resume)
            await db.flush()
            applications = (await db.execute(
                select(JobApplication).where(JobApplication.candidate_profile_id == profile.id)
            )).scalars().all()
            for application in applications:
                application.resume_id = resume.id
                attached += 1
        await db.commit()
    await engine.dispose()
    return attached


async def delete_fixture(database_url: str, job_id, emails: list[str]) -> dict:
    from sqlalchemy import delete, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import backend.db.base  # noqa: F401
    from backend.models.interview import InterviewSession, Job
    from backend.models.profile import CandidateProfile

    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        sessions = len((await db.execute(
            select(InterviewSession.id).join(
                CandidateProfile, CandidateProfile.id == InterviewSession.candidate_profile_id
            ).where(CandidateProfile.email.in_(emails))
        )).all())
        profiles = (await db.execute(
            delete(CandidateProfile).where(CandidateProfile.email.in_(emails))
        )).rowcount
        jobs = (await db.execute(delete(Job).where(Job.id == job_id))).rowcount
        await db.commit()
    await engine.dispose()
    return {"profiles": profiles, "sessions": sessions, "jobs": jobs}


# ── the run ───────────────────────────────────────────────────────────────

async def run_level(base_url: str, token: str, concurrency: int, total: int) -> tuple[dict[str, Samples], float, list[dict]]:
    preview = Samples("GET /apply/{token}")
    register = Samples("POST /apply/{token}/register")
    limits = httpx.Limits(max_connections=concurrency * 2, max_keepalive_connections=concurrency * 2)
    registered: list[dict] = []
    lock = asyncio.Lock()

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0, limits=limits) as client:
        semaphore = asyncio.Semaphore(concurrency)

        async def one(index: int) -> None:
            async with semaphore:
                await timed(client, preview, "GET", f"/api/v1/apply/{token}")
                # Not a reserved TLD: `email-validator` rejects .invalid/.test
                # outright, which arrives as a 422 and measures nothing.
                email = f"load-{uuid.uuid4().hex[:12]}@load.example.com"
                response = await timed(
                    client, register, "POST", f"/api/v1/apply/{token}/register",
                    json={"name": "Load Baseline", "email": email},
                )
                if response is not None and response.status_code == 200:
                    body = response.json()
                    async with lock:
                        registered.append({
                            "email": email,
                            "session_id": body["session"]["id"],
                            "access_token": body["access_token"],
                        })

        start = time.perf_counter()
        await asyncio.gather(*[one(i) for i in range(total)])
        elapsed = time.perf_counter() - start

    return {"preview": preview, "register": register}, elapsed, registered


async def run_authenticated(base_url: str, people: list[dict], concurrency: int) -> tuple[dict[str, Samples], float]:
    token_samples = Samples("POST /livekit/token")
    read_samples = Samples("GET /interviews/{id}")
    limits = httpx.Limits(max_connections=concurrency * 2, max_keepalive_connections=concurrency * 2)

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0, limits=limits) as client:
        semaphore = asyncio.Semaphore(concurrency)

        async def one(person: dict) -> None:
            headers = {"Authorization": f"Bearer {person['access_token']}"}
            async with semaphore:
                await timed(client, read_samples, "GET",
                            f"/api/v1/interviews/{person['session_id']}", headers=headers)
                await timed(client, token_samples, "POST", "/api/v1/livekit/token",
                            json={"session_id": person["session_id"]}, headers=headers)

        start = time.perf_counter()
        await asyncio.gather(*[one(p) for p in people])
        elapsed = time.perf_counter() - start

    return {"read": read_samples, "token": token_samples}, elapsed


async def floor(base_url: str, concurrency: int, total: int) -> tuple[Samples, float]:
    samples = Samples("GET /health")
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0,
                                 limits=httpx.Limits(max_connections=concurrency * 2)) as client:
        semaphore = asyncio.Semaphore(concurrency)

        async def one() -> None:
            async with semaphore:
                await timed(client, samples, "GET", "/health")

        start = time.perf_counter()
        await asyncio.gather(*[one() for _ in range(total)])
        elapsed = time.perf_counter() - start
    return samples, elapsed


HEADER = "| Endpoint | Requests | req/s | p50 ms | p95 ms | p99 ms | max ms | Statuses |"
DIVIDER = "|---|---|---|---|---|---|---|---|"


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:8002")
    parser.add_argument("--database-url", default=os.environ.get("TEST_DATABASE_URL", DEFAULT_DB))
    parser.add_argument("--levels", default=",".join(str(level) for level in LEVELS))
    parser.add_argument("--requests", type=int, default=REQUESTS_PER_LEVEL)
    args = parser.parse_args(argv)

    host = (urlsplit(args.database_url).hostname or "").lower()
    if "supabase" in host:
        print(f"Refusing to load-test against a Supabase host ({host}). Use a disposable database.")
        return 2

    levels = [int(level) for level in args.levels.split(",")]

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            ready = await client.get(f"{args.base_url}/ready")
        except Exception as error:  # noqa: BLE001
            print(f"No backend at {args.base_url}: {error}")
            return 2
    print(f"backend at {args.base_url}: /ready -> {ready.status_code} {ready.text.strip()}")

    fixture = await create_fixture(args.database_url)
    print(f"fixture: public job {fixture['job_id']}")
    emails: list[str] = []

    try:
        health, elapsed = await floor(args.base_url, concurrency=20, total=200)
        print(f"\n### Floor — GET /health, 200 requests at 20 concurrent\n\n{HEADER}\n{DIVIDER}")
        print(health.row(elapsed))

        for concurrency in levels:
            print(f"\n### Candidate registration — {args.requests} requests at {concurrency} concurrent\n")
            print(f"{HEADER}\n{DIVIDER}")
            results, elapsed, people = await run_level(args.base_url, fixture["token"], concurrency, args.requests)
            for samples in results.values():
                print(samples.row(elapsed))
            emails.extend(person["email"] for person in people)

            if people:
                attached = await attach_resumes(args.database_url, [p["email"] for p in people])
                print(f"\n### Authenticated calls — {len(people)} sessions at {concurrency} concurrent")
                print(f"_CV gate satisfied for {attached} application(s) by seeding the resume row._\n")
                print(f"{HEADER}\n{DIVIDER}")
                auth_results, auth_elapsed = await run_authenticated(args.base_url, people, concurrency)
                for samples in auth_results.values():
                    print(samples.row(auth_elapsed))
    finally:
        removed = await delete_fixture(args.database_url, fixture["job_id"], emails)
        print(f"\ncleanup: removed {removed['profiles']} profile(s), "
              f"{removed['sessions']} session(s), {removed['jobs']} job(s)")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
