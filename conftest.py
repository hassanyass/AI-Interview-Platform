"""Repo-wide pytest bootstrap: every DB-backed suite runs against the
disposable test database, never against the live one.

docs/production-hardening-plan.md H0-A. Before this file existed the
suites under backend/tests and tests/legacy used whatever DATABASE_URL the
root .env pointed at -- the shared Supabase project -- and relied on a
regex clean-up fixture (now tests/legacy/conftest.py) to remove what they
created. Two things happen here instead:

1. At import time -- i.e. before any test module imports `backend`, whose
   engine is built at import from `settings.DATABASE_URL` -- DATABASE_URL
   is overwritten with TEST_DATABASE_URL (default: the `postgres-test`
   service in docker-compose.yml). Environment variables beat the .env
   file in pydantic-settings, so no application code changes. If the
   resulting URL still points at a Supabase host the run is aborted.

2. Once per session, if any collected test lives under backend/tests or
   tests/legacy, the `public` schema is dropped and recreated and the
   real Alembic chain is applied (`alembic upgrade head`), so every run
   starts from an empty, current schema. Agent-only runs skip this.

Start the database with:  docker compose up -d postgres-test
"""
import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import pytest

REPO_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = REPO_ROOT / "backend"

DEFAULT_TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/himma_test"

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

_host = (urlsplit(TEST_DATABASE_URL).hostname or "").lower()
if "supabase" in _host:
    raise pytest.UsageError(
        "Refusing to run the test suites against a Supabase host "
        f"({_host}). Point TEST_DATABASE_URL at a disposable database "
        "(docker compose up -d postgres-test)."
    )

DB_TEST_DIRS = (REPO_ROOT / "backend" / "tests", REPO_ROOT / "tests" / "legacy")


def pytest_collection_modifyitems(session, config, items):
    session.needs_test_db = any(
        any(Path(str(item.fspath)).is_relative_to(d) for d in DB_TEST_DIRS) for item in items
    )


def _asyncpg_dsn(url: str) -> str:
    # asyncpg wants a plain postgresql:// DSN, not SQLAlchemy's +asyncpg scheme.
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _run(coro):
    # A private loop per call: nothing here may touch the loop pytest-asyncio
    # runs the tests on. asyncpg on Windows needs the selector loop.
    factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    with asyncio.Runner(loop_factory=factory) as runner:
        return runner.run(coro)


async def _wait_for_db(dsn: str, timeout_s: float = 30.0) -> None:
    import asyncpg

    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            conn = await asyncpg.connect(dsn, timeout=3)
            await conn.close()
            return
        except Exception as e:  # noqa: BLE001 -- retried until the deadline
            last_error = e
            await asyncio.sleep(0.5)
    raise pytest.UsageError(
        f"Test database not reachable at {dsn.split('@')[-1]}: {last_error}\n"
        "Start it with:  docker compose up -d postgres-test"
    )


async def _reset_schema(dsn: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    finally:
        await conn.close()


def _migrate() -> None:
    # Run Alembic exactly as the deploy does, from backend/ so alembic.ini
    # and env.py resolve the same way; the inherited environment carries the
    # test DATABASE_URL set above.
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise pytest.UsageError(
            "alembic upgrade head failed against the test database:\n"
            f"{result.stdout}\n{result.stderr}"
        )


@pytest.fixture(scope="session", autouse=True)
def _fresh_test_database(request):
    if not getattr(request.session, "needs_test_db", False):
        yield
        return
    dsn = _asyncpg_dsn(TEST_DATABASE_URL)
    _run(_wait_for_db(dsn))
    _run(_reset_schema(dsn))
    _migrate()
    print(f"\n[conftest] test database migrated to head: {dsn.split('@')[-1]}")
    yield
