"""H4-B: every route's authentication, checked against the route table
rather than a hand-written list.

The point is the gate, not the snapshot: a route added without an auth
dependency, or one whose dependency is dropped in a refactor, answers 200
where these expect 401 and fails here. The wrong-credential half (a
candidate on an admin route, candidate B on candidate A's session) is the
part with real teeth -- before this file the whole repository held about
ten 401/403 assertions.

Two real credentials are used, not mocks of the dependency under test:
the admin is a `users_roles` row with a Supabase-shaped token, and the
candidates are guest JWTs minted by the public-apply flow.
"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from backend.api.deps import get_current_user_token_data
from backend.db.session import AsyncSessionLocal
from backend.main import app
from backend.models.profile import CandidateProfile, UserRole

ADMIN_UUID = uuid.uuid4()
NON_ADMIN_UUID = uuid.uuid4()
_admin = lambda: {"sub": str(ADMIN_UUID), "email": "authmatrix@path2hire.test", "type": "supabase"}  # noqa: E731
_non_admin = lambda: {"sub": str(NON_ADMIN_UUID), "email": "notadmin@path2hire.test", "type": "supabase"}  # noqa: E731

PLACEHOLDERS = ("{session_id}", "{job_id}", "{question_id}", "{section_id}", "{definition_id}", "{task_id}")
SKIP_PREFIXES = ("/docs", "/redoc", "/openapi", "/health", "/ready", "/version", "/metrics", "/__")


# ── the route table ───────────────────────────────────────────────────────

def _routes():
    """(path, method, auth-class) for every API route, including those
    reached through include_router (FastAPI lists those as _IncludedRouter,
    the same shape core/metrics.py has to walk)."""
    found = []

    def walk(routes, prefix=""):
        for route in routes:
            inner = getattr(route, "original_router", None)
            if inner is not None:
                ctx = getattr(route, "include_context", None)
                walk(inner.routes, prefix + (getattr(ctx, "prefix", "") or ""))
                continue
            path = getattr(route, "path", None)
            if not path or path.startswith(SKIP_PREFIXES):
                continue
            dependant = getattr(route, "dependant", None)
            names = {getattr(d.call, "__name__", "") for d in (dependant.dependencies if dependant else [])}
            if "get_current_admin" in names:
                kind = "admin"
            elif "verify_agent_secret" in names:
                kind = "agent"
            elif "get_current_candidate_profile_id" in names:
                kind = "candidate"
            else:
                kind = "public"
            for method in sorted(getattr(route, "methods", []) or []):
                if method in ("HEAD", "OPTIONS"):
                    continue
                found.append((prefix + path, method, kind))

    walk(app.routes)
    return found


def _concrete(path: str) -> str:
    for token in PLACEHOLDERS:
        path = path.replace(token, str(uuid.uuid4()))
    return path.replace("{token}", "no-such-token")


ROUTES = _routes()
ADMIN_ROUTES = [(p, m) for p, m, k in ROUTES if k == "admin"]
CANDIDATE_ROUTES = [(p, m) for p, m, k in ROUTES if k == "candidate"]
AGENT_ROUTES = [(p, m) for p, m, k in ROUTES if k == "agent"]
PUBLIC_ROUTES = [(p, m) for p, m, k in ROUTES if k == "public"]


async def _call(client: AsyncClient, method: str, path: str, **kwargs):
    body = {} if method in ("POST", "PATCH", "PUT") else None
    return await client.request(method, _concrete(path), json=body, **kwargs)


@pytest_asyncio.fixture
async def anon():
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def as_non_admin():
    """A real Supabase-shaped identity with no users_roles row."""
    app.dependency_overrides[get_current_user_token_data] = _non_admin
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_current_user_token_data, None)
    async with AsyncSessionLocal() as db:
        await db.execute(delete(CandidateProfile).where(CandidateProfile.email == "notadmin@path2hire.test"))
        await db.commit()


# ── no credentials ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_route_table_still_has_the_shape_these_tests_assume():
    # If this fails, a whole class of route appeared or vanished -- look at
    # the new route before adjusting the number.
    assert len(ADMIN_ROUTES) >= 29, ADMIN_ROUTES
    assert len(CANDIDATE_ROUTES) >= 12, CANDIDATE_ROUTES
    assert len(AGENT_ROUTES) == 7, AGENT_ROUTES
    assert sorted(PUBLIC_ROUTES) == [
        ("/api/v1/apply/{token}", "GET"),
        ("/api/v1/apply/{token}/register", "POST"),
        ("/api/v1/invitations/{token}", "GET"),
    ], PUBLIC_ROUTES


@pytest.mark.asyncio
async def test_no_admin_route_answers_without_credentials(anon):
    bad = []
    for path, method in ADMIN_ROUTES:
        r = await _call(anon, method, path)
        if r.status_code != 401:
            bad.append((method, path, r.status_code))
    assert not bad, f"admin routes reachable without credentials: {bad}"


@pytest.mark.asyncio
async def test_no_candidate_route_answers_without_credentials(anon):
    bad = []
    for path, method in CANDIDATE_ROUTES:
        r = await _call(anon, method, path)
        if r.status_code != 401:
            bad.append((method, path, r.status_code))
    assert not bad, f"candidate routes reachable without credentials: {bad}"


# ── wrong credentials ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_signed_in_non_admin_is_refused_every_admin_route(as_non_admin):
    """403, not 401: the identity is valid, the role is not. RoleContext
    depends on exactly this distinction (H2-E) -- a 401 here would sign a
    real admin out on a blip."""
    bad = []
    for path, method in ADMIN_ROUTES:
        r = await _call(as_non_admin, method, path)
        if r.status_code != 403:
            bad.append((method, path, r.status_code))
    assert not bad, f"admin routes not returning 403 to a non-admin: {bad}"


@pytest.mark.asyncio
async def test_internal_routes_need_the_agent_secret(anon):
    from backend.core.config import settings

    missing, wrong, accepted = [], [], []
    for path, method in AGENT_ROUTES:
        r = await _call(anon, method, path)
        # The header is declared required, so its absence is a validation
        # error, not 401. Pinned as today's behaviour -- and pinned to be
        # about the header, not the body: changing it would touch
        # /internal/*, a frozen contract (AGENTS.md §2).
        blames_header = "agent-secret" in r.text.lower()
        if r.status_code != 422 or not blames_header:
            missing.append((method, path, r.status_code))

        r = await _call(anon, method, path, headers={"X-Agent-Secret": "not-the-secret"})
        if r.status_code != 403:
            wrong.append((method, path, r.status_code))

        # With the right secret the request gets past auth; what it does
        # next (404 for an unknown session, 422 for the empty body these
        # probes send) is the handler's business, not this test's. The one
        # thing that must not happen is another 403.
        r = await _call(anon, method, path, headers={"X-Agent-Secret": settings.AGENT_API_SECRET})
        if r.status_code == 403:
            accepted.append((method, path, r.status_code))
    assert not missing, f"internal routes without the header: {missing}"
    assert not wrong, f"internal routes accepting a wrong secret: {wrong}"
    assert not accepted, f"internal routes rejecting the right secret: {accepted}"


@pytest.mark.asyncio
async def test_public_routes_stay_reachable_without_credentials(anon):
    """The three deliberately public routes must not acquire auth by
    accident -- a candidate link that starts answering 401 is a silent
    outage. They answer 403/404/422 for unknown tokens, never 401."""
    for path, method in PUBLIC_ROUTES:
        r = await _call(anon, method, path)
        assert r.status_code != 401, f"{method} {path} now requires credentials"


# ── one candidate cannot reach another's session ──────────────────────────

@pytest_asyncio.fixture
async def two_candidates_on_one_job():
    """A published public job plus two registered candidates, each with a
    real guest JWT and their own session."""
    async with AsyncSessionLocal() as db:
        db.add(UserRole(user_id=ADMIN_UUID, role="admin"))
        await db.commit()
    app.dependency_overrides[get_current_user_token_data] = _admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        job = (await c.post("/api/v1/admin/jobs", json={"title": "Auth Matrix Test Job", "seniority": "mid"})).json()
        job_id, definition_id = job["id"], job["definition"]["id"]
        sec = (await c.post("/api/v1/admin/sections", json={
            "definition_id": definition_id, "section_type": "VERBAL", "order_index": 0})).json()
        await c.patch(f"/api/v1/admin/sections/{sec['id']}", json={"config": {**sec["config"], "time_budget_minutes": 10}})
        await c.post(f"/api/v1/admin/sections/{sec['id']}/questions", json={"title": "Q", "text": "Tell me."})
        token = (await c.patch(f"/api/v1/admin/definitions/{definition_id}",
                               json={"is_public": True})).json()["definition"]["public_access_token"]
        assert (await c.post(f"/api/v1/admin/jobs/{job_id}/publish")).status_code == 200
    app.dependency_overrides.pop(get_current_user_token_data, None)

    people, emails = [], []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        for who in ("a", "b"):
            email = f"authmatrix-{who}-{uuid.uuid4().hex[:8]}@example.dev"
            emails.append(email)
            reg = (await c.post(f"/api/v1/apply/{token}/register",
                                json={"name": f"Candidate {who.upper()}", "email": email})).json()
            people.append({"session_id": reg["session"]["id"],
                           "auth": {"Authorization": f"Bearer {reg['access_token']}"}})

    yield people

    app.dependency_overrides[get_current_user_token_data] = _admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        for person in people:
            await c.delete(f"/api/v1/admin/interviews/{person['session_id']}")
        await c.delete(f"/api/v1/admin/jobs/{job_id}")
    app.dependency_overrides.pop(get_current_user_token_data, None)
    async with AsyncSessionLocal() as db:
        for email in emails:
            await db.execute(delete(CandidateProfile).where(CandidateProfile.email == email))
        await db.execute(delete(UserRole).where(UserRole.user_id == ADMIN_UUID))
        await db.commit()


@pytest.mark.asyncio
async def test_a_candidate_cannot_touch_another_candidates_session(two_candidates_on_one_job):
    a, b = two_candidates_on_one_job
    sid = a["session_id"]

    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as c:
        # Every ownership check in interviews.py, plus the room token.
        # `terminate` scopes its SELECT by candidate_profile_id, so a
        # stranger gets 404 rather than 403 -- refusal either way, and it
        # does not confirm the session exists. Both are accepted here; a
        # 2xx from any of them is the failure.
        consent_body = {"disclosure_language": "en", "disclosure_text": "Recorded for review."}
        probes = [
            ("GET", f"/api/v1/interviews/{sid}", None),
            ("GET", f"/api/v1/interviews/{sid}/transcript", None),
            ("GET", f"/api/v1/interviews/{sid}/events", None),
            ("GET", f"/api/v1/interviews/{sid}/cv", None),
            ("POST", f"/api/v1/interviews/{sid}/terminate", {}),
            ("POST", f"/api/v1/interviews/{sid}/consent", consent_body),
        ]
        leaked = []
        for method, path, body in probes:
            r = await c.request(method, path, json=body, headers=b["auth"])
            if r.status_code not in (403, 404):
                leaked.append((method, path, r.status_code))
        assert not leaked, f"candidate B reached candidate A's session: {leaked}"

        # ...and the session really is still there for its owner, so the
        # 404 above is a refusal, not a missing row.
        assert (await c.get(f"/api/v1/interviews/{sid}", headers=a["auth"])).status_code == 200

        # Same defensive shape as terminate: the room-token route answers
        # "not found or you do not have access" rather than confirming the
        # session exists.
        token = await c.post("/api/v1/livekit/token", json={"session_id": sid}, headers=b["auth"])
        assert token.status_code in (403, 404), token.text

        # ...and the owner is still allowed in (the checks reject by owner,
        # not by rejecting everyone).
        own = await c.get(f"/api/v1/interviews/{sid}", headers=a["auth"])
        assert own.status_code == 200, own.text
