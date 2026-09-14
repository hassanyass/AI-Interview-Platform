from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import httpx
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
        # 1. Try Supabase JWT first
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated"
        )
        return {"sub": payload.get("sub"), "email": payload.get("email"), "type": "supabase"}
    except Exception:
        # 2. Fallback to Guest JWT
        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=["HS256"]
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
