"""H5-B: the unauthenticated and expensive routes are bounded.

The bucket itself is tested directly (refill is arithmetic, and arithmetic
deserves exact assertions rather than sleeps), then through the real app on
the route that matters most: `POST /apply/{token}/register` is anonymous
and each call creates a profile, an application, an interview session and a
guest token.
"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.core.config import settings
from backend.core.ratelimit import Rule, get_limiter, parse_rule
from backend.main import app


@pytest.fixture(autouse=True)
def empty_buckets():
    get_limiter().reset()
    yield
    get_limiter().reset()


# ── the bucket ────────────────────────────────────────────────────────────

def test_a_rule_is_read_from_its_written_form():
    assert parse_rule("20/minute") == Rule(limit=20, per_seconds=60.0)
    assert parse_rule(" 5 / second ") == Rule(limit=5, per_seconds=1.0)
    assert parse_rule("100/hour").refill_per_second == pytest.approx(100 / 3600)


@pytest.mark.parametrize("bad", ["", "20", "20/fortnight", "0/minute", "-1/minute", "20 minute", "many/minute"])
def test_an_unreadable_rule_is_refused_rather_than_ignored(bad):
    """A typo in the environment must stop the route loudly. Silently
    treating it as "no limit" is the failure mode worth preventing."""
    with pytest.raises(ValueError):
        parse_rule(bad)


def test_the_burst_is_the_limit_and_then_it_refuses():
    limiter = get_limiter()
    rule = parse_rule("3/minute")
    assert [limiter.check("s", "k", rule, now=100.0) for _ in range(3)] == [None, None, None]

    retry_after = limiter.check("s", "k", rule, now=100.0)
    assert retry_after is not None
    assert retry_after == pytest.approx(20.0)      # 3 per 60s -> one token every 20s


def test_tokens_come_back_over_time():
    limiter = get_limiter()
    rule = parse_rule("3/minute")
    for _ in range(3):
        limiter.check("s", "k", rule, now=0.0)
    assert limiter.check("s", "k", rule, now=19.0) is not None
    assert limiter.check("s", "k", rule, now=20.0) is None      # exactly one token back
    assert limiter.check("s", "k", rule, now=20.0) is not None  # and only one


def test_the_bucket_never_fills_past_its_limit():
    limiter = get_limiter()
    rule = parse_rule("3/minute")
    limiter.check("s", "k", rule, now=0.0)
    # An hour later the bucket is full, not overflowing.
    assert [limiter.check("s", "k", rule, now=3600.0) for _ in range(3)] == [None, None, None]
    assert limiter.check("s", "k", rule, now=3600.0) is not None


def test_callers_and_scopes_do_not_share_a_bucket():
    limiter = get_limiter()
    rule = parse_rule("1/minute")
    assert limiter.check("scope-a", "caller-1", rule, now=0.0) is None
    assert limiter.check("scope-a", "caller-1", rule, now=0.0) is not None   # same caller, refused
    assert limiter.check("scope-a", "caller-2", rule, now=0.0) is None       # different caller
    assert limiter.check("scope-b", "caller-1", rule, now=0.0) is None       # different scope


def test_idle_buckets_are_forgotten_so_memory_does_not_grow_forever():
    """This process is expected to run for days; one bucket per address
    ever seen would be a slow leak."""
    limiter = get_limiter()
    rule = parse_rule("5/minute")
    for i in range(50):
        limiter.check("s", f"caller-{i}", rule, now=0.0)
    assert len(limiter._buckets) == 50

    # Long enough later that every bucket has refilled and gone idle.
    limiter.check("s", "someone-new", rule, now=100_000.0)
    assert len(limiter._buckets) == 1


# ── through the app ───────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_public_registration_is_bounded_and_says_when_to_come_back(client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_PUBLIC_REGISTER", "3/minute")
    url = f"/api/v1/apply/{uuid.uuid4().hex}/register"
    body = {"name": "Visitor", "email": "visitor@example.dev"}

    # The token is nonsense, so these are 403s -- but they are answered,
    # which is what consumes a token. Rate limiting runs before the work.
    for _ in range(3):
        assert (await client.post(url, json=body)).status_code != 429

    limited = await client.post(url, json=body)
    assert limited.status_code == 429
    assert limited.json()["code"] == "rate_limited"
    assert int(limited.headers["Retry-After"]) >= 1
    assert limited.headers.get("X-Request-ID")      # still a traceable failure


@pytest.mark.asyncio
async def test_the_limit_can_be_turned_off(client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_PUBLIC_REGISTER", "1/minute")
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    url = f"/api/v1/apply/{uuid.uuid4().hex}/register"
    body = {"name": "Visitor", "email": "visitor@example.dev"}
    for _ in range(5):
        assert (await client.post(url, json=body)).status_code != 429


@pytest.mark.asyncio
async def test_a_limited_route_still_accepts_its_own_body(client):
    """Regression: the first version of the dependency declared a
    `dict | None` parameter, which FastAPI read as a *body field* -- so
    every guarded route's own body became embedded and valid requests
    turned into 422s."""
    response = await client.post(
        f"/api/v1/apply/{uuid.uuid4().hex}/register",
        json={"name": "Visitor", "email": "visitor@example.dev"},
    )
    assert response.status_code != 422, response.text


@pytest.mark.asyncio
async def test_the_preview_route_is_limited_separately_from_registration(client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_APPLY_PREVIEW", "2/minute")
    monkeypatch.setattr(settings, "RATE_LIMIT_PUBLIC_REGISTER", "5/minute")
    token = uuid.uuid4().hex
    for _ in range(2):
        assert (await client.get(f"/api/v1/apply/{token}")).status_code != 429
    assert (await client.get(f"/api/v1/apply/{token}")).status_code == 429
    # Registration has its own bucket and is unaffected.
    assert (await client.post(f"/api/v1/apply/{token}/register",
                              json={"name": "V", "email": "v@example.dev"})).status_code != 429
