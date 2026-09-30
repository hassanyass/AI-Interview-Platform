"""Recognising "the database has no connection for you right now".

H5-B measured this and left it open: driving 40 concurrent requests made
Supabase's connection pooler reject at its own 15-client session-mode
ceiling (`EMAXCONNSESSION`), and the result reached the candidate as an
unhandled **500**. A 500 says "this server is broken"; the truthful answer
is **503 — busy, try again**, which is also what a load balancer, a retry
policy and an on-call engineer each need it to say.

Two distinct exhaustion points, and both mean the same thing to a caller:

1. **Our own pool** is full and `pool_timeout` elapsed — SQLAlchemy raises
   `sqlalchemy.exc.TimeoutError`. Tunable with `DB_POOL_SIZE` /
   `DB_MAX_OVERFLOW`.
2. **The server or pooler in front of it** refuses another connection —
   Postgres SQLSTATE `53300` (`too_many_connections`), or Supabase's
   pooler, which reports `EMAXCONNSESSION` rather than a SQLSTATE. Raising
   our own pool size makes this one *worse*, which is exactly why the two
   are worth telling apart in the logs even though both answer 503.

The predicate is deliberately separate from the handler so it can be
tested without a database or a real outage -- neither of which is
reproducible in CI.
"""

from __future__ import annotations

import sqlalchemy.exc

#: Postgres SQLSTATE for `too_many_connections`.
TOO_MANY_CONNECTIONS_SQLSTATE = "53300"

#: Supabase's pooler reports session-mode exhaustion by name, not SQLSTATE.
_POOLER_MARKERS = ("emaxconnsession", "max clients reached", "too many clients")


def _sqlstate_of(exc: BaseException) -> str | None:
    """SQLSTATE from a DBAPI error, wrapped or not."""
    for candidate in (exc, getattr(exc, "orig", None)):
        if candidate is None:
            continue
        code = getattr(candidate, "sqlstate", None) or getattr(candidate, "pgcode", None)
        if code:
            return str(code)
    return None


def is_connection_exhaustion(exc: BaseException) -> bool:
    """True when the cause is 'no connection available', not a real fault.

    Matches our own pool timing out, SQLSTATE 53300 from the server, and
    the pooler's textual marker. Anything else is left alone: a genuine
    failure must keep surfacing as a 500 rather than being softened into a
    503 that invites a retry loop against a broken database.
    """
    if isinstance(exc, sqlalchemy.exc.TimeoutError):
        return True

    if _sqlstate_of(exc) == TOO_MANY_CONNECTIONS_SQLSTATE:
        return True

    # The pooler's message travels through asyncpg and SQLAlchemy as text.
    haystack = " ".join(
        str(part) for part in (exc, getattr(exc, "orig", None)) if part is not None
    ).lower()
    return any(marker in haystack for marker in _POOLER_MARKERS)


def exhaustion_source(exc: BaseException) -> str:
    """Which limit was hit -- for the log line, not the response body.

    Worth distinguishing: `local_pool` is fixed by raising DB_POOL_SIZE,
    while `server_or_pooler` is made *worse* by exactly that change.
    """
    if isinstance(exc, sqlalchemy.exc.TimeoutError):
        return "local_pool"
    return "server_or_pooler"
