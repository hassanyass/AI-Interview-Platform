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
    expiration = datetime.now(timezone.utc) + timedelta(hours=24)
    payload = {
        "sub": profile_id,
        "email": email,
        "type": "guest",
        "exp": expiration,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
