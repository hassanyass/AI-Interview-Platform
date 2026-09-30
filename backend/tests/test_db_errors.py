"""Connection exhaustion answers 503, not 500.

H5-B measured the defect and left it open: 40 concurrent requests made
Supabase's pooler refuse at its 15-client session-mode ceiling, and that
reached the caller as an unhandled 500. Neither a real pooler outage nor a
saturated pool is reproducible in CI, so the predicate is pure and tested
directly, and the handler is tested through the app with a route that
raises what the driver would raise.
"""

import pytest
import sqlalchemy.exc
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.core.db_errors import (
    TOO_MANY_CONNECTIONS_SQLSTATE,
    exhaustion_source,
    is_connection_exhaustion,
)
from backend.core.errors import install_exception_handlers


class _Orig(Exception):
    """Stands in for the DBAPI error asyncpg raises, which carries sqlstate."""

    def __init__(self, message: str, sqlstate: str | None = None):
        super().__init__(message)
        self.sqlstate = sqlstate


def _operational(message: str, sqlstate: str | None = None) -> sqlalchemy.exc.OperationalError:
    return sqlalchemy.exc.OperationalError("SELECT 1", {}, _Orig(message, sqlstate))


# ── the predicate ───────────────────────────────────────────────────────
def test_our_own_pool_timing_out_counts():
    assert is_connection_exhaustion(sqlalchemy.exc.TimeoutError("QueuePool limit of size 5 overflow 10 reached"))


def test_postgres_too_many_connections_sqlstate_counts():
    assert is_connection_exhaustion(_operational("sorry, too many clients already", TOO_MANY_CONNECTIONS_SQLSTATE))


def test_supabase_pooler_marker_counts_even_without_a_sqlstate():
    # The pooler reports session-mode exhaustion by name, not by SQLSTATE --
    # which is why a SQLSTATE-only check would have missed the real outage.
    assert is_connection_exhaustion(_operational("MaxClientsInSessionMode: EMAXCONNSESSION"))


@pytest.mark.parametrize(
    "message",
    [
        'relation "jobs" does not exist',
        "duplicate key value violates unique constraint",
        "deadlock detected",
    ],
)
def test_real_faults_are_left_alone(message):
    # The important half: a genuine failure must keep surfacing as a 500.
    # Softening it to 503 would invite a retry loop against a broken database.
    assert not is_connection_exhaustion(_operational(message, "42P01"))


def test_the_two_exhaustion_sources_are_distinguished():
    # Worth separating in the log: raising DB_POOL_SIZE fixes the first and
    # makes the second worse.
    assert exhaustion_source(sqlalchemy.exc.TimeoutError("x")) == "local_pool"
    assert exhaustion_source(_operational("EMAXCONNSESSION")) == "server_or_pooler"


# ── the handler, through a real app ─────────────────────────────────────
def _app_raising(exc: Exception) -> FastAPI:
    app = FastAPI()

    @app.get("/boom")
    async def boom():
        raise exc

    install_exception_handlers(app)
    return app


async def _get(app: FastAPI):
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/boom")


@pytest.mark.asyncio
async def test_exhaustion_answers_503_with_retry_after():
    response = await _get(_app_raising(_operational("EMAXCONNSESSION")))
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "db_unavailable"
    assert body["status"] == 503
    # A caller that cannot retry intelligently is why this mattered.
    assert response.headers["Retry-After"] == "5"


@pytest.mark.asyncio
async def test_a_genuine_database_fault_still_answers_500():
    response = await _get(_app_raising(_operational('relation "jobs" does not exist', "42P01")))
    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"


@pytest.mark.asyncio
async def test_the_503_body_does_not_leak_the_driver_message():
    # "EMAXCONNSESSION" and the SQL text are for the log, not the candidate.
    response = await _get(_app_raising(_operational("EMAXCONNSESSION on SELECT secret_column")))
    assert "EMAXCONNSESSION" not in response.text
    assert "secret_column" not in response.text
