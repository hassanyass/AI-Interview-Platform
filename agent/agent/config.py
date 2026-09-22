"""Agent worker configuration — the single place every environment
variable the worker reads is declared, typed, defaulted and validated.

docs/production-hardening-plan.md H1-C. Before this module the 20 reads were
scattered over main.py, groq_provider.py, groq_key_rotator.py and
voice_adapter.py, each with its own parsing and defaults. Defaults here equal
the literals those sites used, so an unchanged .env behaves exactly as before.

Precedence is deliberately the worker's historical one: main._load_env()
(-> load_env_files here) loads the repo-root .env with ``override=True`` (the
file beats inherited process variables, so restarting the worker picks up a
rotated key), then agent/.env fills gaps. That load happens only at
entrypoint start and in __main__ -- never here. ``get_settings()`` reads the
process environment as it is, so importing this module, building an adapter
in a test, or calling get_settings() has no side effect on os.environ
(Phase 7E: an import-time override once leaked GROQ_API_KEY into pytest's
shared process, and today it would also clobber the test DATABASE_URL).
Job processes inherit the loaded environment from the worker process.

One env read intentionally stays outside this module:
``VERBAL_FOLLOWUP_TIME_BONUS_SECONDS`` in interview/controller.py -- a frozen
file (AGENTS.md §2). It is documented in agent/.env.example.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

AGENT_DIR = Path(__file__).resolve().parents[1]      # <repo>/agent
REPO_ROOT = AGENT_DIR.parent

_DEFAULTS = {
    "VAD_MIN_SILENCE_DURATION_SECONDS": (0.85, 0.55),   # (default, floor)
    "STT_ENDPOINT_DELAY_SECONDS": (0.8, 0.25),
    "WAITING_ROOM_TIMEOUT_SECONDS": (300.0, 1.0),
}


def load_env_files() -> None:
    """Repo .env wins over inherited variables; agent/.env fills gaps only.
    Same semantics main.py's ``_load_env`` has had since Phase 7E."""
    load_dotenv(REPO_ROOT / ".env", override=True)
    load_dotenv(AGENT_DIR / ".env", override=False)


