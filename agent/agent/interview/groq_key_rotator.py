"""
Multi-key rotation for Groq TTS.

Groq's free-tier TTS quota is a hard per-key, per-model, per-day (TPD)
ceiling — confirmed live against the real account (see
docs/CURRENT_DECISIONS.md / docs/tts-provider-switching.md): one real test
day exhausted it outright (3,536/3,600 used), and a backoff-and-retry-the-
SAME-key strategy structurally cannot help against a DAILY quota — no
amount of waiting seconds or minutes brings it back before the next UTC
day. Rotating to a genuinely different key is the correct fix for this
specific failure mode: a different key has its own, independent quota.

On a 429, the caller (voice_adapter.py) rotates to the NEXT configured key
immediately — no backoff delay, since waiting doesn't help a different
key's quota become more available. Only once every configured key has been
tried does the caller fall back to the existing give-up path (client-side
Web Speech fallback).

Deliberately disk-persisted, not just in-process: each candidate session
runs in its own worker subprocess (confirmed live, same reasoning as
tts_cache.py), so a purely in-memory "which key are we on" would reset to
key 1 for every new session — meaning every fresh session would re-waste
one guaranteed 429 rediscovering that key 1 is already exhausted for the
day. Persisting the last-known-good index means a new session starts
exactly where the last one left off.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import List, Optional

logger = logging.getLogger(__name__)

_STATE_DIR = Path(__file__).resolve().parents[2]
_lock = Lock()


def _load_keys() -> List[str]:
    """GROQ_API_KEY_1 .. GROQ_API_KEY_N, in order, skipping unset/empty
    entries — scans up to 20 slots so adding more keys later than the 7
    this was built for needs no code change, just more env vars. Falls
    back to the single legacy GROQ_API_KEY (already used by STT/LLM) as
    the only key if no numbered keys are configured at all, so this is
    fully backward compatible with an unconfigured/single-key setup."""
    keys = []
    for i in range(1, 21):
        val = os.getenv(f"GROQ_API_KEY_{i}", "").strip()
        if val:
            keys.append(val)
    if not keys:
        legacy = os.getenv("GROQ_API_KEY", "").strip()
        if legacy:
            keys.append(legacy)
    return keys


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _read_state(state_path: Path) -> dict:
    try:
        if state_path.exists():
            return json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.exception("[GROQ-KEY-ROTATOR] Failed to read state file, starting fresh")
    return {}


def _write_state(state_path: Path, index: int) -> None:
    try:
        state_path.write_text(
            json.dumps({"index": index, "date": _today_utc()}), encoding="utf-8"
        )
    except OSError:
        logger.exception("[GROQ-KEY-ROTATOR] Failed to persist state")


class GroqKeyRotator:
    """One instance per TTS plugin (English and Arabic get their own —
    they're independent Groq models with independent quotas, no reason a
    rotation on one should affect the other's starting index).

    namespace: MUST differ between independent rotation needs (e.g. "en"
    vs "ar") — each gets its own persisted state file
    (.groq_key_state_<namespace>.json). Sharing one file between English
    and Arabic would have them silently overwrite each other's rotation
    progress on every write, and both would read whichever happened to be
    saved last regardless of which language it actually came from."""

    def __init__(self, namespace: str, model: str = "", voice: str = ""):
        self._namespace = namespace
        # Stored so rebuild_plugin() can construct a fresh groq.TTS instance
        # after a rotation without the caller (voice_adapter.py) needing to
        # know Groq-specific construction details -- it stays provider-
        # agnostic, only ever calling the abstract tts.TTS interface plus
        # this rotator's own rotate()/rebuild_plugin() pair.
        self._model = model
        self._voice = voice
        self._state_path = _STATE_DIR / f".groq_key_state_{namespace}.json"
        self._keys = _load_keys()
        state = _read_state(self._state_path)
        # A new UTC day means every key's daily quota is fresh again --
        # start back at key 1 rather than staying wherever yesterday's
        # rotation left off (which could be key 7 forever otherwise).
        if state.get("date") == _today_utc():
            self._index = min(state.get("index", 0), max(len(self._keys) - 1, 0))
        else:
            self._index = 0
            _write_state(self._state_path, 0)
        logger.info(
            "[GROQ-KEY-ROTATOR:%s] Loaded %d key(s), starting at index %d",
            namespace, len(self._keys), self._index,
        )

    @property
    def total_keys(self) -> int:
        return len(self._keys)

    def current_key(self) -> Optional[str]:
        if not self._keys:
            return None
        return self._keys[self._index]

    def rotate(self) -> Optional[str]:
        """Advances to the next key and persists it. Returns the new key,
        or None if every configured key has already been tried (caller
        should give up / fall back)."""
        with _lock:
            if self._index + 1 >= len(self._keys):
                return None
            self._index += 1
            _write_state(self._state_path, self._index)
            logger.warning(
                "[GROQ-KEY-ROTATOR:%s] Rotated to key %d/%d",
                self._namespace, self._index + 1, len(self._keys),
            )
            return self._keys[self._index]

    @property
    def current_position(self) -> int:
        """1-based, for logging/broadcast — "key 2 of 7", not "index 1"."""
        return self._index + 1

    def rebuild_plugin(self):
        """Constructs a fresh groq.TTS instance bound to the CURRENT key
        (call rotate() first if you want the next one) -- api_key is fixed
        at construction time on groq.TTS, there's no in-place "swap the
        key" method on the plugin itself, so a rotation means building a
        new instance, not mutating the old one. Re-attaches the same
        provider_name/model_name/groq_model/groq_voice/key_rotator
        attributes main.py originally set, so anything downstream reading
        them (voice_adapter.py's cache-key logic, logging) keeps working
        unchanged after a rotation.

        Imports the groq plugin locally, not at module level -- this
        module is inherently Groq-specific already (unlike voice_adapter.py,
        which stays provider-agnostic and only ever calls this method
        through the abstract interface, never imports groq itself)."""
        from livekit.plugins import groq as groq_plugin

        plugin = groq_plugin.TTS(model=self._model, voice=self._voice, api_key=self.current_key())
        plugin.provider_name = "Groq"
        plugin.model_name = self._model
        plugin.groq_model = self._model
        plugin.groq_voice = self._voice
        plugin.key_rotator = self
        return plugin
