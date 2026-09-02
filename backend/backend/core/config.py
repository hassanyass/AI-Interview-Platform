from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import json

class Settings(BaseSettings):
    ENVIRONMENT: str = "local"
    SECRET_KEY: str = "local_guest_jwt_secret_key_change_me_in_prod"
    
    SUPABASE_URL: str
    SUPABASE_PUBLISHABLE_KEY: str
    SUPABASE_SECRET_KEY: str
    SUPABASE_JWKS_URL: str
    
    DATABASE_URL: str
    
    LIVEKIT_URL: str = ""
    LIVEKIT_API_KEY: str = ""
    LIVEKIT_API_SECRET: str = ""

    # PR-C (docs/proctoring-architecture.md): Cloudflare R2, S3-compatible,
    # destination for LiveKit Egress full audio+video recordings.
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = ""
    R2_ENDPOINT: str = ""

    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = ""
    
    STT_PROVIDER: str = "livekit"
    LLM_PROVIDER: str = "openai"
    TTS_PROVIDER: str = "livekit"
    
    # Internal agent-to-backend API authentication
    AGENT_API_SECRET: str = ""

    # Phase 8D: HR dashboard "suggested candidates" threshold — reasonable
    # default, needs real-world tuning once real evaluated sessions exist
    # to calibrate against (see docs/CURRENT_DECISIONS.md).
    SUGGESTED_EVIDENCE_SUFFICIENCY_FLOOR: float = 0.5

    # Session-finalization-contract fix (2026-09-01, see
    # docs/CURRENT_DECISIONS.md): a candidate who disconnects and never
    # resumes gets auto-finalized (recording stopped, status -> TERMINATED,
    # a guaranteed Evaluation row) after this many minutes idle in
    # DISCONNECTED. Same env-configurable-constant pattern as the agent's
    # own WAITING_ROOM_TIMEOUT_SECONDS. Confirmed default with the user.
    DISCONNECT_AUTO_FINALIZE_MINUTES: int = 10
    
    BACKEND_CORS_ORIGINS: str = '["http://localhost:5173", "http://127.0.0.1:5173"]'

    @property
    def cors_origins(self) -> List[str]:
        return json.loads(self.BACKEND_CORS_ORIGINS)

    model_config = SettingsConfigDict(
        env_file=["../.env", ".env"], 
        env_file_encoding="utf-8", 
        extra="ignore"
    )

settings = Settings()
