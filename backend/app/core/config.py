from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import json

class Settings(BaseSettings):
    ENVIRONMENT: str = "local"
    
    SUPABASE_URL: str
    SUPABASE_PUBLISHABLE_KEY: str
    SUPABASE_SECRET_KEY: str
    SUPABASE_JWKS_URL: str
    
    DATABASE_URL: str
    
    LIVEKIT_URL: str = ""
    LIVEKIT_API_KEY: str = ""
    LIVEKIT_API_SECRET: str = ""
    
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = ""
    
    STT_PROVIDER: str = "livekit"
    LLM_PROVIDER: str = "openai"
    TTS_PROVIDER: str = "livekit"
    
    BACKEND_CORS_ORIGINS: str = '["http://localhost:5173"]'

    @property
    def cors_origins(self) -> List[str]:
        return json.loads(self.BACKEND_CORS_ORIGINS)

    model_config = SettingsConfigDict(
        env_file=["../.env", ".env"], 
        env_file_encoding="utf-8", 
        extra="ignore"
    )

settings = Settings()
