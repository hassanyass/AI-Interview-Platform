"""
Shared guest-JWT minting — extracted from Phase 3's
POST /api/v1/interviews/public/register (backend/backend/api/endpoints/
interviews.py) during Sub-phase 6C, so Flow B's new
POST /apply/{token}/register (public_apply.py) doesn't duplicate this
logic. Behavior-preserving extraction: identical payload shape, same
signing key/algorithm, same 24h expiry — verified by rerunning Phase 3's
existing public_register tests unchanged after this extraction.
"""
from datetime import datetime, timezone, timedelta

import jwt

from backend.core.config import settings


def mint_guest_jwt(profile_id: str, email: str) -> str:
    expiration = datetime.now(timezone.utc) + timedelta(hours=settings.GUEST_JWT_TTL_HOURS)
    payload = {
        "sub": profile_id,
        "email": email,
        "type": "guest",
        "exp": expiration,
        # H5-A: stamped so the token says who minted it. core/security.py
        # selects the verification path by the absence of a `kid` header
        # and checks this when present; tokens minted before H5-A have no
        # `iss` and stay valid until they expire.
        "iss": settings.GUEST_JWT_ISSUER,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.GUEST_JWT_ALGORITHM)
