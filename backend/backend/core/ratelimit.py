"""In-process rate limiting (H5-B).

A token bucket per (scope, caller), held in this process's memory. No
Redis, per plan decision S9's reasoning: one backend replica, a load that
is measured in candidates per day, and a dependency that would have to be
operated for the rest of the system's life. When there are N replicas each
one enforces its own share of the limit; the swap is a DB- or Redis-backed
`_Store` behind the same `rate_limit()` dependency, and nothing at the call
sites changes.

**Who the caller is matters more than it looks.** Authenticated routes are
keyed by the token's subject, because everyone at an exhibition booth, in
an office or behind a corporate NAT shares one address -- an IP-keyed
limit would throttle a room full of legitimate candidates as though they
were one attacker. Only the two genuinely anonymous routes fall back to
the address, and their defaults are set generously for exactly that
reason: they are there to stop a script, not a queue of visitors.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Callable

from fastapi import Depends, Request

from backend.core.config import settings
from backend.core.errors import TooManyRequests
from backend.core.metrics import rate_limit_rejections_total
from backend.core.security import get_current_user_token_data

logger = logging.getLogger(__name__)

_WINDOWS = {"second": 1.0, "minute": 60.0, "hour": 3600.0, "day": 86400.0}
_RULE_RE = re.compile(r"^\s*(\d+)\s*/\s*(second|minute|hour|day)\s*$")

# A bucket that has been full for this long is indistinguishable from one
# that never existed, so it can be forgotten. Without this the dictionary
# would grow for every address ever seen -- which matters for a process
# expected to run for days.
_IDLE_EVICTION_SECONDS = 3600.0
_PRUNE_EVERY_SECONDS = 60.0


@dataclass(frozen=True)
class Rule:
    limit: int
    """Burst: how many requests can be made back to back."""
    per_seconds: float
    """The window those `limit` requests refill over."""

    @property
    def refill_per_second(self) -> float:
        return self.limit / self.per_seconds


def parse_rule(spec: str) -> Rule:
    """`"20/minute"` -> Rule(20, 60). Raises ValueError on anything else, so
    a typo in the environment stops the process at boot rather than
    silently disabling a limit."""
    match = _RULE_RE.match(spec)
    if not match:
        raise ValueError(f"Invalid rate-limit rule {spec!r}; expected '<count>/<second|minute|hour|day>'")
    count, window = int(match.group(1)), match.group(2)
    if count < 1:
        raise ValueError(f"Invalid rate-limit rule {spec!r}; the count must be at least 1")
    return Rule(limit=count, per_seconds=_WINDOWS[window])


@dataclass
class _Bucket:
    tokens: float
    updated: float
    per_seconds: float
    """The rule's window, kept so eviction can tell when this bucket would
    have refilled to full anyway."""


class RateLimiter:
    """Not thread-safe by design: one event loop, and every operation here
    is synchronous between awaits."""

    def __init__(self) -> None:
        self._buckets: dict[tuple[str, str], _Bucket] = {}
        self._last_prune = 0.0

    def check(self, scope: str, key: str, rule: Rule, *, now: float | None = None) -> float | None:
        """Consume one token. Returns None when allowed, or the number of
        seconds until the next token is available when refused."""
        now = time.monotonic() if now is None else now
        self._maybe_prune(now, rule)

        bucket = self._buckets.get((scope, key))
        if bucket is None:
            bucket = _Bucket(tokens=float(rule.limit), updated=now, per_seconds=rule.per_seconds)
            self._buckets[(scope, key)] = bucket
        else:
            elapsed = max(now - bucket.updated, 0.0)
            bucket.tokens = min(float(rule.limit), bucket.tokens + elapsed * rule.refill_per_second)
            bucket.updated = now
            bucket.per_seconds = rule.per_seconds

        if bucket.tokens >= 1.0:
            bucket.tokens -= 1.0
            return None
        return (1.0 - bucket.tokens) / rule.refill_per_second

    def reset(self) -> None:
        self._buckets.clear()
        self._last_prune = 0.0

    def _maybe_prune(self, now: float, rule: Rule) -> None:
        if now - self._last_prune < _PRUNE_EVERY_SECONDS:
            return
        self._last_prune = now
        # A bucket idle for longer than its own window has refilled to full,
        # so forgetting it is indistinguishable from keeping it -- the next
        # request would rebuild it full either way. Checking the stored
        # token count instead would keep every bucket forever, because a
        # bucket only refills when it is next used.
        stale = [
            key for key, bucket in self._buckets.items()
            if now - bucket.updated > max(_IDLE_EVICTION_SECONDS, bucket.per_seconds)
        ]
        for key in stale:
            del self._buckets[key]
        if stale:
            logger.debug("Rate limiter forgot %d idle bucket(s)", len(stale))


_limiter = RateLimiter()


def get_limiter() -> RateLimiter:
    return _limiter


def client_key(request: Request) -> str:
    """The caller's address. A proxy in front of this app must be trusted
    and configured (uvicorn `--proxy-headers`) for `request.client` to be
    the real client rather than the proxy; otherwise every request shares
    one bucket, which fails closed-ish (one shared limit) rather than open.
    """
    client = request.client
    return client.host if client else "unknown"


def rate_limit(scope: str, rule_getter: Callable[[], str], *, by_subject: bool = False):
    """FastAPI dependency factory.

    `rule_getter` is read per request, not at import time, so a test (or a
    settings reload) can change a limit without rebuilding the routes.
    `by_subject=True` keys the bucket by the authenticated token's subject
    -- see this module's docstring on why that is not a detail.
    """

    def _enforce(scope_key: str, request: Request) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return
        rule = parse_rule(rule_getter())
        retry_after = _limiter.check(scope, scope_key, rule)
        if retry_after is None:
            return
        rate_limit_rejections_total.labels(scope).inc()
        logger.warning(
            "Rate limit hit on %s by %s (%s)", scope, scope_key, rule_getter(),
            extra={"event": "rate_limited", "scope": scope},
        )
        raise TooManyRequests(
            "Too many requests. Please wait a moment and try again.",
            code="rate_limited",
            headers={"Retry-After": str(max(1, int(retry_after + 0.999)))},
        )

    # Two separate signatures on purpose. A parameter that is not a
    # Depends() is a *body field* to FastAPI -- declaring `token_data: dict
    # | None = None` on the anonymous variant silently added one to every
    # route it guarded, which turned each endpoint's own body into an
    # embedded field and made valid requests 422. (Caught by the suite the
    # first time this shipped.)
    if by_subject:
        async def _by_subject(
            request: Request,
            token_data: dict = Depends(get_current_user_token_data),
        ) -> None:
            _enforce(str(token_data.get("sub") or client_key(request)), request)

        return _by_subject

    async def _by_address(request: Request) -> None:
        _enforce(client_key(request), request)

    return _by_address
