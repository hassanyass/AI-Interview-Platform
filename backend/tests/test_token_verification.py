"""H5-A: one token, one verification path, and every rejection is its own.

Real tokens throughout -- an EC key pair stands in for the Supabase
project's JWKS and guest tokens are minted by the real service -- because
the thing under test is exactly what the library does with a signature,
an `aud`, an `iss` and an `exp`.

What this pins down, beyond "a bad token is rejected":
- a token is verified by the path its issuer implies (`kid` present or
  not), never by trying both;
- a JWKS outage answers 503, not 401, so an outage on our side is not
  reported to users as their credentials being wrong;
- an HS256 token is never accepted on the Supabase path, and vice versa.
"""
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric import ec
from httpx import ASGITransport, AsyncClient

from backend.core import security
from backend.core.config import settings
from backend.main import app
from backend.services.guest_jwt_service import mint_guest_jwt

KID = "test-signing-key"
PROBE = "/api/v1/profiles/me"          # any candidate-authenticated route


@pytest.fixture(scope="module")
def keypair():
    private = ec.generate_private_key(ec.SECP256R1())
    return private, private.public_key()


@pytest.fixture(autouse=True)
def jwks(monkeypatch, keypair):
    """Stand in for the project's JWKS: hands back the public key for any
    token that carries our `kid`, and raises like PyJWKClient does for
    anything else."""
    _, public = keypair

    class FakeJWKSClient:
        def get_signing_key_from_jwt(self, token):
            header = jwt.get_unverified_header(token)
            if header.get("kid") != KID:
                raise jwt.exceptions.PyJWKClientError(f"Unable to find a signing key that matches: {header.get('kid')}")
            return type("Key", (), {"key": public})()

    monkeypatch.setattr(security, "_jwks_client", FakeJWKSClient())
    yield
    security.reset_jwks_client()


def supabase_token(keypair, *, sub=None, email="candidate@example.dev", aud=None, iss=None,
                   exp_delta=timedelta(hours=1), kid=KID, extra=None):
    private, _ = keypair
    payload = {
        "sub": sub or str(uuid.uuid4()),
        "email": email,
        "aud": settings.SUPABASE_JWT_AUDIENCE if aud is None else aud,
        "iss": settings.supabase_jwt_issuer if iss is None else iss,
        "exp": datetime.now(timezone.utc) + exp_delta,
        "iat": datetime.now(timezone.utc),
    }
    payload.update(extra or {})
    headers = {"kid": kid} if kid else None
    return jwt.encode(payload, private, algorithm="ES256", headers=headers)


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as c:
        yield c


async def auth_status(client, token) -> int:
    return (await client.get(PROBE, headers={"Authorization": f"Bearer {token}"})).status_code


async def authenticated(client, token) -> bool:
    """Whether the token got past verification. The probe route's own
    answer (200 for a resolvable profile, 404 for a guest whose profile
    this test never created) is not what is under test here."""
    return await auth_status(client, token) not in (401, 403, 503)


# ── the selector ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_valid_supabase_token_is_accepted(client, keypair):
    assert await auth_status(client, supabase_token(keypair)) == 200


@pytest.mark.asyncio
async def test_a_valid_guest_token_is_accepted(client):
    token = mint_guest_jwt(str(uuid.uuid4()), "guest@example.dev")
    assert await authenticated(client, token)


@pytest.mark.asyncio
async def test_an_hs256_token_is_never_tried_against_the_supabase_path(client):
    """Signed with our guest key but wearing a `kid`, so it is routed to
    the asymmetric path -- where it must fail rather than fall back."""
    forged = jwt.encode(
        {"sub": str(uuid.uuid4()), "email": "x@example.dev", "type": "guest",
         "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        settings.SECRET_KEY, algorithm="HS256", headers={"kid": KID},
    )
    assert await auth_status(client, forged) == 401


@pytest.mark.asyncio
async def test_a_supabase_token_is_not_retried_as_a_guest_token(client, keypair):
    """The old code caught every Supabase failure and re-decoded the same
    string with the guest key. An expired Supabase token must be rejected
    on its own path, once."""
    expired = supabase_token(keypair, exp_delta=timedelta(hours=-1))
    assert await auth_status(client, expired) == 401


# ── Supabase rejections ───────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("bad, why", [
    ({"exp_delta": timedelta(seconds=-5)}, "expired"),
    ({"aud": "some-other-audience"}, "wrong audience"),
    ({"iss": "https://evil.example.com/auth/v1"}, "wrong issuer"),
    ({"kid": "unknown-key"}, "unknown signing key"),
])
async def test_supabase_tokens_are_rejected_one_reason_at_a_time(client, keypair, bad, why):
    assert await auth_status(client, supabase_token(keypair, **bad)) == 401, why


