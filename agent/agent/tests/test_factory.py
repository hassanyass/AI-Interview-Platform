"""H1-C: agent.providers.factory builds the voice pipeline from settings.
No network: plugin constructors only store configuration; the Groq TTS path
is exercised with injected keys and a temp state dir, VAD prewarm loads the
bundled Silero model once."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.config import AgentSettings, reset_settings
from agent.interview import tts_cache
from agent.providers import factory


@pytest.fixture
def settings(monkeypatch, tmp_path: Path) -> AgentSettings:
    for k in ("AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION", "TTS_PROVIDER", "GROQ_API_KEY", "LLM_MODEL"):
        monkeypatch.delenv(k, raising=False)
    for i in range(1, 21):
        monkeypatch.delenv(f"GROQ_API_KEY_{i}", raising=False)
    reset_settings()
    yield AgentSettings(
        GROQ_API_KEY="gk", LLM_MODEL="llm-model", TTS_PROVIDER="groq",
        GROQ_API_KEY_1="ignored-here",  # extra=ignore; keys come from the env scan
        AGENT_STATE_DIR=tmp_path,
    )
    reset_settings()


def test_build_llm_uses_settings_not_env(settings):
    llm = factory.build_llm(settings)
    assert llm.model == "llm-model"


def test_build_stt_passes_the_interview_language(settings):
    stt = factory.build_stt("ar", settings)
    # livekit.plugins.groq.STT keeps its options on ._opts
    assert stt._opts.languages == ["ar"] or stt._opts.languages == "ar"
    assert stt._opts.model == "whisper-large-v3-turbo"


def test_build_tts_groq_english_uses_rotator_with_injected_keys_and_state_dir(settings, monkeypatch, tmp_path):
    monkeypatch.setenv("GROQ_API_KEY_1", "k1")
    monkeypatch.setenv("GROQ_API_KEY_2", "k2")
    plugin, rotator = factory.build_tts("en", settings)
    assert rotator is not None
    assert rotator.total_keys == 2 and rotator.current_key() == "k1"
    assert (tmp_path / ".groq_key_state_en.json").exists()      # state written under AGENT_STATE_DIR
    assert plugin.model_name == "canopylabs/orpheus-v1-english"
    assert tts_cache._cache_dir() == tmp_path / ".tts_cache"    # cache follows the state dir


def test_build_tts_groq_arabic_voice_is_configurable(settings, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY_1", "k1")
    plugin, rotator = factory.build_tts("ar", settings)
    assert rotator is not None and rotator.total_keys == 1
    assert plugin.model_name == "canopylabs/orpheus-arabic-saudi"
    s2 = settings.model_copy(update={"GROQ_TTS_ARABIC_VOICE": "fatima"})
    plugin2, _ = factory.build_tts("ar", s2)
    assert plugin2.groq_voice == "fatima"


def test_build_tts_azure_reads_credentials_from_env_and_needs_no_rotator(settings, monkeypatch):
    monkeypatch.setenv("AZURE_SPEECH_KEY", "azk")
    monkeypatch.setenv("AZURE_SPEECH_REGION", "uaenorth")
    s = settings.model_copy(update={"TTS_PROVIDER": "azure"})
    plugin, rotator = factory.build_tts("en", s)
    assert rotator is None
    assert plugin.provider_name == "Azure" and plugin.model_name == "en-US-AvaNeural"


def test_prewarm_loads_vad_once_and_vad_for_reuses_it(settings, monkeypatch):
    calls = []
    monkeypatch.setattr(factory, "build_vad", lambda s=None: calls.append(1) or "VAD")
    proc = SimpleNamespace(userdata={})
    factory.prewarm(proc)
    assert proc.userdata[factory.VAD_USERDATA_KEY] == "VAD" and calls == [1]
    assert factory.vad_for(proc) == "VAD" and calls == [1]       # reused, not rebuilt
    assert factory.vad_for(SimpleNamespace(userdata={})) == "VAD" and calls == [1, 1]  # fallback path builds


def test_build_vad_applies_the_configured_min_silence(settings):
    vad = factory.build_vad(settings.model_copy(update={"VAD_MIN_SILENCE_DURATION_SECONDS": 0.9}))
    assert vad._opts.min_silence_duration == pytest.approx(0.9)