class AgentSettings(BaseSettings):
    # ── Required for any interview job (validate_for_job) ──────────────────
    LIVEKIT_URL: str = ""
    LIVEKIT_API_KEY: str = ""
    LIVEKIT_API_SECRET: str = ""
    GROQ_API_KEY: str = ""
    """LLM + STT key; also the only TTS key when no GROQ_API_KEY_n is set."""
    AGENT_API_SECRET: str = ""
    """Must equal the backend's AGENT_API_SECRET (X-Agent-Secret on /internal/*)."""
    BACKEND_INTERNAL_URL: str = ""
    """Backend base URL for /internal/*."""
    LLM_MODEL: str = ""
    """Groq model for the live interview (GroqProvider). Required."""
    LLM_TIMEOUT_SECONDS: float = 30.0
    """Per-request timeout for the live LLM call. Bounds how long a turn (and the turn lock) can hang."""
    LLM_MAX_RETRIES: int = 1
    """Groq SDK retries on transient failures."""

    # ── Backend (/internal/*) client ───────────────────────────────────────
    BACKEND_TIMEOUT_SECONDS: float = 10.0
    """Per-request timeout for backend persistence calls."""
    BACKEND_RETRY_ATTEMPTS: int = 3
    """Retries on transport errors / 5xx (never on 4xx); backoff 0.5s, 1s, 2s."""
    LEASE_ERROR_SHUTDOWN_AFTER: int = 3
    """Consecutive lease-renewal transport errors before the worker stops driving the session
    (3 x 5 min > the backend's 10-minute lease: by then another worker may own it)."""

    # ── Room / data channel guards ─────────────────────────────────────────
    STT_RESTART_MAX: int = 2
    """How many times a crashed STT stream is rebuilt before transcription is given up for the session."""
    UI_COMMAND_MAX_BYTES: int = 16384
    """Largest ui_command data packet accepted."""

    # ── STT ────────────────────────────────────────────────────────────────
    GROQ_STT_MODEL: str = "whisper-large-v3-turbo"
    STT_ENDPOINT_DELAY_SECONDS: float = 0.8
    """Candidate end-of-turn coalescing delay; floor 0.25."""

    # ── TTS ────────────────────────────────────────────────────────────────
    TTS_PROVIDER: Literal["azure", "groq"] = "azure"
    """Code default is azure (2026-08-27 quota decision); the deployed .env selects groq."""
    GROQ_TTS_ENGLISH_MODEL: str = "canopylabs/orpheus-v1-english"
    GROQ_TTS_ENGLISH_VOICE: str = "troy"
    GROQ_TTS_ARABIC_MODEL: str = "canopylabs/orpheus-arabic-saudi"
    GROQ_TTS_ARABIC_VOICE: str = "abdullah"
    AZURE_SPEECH_KEY: str = ""
    """Read by the LiveKit azure plugin; required when TTS_PROVIDER=azure."""
    AZURE_SPEECH_REGION: str = ""
    AZURE_TTS_ENGLISH_VOICE: str = "en-US-AvaNeural"
    AZURE_TTS_ARABIC_VOICE: str = "ar-SA-HamedNeural"

    # ── Voice activity / pacing ────────────────────────────────────────────
    VAD_MIN_SILENCE_DURATION_SECONDS: float = 0.85
    """Silero min_silence_duration; floor 0.55."""
    WAITING_ROOM_TIMEOUT_SECONDS: float = 300.0
    """Auto-proceed timeout in the waiting room; floor 1.0."""
    LEASE_RENEWAL_INTERVAL_SECONDS: int = 300
    """How often the worker renews its session lease with the backend."""

    # ── Logging (H3) ───────────────────────────────────────────────────────
    LOG_FORMAT: Literal["json", "text", "auto"] = "auto"
    """auto = text in `dev` mode / local, json otherwise (logging_setup.py). Same line shape as the backend."""
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "local"
    """Stamped on every log line as `env`; shares the backend's variable."""

    # ── Worker process ─────────────────────────────────────────────────────
    AGENT_NAME: str = ""
    """LiveKit agent_name for explicit dispatch; empty = automatic dispatch (today's behaviour)."""
    JOB_MEMORY_LIMIT_MB: int = 0
    """Kill a job process above this RSS; 0 = SDK default (disabled)."""
    JOB_MEMORY_WARN_MB: int = 0
    """Warn above this RSS; 0 = SDK default."""
    AGENT_STATE_DIR: Path = Field(default=AGENT_DIR)
    """Where the Groq key-rotation state files live. Default = the agent/ directory (as before)."""
    TTS_CACHE_DIR: Path | None = None
    """Synthesised-audio cache. Default = <AGENT_STATE_DIR>/.tts_cache."""

    model_config = SettingsConfigDict(extra="ignore")

    # -- parsing semantics preserved from the inline reads: an unparseable
    #    value falls back to the default, and values are floored.
    @field_validator("VAD_MIN_SILENCE_DURATION_SECONDS", "STT_ENDPOINT_DELAY_SECONDS",
                     "WAITING_ROOM_TIMEOUT_SECONDS", mode="before")
    @classmethod
    def _unparseable_means_default(cls, v, info):
        default, _floor = _DEFAULTS[info.field_name]
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    @field_validator("VAD_MIN_SILENCE_DURATION_SECONDS", "STT_ENDPOINT_DELAY_SECONDS",
                     "WAITING_ROOM_TIMEOUT_SECONDS", mode="after")
    @classmethod
    def _apply_floor(cls, v: float, info) -> float:
        _default, floor = _DEFAULTS[info.field_name]
        return max(floor, v)

    @field_validator("TTS_PROVIDER", mode="before")
    @classmethod
    def _lowercase_provider(cls, v):
        return v.lower() if isinstance(v, str) else v

    # -- derived
    def log_format_for(self, devmode: bool) -> str:
        if self.LOG_FORMAT != "auto":
            return self.LOG_FORMAT
        return "text" if (devmode or self.ENVIRONMENT in ("local", "test")) else "json"

    @property
    def tts_cache_dir(self) -> Path:
        return self.TTS_CACHE_DIR or (self.AGENT_STATE_DIR / ".tts_cache")

    @property
    def groq_tts_keys(self) -> list[str]:
        """GROQ_API_KEY_1 .. GROQ_API_KEY_20 in order, skipping unset slots;
        falls back to the single GROQ_API_KEY (groq_key_rotator._load_keys)."""
        keys = [v for i in range(1, 21) if (v := os.getenv(f"GROQ_API_KEY_{i}", "").strip())]
        return keys or ([self.GROQ_API_KEY.strip()] if self.GROQ_API_KEY.strip() else [])

    def missing_for_job(self) -> list[str]:
        """Names of the variables an interview job cannot run without. Checked
        before the worker touches the session, so a misconfiguration can no
        longer strand a session IN_PROGRESS."""
        required = ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET",
                    "GROQ_API_KEY", "AGENT_API_SECRET", "BACKEND_INTERNAL_URL", "LLM_MODEL"]
        if self.TTS_PROVIDER == "azure":
            required += ["AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION"]
        return [name for name in required if not getattr(self, name)]


@lru_cache(maxsize=1)
def get_settings() -> AgentSettings:
    return AgentSettings()


def reset_settings() -> None:
    """For tests: forget the cached settings so the next get_settings() re-reads the environment."""
    get_settings.cache_clear()
