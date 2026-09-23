"""Token verification (H5-A).

Two kinds of bearer token reach this backend and they are told apart
**before** either is verified, by the one thing that is structural rather
than a guess: a Supabase token is asymmetric and always carries a `kid` in
its JOSE header, naming the key in the project's JWKS. A guest token is
minted here, signed HS256 with `SECRET_KEY`, and has no `kid`.

Before this, the code tried Supabase, caught *everything*, and retried the
same string as a guest token. Two things were wrong with that. A token was
accepted by whichever path happened to succeed rather than by who issued
it; and a JWKS outage -- a fault on our side -- was reported to every
candidate and admin as "invalid authentication credentials", because the
network error and a forged token took the same branch. Now each token has
exactly one path, and an unreachable JWKS is a 503.

Both paths pin their algorithms, and both check `iss` and (Supabase) `aud`.
Guest tokens minted before this change carry no `iss`, so it is verified
only when present -- they stay valid until they expire (24h).
"""
from __future__ import annotations

import asyncio
import logging

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.core.config import settings
from backend.core.errors import ServiceUnavailable, Unauthorized

logger = logging.getLogger(__name__)

security = HTTPBearer()

# Cache the JWKS so we don't fetch it on every request
_jwks_client = None


def get_jwks_client():
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(settings.SUPABASE_JWKS_URL)
    return _jwks_client


def reset_jwks_client() -> None:
    """Drop the cached client so the next call rebuilds it from the current
    settings. For tests."""
    global _jwks_client
    _jwks_client = None


def _unverified_header(token: str) -> dict:
    try:
        return jwt.get_unverified_header(token)
    except jwt.PyJWTError as e:
        logger.info("Rejected a token with an unreadable header: %s", e)
        raise Unauthorized("Invalid authentication credentials") from e


def _email_verified(payload: dict) -> bool | None:
    """True / False when the token says so, None when it does not say.

    Supabase has moved the claim around between versions (top level today,
    inside `user_metadata` for older projects), so all the places it can
    live are checked before concluding the token is silent on the subject.
    `None` is not `False`: the caller decides what an unprovable address
    means (see IDENTITY_AUTOLINK), and that is a policy question, not one
    this function should answer by guessing.
    """
    for container in (payload, payload.get("user_metadata") or {}, payload.get("app_metadata") or {}):
        if isinstance(container, dict) and "email_verified" in container:
            return bool(container["email_verified"])
    return None


async def _verify_supabase(token: str) -> dict:
    jwks_client = get_jwks_client()
    try:
        # PyJWKClient fetches/refreshes the JWKS over HTTP synchronously
        # (cached in between) -- off the event loop (H2-B) so a slow key
        # refresh cannot stall every other request.
        signing_key = await asyncio.to_thread(jwks_client.get_signing_key_from_jwt, token)
    except jwt.exceptions.PyJWKClientConnectionError as e:
        # Our dependency is unreachable. Reporting this as 401 would tell a
        # valid user their credentials are bad and hide the outage from
        # every dashboard -- which is what the old fallback did.
        logger.error("Cannot verify Supabase tokens: JWKS unreachable: %s", e)
        raise ServiceUnavailable(
            "Sign-in verification is temporarily unavailable. Please try again.",
            code="jwks_unavailable",
        ) from e
    except jwt.exceptions.PyJWKClientError as e:
        # Reachable, but no key matches this token's `kid`: a forged or
        # stale token, not an outage. (The distinction matters: the two
        # were one branch until a test asked what an unknown key should
        # answer.)
        logger.info("Rejected a Supabase token with an unknown signing key: %s", e)
        raise Unauthorized("Invalid authentication credentials") from e

    issuer = settings.supabase_jwt_issuer
    try:
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=settings.SUPABASE_JWT_ALGORITHMS,
            audience=settings.SUPABASE_JWT_AUDIENCE,
            issuer=issuer or None,
            options={"require": ["exp", "sub"], "verify_iss": bool(issuer)},
        )
    except jwt.PyJWTError as e:
        logger.info("Rejected a Supabase token: %s", e)
        raise Unauthorized("Invalid authentication credentials") from e

    return {
        "sub": payload.get("sub"),
        "email": payload.get("email"),
        "email_verified": _email_verified(payload),
        "type": "supabase",
    }


def _verify_guest(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.GUEST_JWT_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as e:
        logger.info("Rejected a guest token: %s", e)
        raise Unauthorized("Invalid authentication credentials") from e

    if payload.get("type") != "guest":
        # An HS256 token signed with our key but not minted as a guest
        # credential has no business here.
        logger.warning("Rejected an HS256 token whose type is %r", payload.get("type"))
        raise Unauthorized("Invalid authentication credentials")

    # Verified only when present: tokens minted before H5-A carry no `iss`
    # and must keep working until they expire.
    issuer = payload.get("iss")
    if issuer is not None and issuer != settings.GUEST_JWT_ISSUER:
        logger.warning("Rejected a guest token with issuer %r", issuer)
        raise Unauthorized("Invalid authentication credentials")

    return {
        "sub": payload.get("sub"),
        "email": payload.get("email"),
        # A guest credential is proof of nothing about the address: it is
        # minted from whatever the applicant typed into the form.
        "email_verified": False,
        "type": "guest",
    }


async def get_current_user_token_data(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    token = credentials.credentials
    header = _unverified_header(token)
    # The selector. `kid` names a key in someone else's JWKS, so it can
    # only be an asymmetric token from the identity provider; our own guest
    # tokens never carry one. Nothing falls through from one path to the
    # other.
    if header.get("kid"):
        return await _verify_supabase(token)
    return _verify_guest(token)
