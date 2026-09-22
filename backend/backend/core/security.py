from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import asyncio
import jwt
from backend.core.config import settings
import logging

logger = logging.getLogger(__name__)

security = HTTPBearer()

# Cache the JWKS so we don't fetch it on every request
_jwks_client = None

def get_jwks_client():
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(settings.SUPABASE_JWKS_URL)
    return _jwks_client

async def get_current_user_token_data(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    token = credentials.credentials
    jwks_client = get_jwks_client()
    try:
        # 1. Try Supabase JWT first. PyJWKClient fetches/refreshes the JWKS
        # over HTTP synchronously (cached in between) -- off the event loop
        # (H2-B) so a slow key refresh cannot stall every other request.
        signing_key = await asyncio.to_thread(jwks_client.get_signing_key_from_jwt, token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=settings.SUPABASE_JWT_ALGORITHMS,
            audience=settings.SUPABASE_JWT_AUDIENCE,
        )
        return {"sub": payload.get("sub"), "email": payload.get("email"), "type": "supabase"}
    except Exception:  # noqa: BLE001 -- H5 replaces this fallback with issuer/kid selection; left as-is until then
        # 2. Fallback to Guest JWT
        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[settings.GUEST_JWT_ALGORITHM]
            )
            if payload.get("type") != "guest":
                raise HTTPException(status_code=401, detail="Invalid token type")
            return {"sub": payload.get("sub"), "email": payload.get("email"), "type": "guest"}
        except jwt.PyJWTError as e:
            logger.error(f"Invalid guest token: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials"
            )
