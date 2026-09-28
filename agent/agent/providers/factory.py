"""Build the voice-pipeline providers from AgentSettings.

Each ``build_*`` is the body that used to sit inline in main.entrypoint
(2026-08/09 decisions and their rationale preserved in the comments), now
parameterised by settings instead of scattered os.getenv reads.
"""
from __future__ import annotations

import logging
from typing import Optional, Tuple

from livekit.agents import JobProcess
from livekit.plugins import azure, groq, silero

from agent.config import AgentSettings, get_settings
from agent.interview import tts_cache
from agent.interview.groq_key_rotator import GroqKeyRotator
from agent.llm.groq_provider import GroqProvider

logger = logging.getLogger("agent")

VAD_USERDATA_KEY = "vad"


def build_llm(settings: Optional[AgentSettings] = None) -> GroqProvider:
    s = settings or get_settings()
    return GroqProvider(api_key=s.GROQ_API_KEY, model=s.LLM_MODEL,
                        timeout_seconds=s.LLM_TIMEOUT_SECONDS, max_retries=s.LLM_MAX_RETRIES)


def build_stt(language: str, settings: Optional[AgentSettings] = None):
    s = settings or get_settings()
    # groq.STT defaults to language="en" (forcing Whisper to transcribe as
    # English regardless of what's actually spoken) when not given explicitly
    # -- an Arabic interview was getting its candidate audio transcribed as
    # English gibberish as a result. Whisper's `language` param takes the same
    # ISO-639-1 codes session_data already uses ("en"/"ar").
    return groq.STT(model=s.GROQ_STT_MODEL, language=language, api_key=s.GROQ_API_KEY)


def build_tts(language: str, settings: Optional[AgentSettings] = None) -> Tuple[object, Optional[GroqKeyRotator]]:
    """Returns (tts_plugin, key_rotator). The rotator is only present on the
    Groq path; voice_adapter uses it to rebuild the plugin after a 429.

    Audit fix (2026-08-27): Groq's TTS free tier is a hard per-key daily
    ceiling, so Azure Speech became the code-default provider; the Groq path
    is kept fully intact -- TTS_PROVIDER=groq selects it (the deployed .env
    does). Both plugin classes share livekit.agents.tts.TTS base machinery,
    so RT-B0's metrics listeners and RT-B1's interruption fix are unaffected
    by the choice.
    """
    s = settings or get_settings()
    tts_cache.configure(s.tts_cache_dir)
    provider = s.TTS_PROVIDER
    logger.info("Interview language: %s", language)
    logger.info("TTS provider: %s", provider)

    if language == "ar":
        if provider == "azure":
            # ar-SA has exactly two neural voices: Zariyah (female) and Hamed
            # (male). Hamed matches InterviewerCharacter.tsx's male-presenting
            # avatar already shown to every candidate.
            voice = s.AZURE_TTS_ARABIC_VOICE
            logger.info("TTS voice: %s", voice)
            plugin = azure.TTS(voice=voice, language="ar-SA")
            plugin.provider_name = "Azure"
            plugin.model_name = voice
            return plugin, None
        # Groq's TTS 429 is a per-KEY daily quota, so multi-key rotation
        # replaces waiting-and-retrying the same exhausted key. One rotator
        # per language: independent models, independent quotas.
        model, voice = s.GROQ_TTS_ARABIC_MODEL, s.GROQ_TTS_ARABIC_VOICE
        rotator = GroqKeyRotator("ar", model=model, voice=voice, keys=s.groq_tts_keys, state_dir=s.AGENT_STATE_DIR)
        logger.info("TTS model: %s", model)
        logger.info("TTS voice: %s", voice)
        logger.info("Groq key rotator: key %d/%d", rotator.current_position, rotator.total_keys)
        return rotator.rebuild_plugin(), rotator

    if provider == "azure":
        # en-US-AvaNeural: tuned for conversational dialogue, generally
        # available (not the Dragon-HD preview tier).
        voice = s.AZURE_TTS_ENGLISH_VOICE
        logger.info("TTS voice: %s", voice)
        plugin = azure.TTS(voice=voice, language="en-US")
        plugin.provider_name = "Azure"
        plugin.model_name = voice
        return plugin, None
    model, voice = s.GROQ_TTS_ENGLISH_MODEL, s.GROQ_TTS_ENGLISH_VOICE
    rotator = GroqKeyRotator("en", model=model, voice=voice, keys=s.groq_tts_keys, state_dir=s.AGENT_STATE_DIR)
    logger.info("TTS model: %s", model)
    logger.info("TTS voice: %s", voice)
    logger.info("Groq key rotator: key %d/%d", rotator.current_position, rotator.total_keys)
    return rotator.rebuild_plugin(), rotator


def build_vad(settings: Optional[AgentSettings] = None):
    s = settings or get_settings()
    logger.info(
        "Voice endpointing: Silero min_silence_duration=%.2fs, candidate endpoint coalescing enabled",
        s.VAD_MIN_SILENCE_DURATION_SECONDS,
    )
    return silero.VAD.load(min_silence_duration=s.VAD_MIN_SILENCE_DURATION_SECONDS)


def prewarm(proc: JobProcess) -> None:
    """WorkerOptions.prewarm_fnc: runs once per job process, before any job.
    Loading the Silero ONNX model here means an interview no longer pays for
    it on the event loop at connect time. Also the first chance to put the
    job process's logging into shape (H3)."""
    import sys
    from agent.logging_setup import configure_worker_logging
    s = get_settings()
    configure_worker_logging(log_format=s.log_format_for("dev" in sys.argv[1:2]), level=s.LOG_LEVEL, environment=s.ENVIRONMENT)
    proc.userdata[VAD_USERDATA_KEY] = build_vad()


def vad_for(ctx_proc: JobProcess):
    """The prewarmed VAD if present (normal path), else load it now (tests,
    or a runner that skipped prewarm)."""
    vad = ctx_proc.userdata.get(VAD_USERDATA_KEY) if ctx_proc is not None else None
    return vad or build_vad()