@pytest.mark.asyncio
async def test_a_token_signed_by_a_different_key_is_rejected(client, keypair):
    attacker = ec.generate_private_key(ec.SECP256R1())
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "email": "x@example.dev", "aud": settings.SUPABASE_JWT_AUDIENCE,
         "iss": settings.supabase_jwt_issuer, "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        attacker, algorithm="ES256", headers={"kid": KID},
    )
    assert await auth_status(client, token) == 401


@pytest.mark.asyncio
async def test_a_token_with_no_expiry_is_rejected(client, keypair):
    private, _ = keypair
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "email": "x@example.dev", "aud": settings.SUPABASE_JWT_AUDIENCE,
         "iss": settings.supabase_jwt_issuer},
        private, algorithm="ES256", headers={"kid": KID},
    )
    assert await auth_status(client, token) == 401


# ── guest rejections ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_guest_token_signed_with_the_wrong_key_is_rejected(client):
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "email": "x@example.dev", "type": "guest",
         "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "not-the-backend-secret-key-at-all", algorithm="HS256",
    )
    assert await auth_status(client, token) == 401


@pytest.mark.asyncio
async def test_an_hs256_token_that_is_not_a_guest_credential_is_rejected(client):
    """Signed with the real key but minted for something else -- it must
    not become a candidate session."""
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "email": "x@example.dev", "type": "password-reset",
         "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        settings.SECRET_KEY, algorithm="HS256",
    )
    assert await auth_status(client, token) == 401


@pytest.mark.asyncio
async def test_a_guest_token_from_another_issuer_is_rejected(client):
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "email": "x@example.dev", "type": "guest", "iss": "somewhere-else",
         "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        settings.SECRET_KEY, algorithm="HS256",
    )
    assert await auth_status(client, token) == 401


@pytest.mark.asyncio
async def test_a_guest_token_minted_before_h5a_still_works(client):
    """Backward compatibility: `iss` is verified when present, and tokens
    already in candidates' hands carry none."""
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "email": "x@example.dev", "type": "guest",
         "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        settings.SECRET_KEY, algorithm="HS256",
    )
    assert await authenticated(client, token)


@pytest.mark.asyncio
async def test_the_none_algorithm_is_rejected(client):
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "email": "x@example.dev", "type": "guest",
         "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        key="", algorithm=None,
    )
    assert await auth_status(client, token) == 401


@pytest.mark.asyncio
async def test_garbage_is_rejected_without_a_traceback(client):
    for token in ("not.a.token", "", "Bearer", "a" * 500):
        assert await auth_status(client, token) in (401, 403)


# ── our outage is not the user's problem ──────────────────────────────────

@pytest.mark.asyncio
async def test_an_unreachable_jwks_is_503_not_401(client, keypair, monkeypatch):
    """The old fallback reported a key-server outage as invalid
    credentials, which sends every admin to the login screen and hides the
    incident."""
    class DeadJWKSClient:
        def get_signing_key_from_jwt(self, token):
            raise jwt.exceptions.PyJWKClientConnectionError("connection refused")

    monkeypatch.setattr(security, "_jwks_client", DeadJWKSClient())
    response = await client.get(PROBE, headers={"Authorization": f"Bearer {supabase_token(keypair)}"})
    assert response.status_code == 503
    assert response.json()["code"] == "jwks_unavailable"


@pytest.mark.asyncio
async def test_a_jwks_outage_does_not_affect_guest_tokens(client, monkeypatch):
    """Guest tokens are verified with a local secret; a key-server outage
    must not end a candidate's interview."""
    class DeadJWKSClient:
        def get_signing_key_from_jwt(self, token):
            raise jwt.exceptions.PyJWKClientConnectionError("connection refused")

    monkeypatch.setattr(security, "_jwks_client", DeadJWKSClient())
    token = mint_guest_jwt(str(uuid.uuid4()), "guest@example.dev")
    assert await authenticated(client, token)
