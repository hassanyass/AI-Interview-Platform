"""
Disk-backed cache for synthesized audio of FIXED, non-personalized system
messages (agent/llm/prompts.py's SYSTEM_MESSAGES dict — the same short
acknowledgment/skip/end-of-section strings spoken verbatim across every
candidate and every session, never containing a name, question text, or
any other per-candidate content).

Deliberately disk-backed, not just an in-memory dict: each candidate
session runs in its own worker subprocess (confirmed live — "job runner
initialized... tid: NNNN" per session), so an in-memory cache would never
be shared ACROSS sessions, only within one — most of the real savings
(the same "No problem, let's skip this one and move on." spoken by
candidate #1 today and candidate #50 tomorrow) only materializes with a
cache that survives across processes. A plain local directory is free,
requires no new infrastructure/dependency, and is safe for a
single-machine dev/test deployment.

Deliberately NOT used for LLM-generated conversational text (greetings,
question presentations, follow-ups, the CLOSING goodbye) — that's
different content nearly every time (candidate name, generated wording),
and caching it would be actively wrong: replaying candidate A's spoken
name to candidate B, or answering a personalized greeting with stale
cached audio. The caller (voice_adapter.py) is responsible for only
passing text that's a real, verified SYSTEM_MESSAGES entry.
"""
from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).resolve().parents[2] / ".tts_cache"


def _cache_dir() -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR


def cache_key(provider: str, voice: str, language: str, text: str) -> str:
    """Stable key over exactly the inputs that change the resulting audio —
    a voice/provider/language switch (e.g. Azure -> Groq, or a different
    Azure voice picked via env var) must never serve stale audio from a
    different voice."""
    raw = f"{provider}|{voice}|{language}|{text}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def load(key: str) -> bytes | None:
    path = _cache_dir() / f"{key}.pcm"
    if not path.exists():
        return None
    try:
        return path.read_bytes()
    except OSError:
        logger.exception("[TTS-CACHE] Failed to read cache entry %s", key)
        return None


def save(key: str, data: bytes) -> None:
    if not data:
        return
    path = _cache_dir() / f"{key}.pcm"
    try:
        # Write-then-rename: avoids a half-written file being read as a
        # cache hit if two turns race to cache the exact same fixed string
        # at the same time (e.g. two sections both ending within the same
        # process's queue).
        tmp_path = path.with_suffix(".pcm.tmp")
        tmp_path.write_bytes(data)
        os.replace(tmp_path, path)
    except OSError:
        logger.exception("[TTS-CACHE] Failed to write cache entry %s", key)
