"""H1-C: AgentSettings — defaults equal the literals the inline os.getenv
reads used, parsing semantics (floor + unparseable→default) are preserved,
and the pre-session validation names exactly what is missing."""
import os
from pathlib import Path

import pytest

from agent.config import AGENT_DIR, AgentSettings, get_settings, reset_settings

ENV_KEYS = [
    "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "GROQ_API_KEY", "AGENT_API_SECRET",
    "BACKEND_INTERNAL_URL", "LLM_MODEL", "GROQ_STT_MODEL", "STT_ENDPOINT_DELAY_SECONDS", "TTS_PROVIDER",
    "GROQ_TTS_ENGLISH_MODEL", "GROQ_TTS_ENGLISH_VOICE", "GROQ_TTS_ARABIC_MODEL", "GROQ_TTS_ARABIC_VOICE",
    "AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION", "AZURE_TTS_ENGLISH_VOICE", "AZURE_TTS_ARABIC_VOICE",
    "VAD_MIN_SILENCE_DURATION_SECONDS", "WAITING_ROOM_TIMEOUT_SECONDS", "LEASE_RENEWAL_INTERVAL_SECONDS",
    "AGENT_NAME", "JOB_MEMORY_LIMIT_MB", "JOB_MEMORY_WARN_MB", "AGENT_STATE_DIR", "TTS_CACHE_DIR",
] + [f"GROQ_API_KEY_{i}" for i in range(1, 21)]


@pytest.fixture
def clean_env(monkeypatch):
    for k in ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    reset_settings()
    yield monkeypatch
    reset_settings()


def test_defaults_match_the_lifted_literals(clean_env):
    s = AgentSettings()
    assert s.GROQ_STT_MODEL == "whisper-large-v3-turbo"
    assert s.STT_ENDPOINT_DELAY_SECONDS == 0.8
    assert s.TTS_PROVIDER == "azure"
    assert s.GROQ_TTS_ENGLISH_MODEL == "canopylabs/orpheus-v1-english"
    assert s.GROQ_TTS_ENGLISH_VOICE == "troy"
    assert s.GROQ_TTS_ARABIC_MODEL == "canopylabs/orpheus-arabic-saudi"
    assert s.GROQ_TTS_ARABIC_VOICE == "abdullah"
    assert s.AZURE_TTS_ENGLISH_VOICE == "en-US-AvaNeural"
    assert s.AZURE_TTS_ARABIC_VOICE == "ar-SA-HamedNeural"
    assert s.VAD_MIN_SILENCE_DURATION_SECONDS == 0.85
    assert s.WAITING_ROOM_TIMEOUT_SECONDS == 300.0
    assert s.LEASE_RENEWAL_INTERVAL_SECONDS == 300
    assert s.AGENT_NAME == "" and s.JOB_MEMORY_LIMIT_MB == 0
    assert s.AGENT_STATE_DIR == AGENT_DIR
    assert s.tts_cache_dir == AGENT_DIR / ".tts_cache"


@pytest.mark.parametrize("name,default,floor", [
    ("VAD_MIN_SILENCE_DURATION_SECONDS", 0.85, 0.55),
    ("STT_ENDPOINT_DELAY_SECONDS", 0.8, 0.25),
    ("WAITING_ROOM_TIMEOUT_SECONDS", 300.0, 1.0),
])
def test_numeric_reads_keep_the_inline_semantics(clean_env, name, default, floor):
    clean_env.setenv(name, "not-a-number")
    assert getattr(AgentSettings(), name) == default          # ValueError -> default
    clean_env.setenv(name, "0.0001")
    assert getattr(AgentSettings(), name) == floor            # max(floor, value)
    clean_env.setenv(name, str(floor + 1))
    assert getattr(AgentSettings(), name) == floor + 1


def test_tts_provider_is_case_insensitive_and_validated(clean_env):
    clean_env.setenv("TTS_PROVIDER", "GROQ")
    assert AgentSettings().TTS_PROVIDER == "groq"
    clean_env.setenv("TTS_PROVIDER", "elevenlabs")
    with pytest.raises(Exception):
        AgentSettings()


def test_groq_tts_keys_scan_numbered_slots_then_fall_back(clean_env):
    clean_env.setenv("GROQ_API_KEY", "legacy")
    assert AgentSettings().groq_tts_keys == ["legacy"]
    clean_env.setenv("GROQ_API_KEY_1", "k1")
    clean_env.setenv("GROQ_API_KEY_3", "k3")       # gaps are fine
    clean_env.setenv("GROQ_API_KEY_2", "   ")      # blank slot skipped
    assert AgentSettings().groq_tts_keys == ["k1", "k3"]


def test_missing_for_job_lists_every_required_var_including_llm_model_and_azure(clean_env):
    assert AgentSettings().missing_for_job() == [
        "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "GROQ_API_KEY",
        "AGENT_API_SECRET", "BACKEND_INTERNAL_URL", "LLM_MODEL", "AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION",
    ]
    for k in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "GROQ_API_KEY",
              "AGENT_API_SECRET", "BACKEND_INTERNAL_URL"):
        clean_env.setenv(k, "x")
    assert AgentSettings().missing_for_job() == ["LLM_MODEL", "AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION"]
    clean_env.setenv("LLM_MODEL", "m")
    clean_env.setenv("TTS_PROVIDER", "groq")       # groq path needs no Azure credentials
    assert AgentSettings().missing_for_job() == []


def test_state_and_cache_dirs_are_configurable(clean_env, tmp_path: Path):
    clean_env.setenv("AGENT_STATE_DIR", str(tmp_path / "state"))
    s = AgentSettings()
    assert s.AGENT_STATE_DIR == tmp_path / "state"
    assert s.tts_cache_dir == tmp_path / "state" / ".tts_cache"
    clean_env.setenv("TTS_CACHE_DIR", str(tmp_path / "cache"))
    assert AgentSettings().tts_cache_dir == tmp_path / "cache"


def test_get_settings_is_cached_and_has_no_env_side_effects(clean_env):
    before = dict(os.environ)
    a = get_settings()
    assert get_settings() is a
    assert dict(os.environ) == before               # no dotenv load from get_settings()
    clean_env.setenv("AGENT_NAME", "himma")
    assert get_settings().AGENT_NAME == ""          # still cached
    reset_settings()
    assert get_settings().AGENT_NAME == "himma"
