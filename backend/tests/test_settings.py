"""H1-A: the typed Settings object — defaults equal the literals the code
used before they were lifted, and the boot-time refusal outside local/test
actually refuses.

Constructs Settings directly with ``_env_file=None`` so neither the repo
.env nor the process environment leaks into what is being asserted; the
required fields are supplied as dummies.
"""
import pytest
from pydantic import ValidationError

from backend.core.config import Settings, _DEFAULT_SECRET_KEY

REQUIRED = {
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SECRET_KEY": "service-role",
    "SUPABASE_JWKS_URL": "https://example.supabase.co/auth/v1/.well-known/jwks.json",
    "DATABASE_URL": "postgresql+asyncpg://u:p@localhost:5433/x",
}

PRODUCTION_OK = {
    **REQUIRED,
    "ENVIRONMENT": "production",
    "SECRET_KEY": "x" * 48,
    "AGENT_API_SECRET": "agent-secret",
    "LIVEKIT_URL": "wss://lk.example",
    "LIVEKIT_API_KEY": "key",
    "LIVEKIT_API_SECRET": "secret",
    # H5-C: CORS is part of "complete" now -- outside local/test the shipped
    # localhost default is refused, so a production config must say which
    # origins the browser app is actually served from.
    "BACKEND_CORS_ORIGINS": '["https://hire.example.com"]',
}


def make(**overrides) -> Settings:
    return Settings(_env_file=None, **{**REQUIRED, **overrides})


def test_defaults_match_the_lifted_literals():
    s = make()
    assert s.ENVIRONMENT == "local"
    assert s.APP_VERSION == "0.1.0"
    assert s.SECRET_KEY == _DEFAULT_SECRET_KEY
    assert s.SUPABASE_JWT_ALGORITHMS == ["ES256", "RS256"]
    assert s.SUPABASE_JWT_AUDIENCE == "authenticated"
    assert s.GUEST_JWT_ALGORITHM == "HS256"
    assert s.GUEST_JWT_TTL_HOURS == 24
    assert s.LIVEKIT_TOKEN_TTL_MINUTES == 360
    assert s.EGRESS_LAYOUT == "speaker"
    assert s.EGRESS_START_RETRY_ATTEMPTS == 10
    assert s.EGRESS_START_RETRY_DELAY_SECONDS == 1.0
    assert s.RECORDING_PATH_TEMPLATE.format(session_id="S", timestamp=1) == "interviews/S/1.mp4"
    assert s.RECORDING_URL_TTL_SECONDS == 3600
    assert s.RESUMES_BUCKET == "resumes"
    assert s.MAX_RESUME_BYTES == 5 * 1024 * 1024
    assert s.GROQ_API_BASE_URL == "https://api.groq.com"
    assert s.GROQ_MODEL == "llama-3.3-70b-versatile"
    assert s.GROQ_EXTRACTION_MODEL == "llama-3.1-8b-instant"
    assert s.GROQ_TIMEOUT_SECONDS == 30.0
    assert s.GROQ_MAX_RETRIES == 2
    assert s.SUPABASE_STORAGE_TIMEOUT_SECONDS == 30.0
    assert s.AGENT_LEASE_MINUTES == 10
    assert s.DISCONNECT_SWEEP_INTERVAL_SECONDS == 120
    assert s.DISCONNECT_AUTO_FINALIZE_MINUTES == 10
    assert s.ADMIN_TEST_CANDIDATE_EMAIL == "admin_tester@path2hire.local"
    assert s.ADMIN_TEST_CANDIDATE_NAME == "Admin Tester"
    assert s.SUGGESTED_EVIDENCE_SUFFICIENCY_FLOOR == 0.5
    assert "http://127.0.0.1:5174" in s.cors_origins
    assert s.SUPABASE_PUBLISHABLE_KEY == ""  # optional now: the backend never reads it


def test_local_accepts_the_shipped_defaults():
    s = make()
    assert s.is_local
    assert s.AGENT_API_SECRET == ""


def test_test_environment_is_also_exempt_from_the_refusal():
    assert make(ENVIRONMENT="test").is_local


def test_production_refuses_the_default_secret_key():
    with pytest.raises(ValidationError) as exc:
        make(**{**PRODUCTION_OK, "SECRET_KEY": _DEFAULT_SECRET_KEY})
    assert "SECRET_KEY is the shipped default" in str(exc.value)


def test_production_refuses_a_short_secret_key():
    with pytest.raises(ValidationError) as exc:
        make(**{**PRODUCTION_OK, "SECRET_KEY": "short"})
    assert "shorter than 32" in str(exc.value)


def test_production_refuses_missing_agent_and_livekit_secrets():
    with pytest.raises(ValidationError) as exc:
        make(**{**PRODUCTION_OK, "AGENT_API_SECRET": "", "LIVEKIT_API_SECRET": ""})
    msg = str(exc.value)
    assert "AGENT_API_SECRET is empty" in msg
    assert "LIVEKIT_API_SECRET is empty" in msg


def test_staging_is_checked_like_production():
    with pytest.raises(ValidationError):
        make(**{**PRODUCTION_OK, "ENVIRONMENT": "staging", "SECRET_KEY": _DEFAULT_SECRET_KEY})


def test_production_boots_with_a_complete_config():
    s = make(**PRODUCTION_OK)
    assert not s.is_local
    assert s.ENVIRONMENT == "production"


def test_unknown_environment_is_rejected():
    with pytest.raises(ValidationError):
        make(ENVIRONMENT="prod")


def test_stt_and_tts_provider_keys_are_ignored_not_errors():
    # They belong to the agent; a shared .env still validates.
    s = make(STT_PROVIDER="groq", TTS_PROVIDER="azure")
    assert not hasattr(s, "STT_PROVIDER")


def test_empty_groq_model_falls_back_to_the_default_like_the_old_or_expression():
    s = make(GROQ_MODEL="", GROQ_EXTRACTION_MODEL="")
    assert s.GROQ_MODEL == "llama-3.3-70b-versatile"
    assert s.GROQ_EXTRACTION_MODEL == "llama-3.1-8b-instant"
