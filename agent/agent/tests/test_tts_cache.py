"""H4-B: the synthesized-audio cache.

The cache exists to reuse the fixed SYSTEM_MESSAGES audio across sessions
and processes. Its one hard requirement is that a key can never collide
across voices: serving Arabic audio for an English line, or one Azure
voice's audio after the voice was changed, is worse than no cache at all.
"""
import pytest

from agent.interview import tts_cache


@pytest.fixture(autouse=True)
def cache_in_tmp(tmp_path, monkeypatch):
    """Point the module-level cache dir at a per-test directory; restore it
    afterwards so no other test (or a developer's real cache) is touched."""
    original = tts_cache._CACHE_DIR
    tts_cache.configure(tmp_path / "tts")
    yield tmp_path / "tts"
    monkeypatch.setattr(tts_cache, "_CACHE_DIR", original, raising=False)


AUDIO = b"\x00\x01" * 64


# ── the key ───────────────────────────────────────────────────────────────

def test_every_input_that_changes_the_audio_changes_the_key():
    base = tts_cache.cache_key("groq", "voice-a", "en", "No problem, let's move on.")
    variants = {
        "provider": tts_cache.cache_key("azure", "voice-a", "en", "No problem, let's move on."),
        "voice": tts_cache.cache_key("groq", "voice-b", "en", "No problem, let's move on."),
        "language": tts_cache.cache_key("groq", "voice-a", "ar", "No problem, let's move on."),
        "text": tts_cache.cache_key("groq", "voice-a", "en", "Let's skip this one."),
    }
    for field, key in variants.items():
        assert key != base, f"changing the {field} did not change the cache key"
    assert len(set(variants.values())) == len(variants)


def test_the_same_inputs_give_the_same_key_every_time():
    args = ("groq", "voice-a", "en", "Thanks, that's helpful.")
    assert tts_cache.cache_key(*args) == tts_cache.cache_key(*args)


# ── round trip ────────────────────────────────────────────────────────────

def test_saved_audio_comes_back_and_a_miss_is_none(cache_in_tmp):
    key = tts_cache.cache_key("groq", "voice-a", "en", "Saved line.")
    assert tts_cache.load(key) is None          # cold

    tts_cache.save(key, AUDIO)
    assert tts_cache.load(key) == AUDIO
    assert tts_cache.load("0" * 64) is None     # a key nothing was written for


def test_saving_leaves_no_temporary_file_behind(cache_in_tmp):
    """The write is write-then-rename so a reader never sees a half-written
    file; the temp file must not survive the write."""
    key = tts_cache.cache_key("groq", "voice-a", "en", "Atomic line.")
    tts_cache.save(key, AUDIO)
    assert [p.name for p in cache_in_tmp.iterdir()] == [f"{key}.pcm"]


def test_empty_audio_is_not_cached(cache_in_tmp):
    """A failed synthesis must not poison the cache with silence that every
    later session would replay."""
    key = tts_cache.cache_key("groq", "voice-a", "en", "Nothing came back.")
    tts_cache.save(key, b"")
    assert tts_cache.load(key) is None
    assert list(cache_in_tmp.iterdir()) == []


def test_an_unreadable_entry_degrades_to_a_miss_instead_of_raising(cache_in_tmp, monkeypatch):
    """A cache problem must cost a re-synthesis, never the turn."""
    key = tts_cache.cache_key("groq", "voice-a", "en", "Unreadable.")
    tts_cache.save(key, AUDIO)

    def boom(*_args, **_kwargs):
        raise OSError("disk went away")

    monkeypatch.setattr("pathlib.Path.read_bytes", boom)
    assert tts_cache.load(key) is None


def test_a_failed_write_does_not_raise(cache_in_tmp, monkeypatch):
    def boom(*_args, **_kwargs):
        raise OSError("read-only volume")

    monkeypatch.setattr("pathlib.Path.write_bytes", boom)
    tts_cache.save(tts_cache.cache_key("groq", "voice-a", "en", "Nope."), AUDIO)   # no exception


def test_configure_creates_the_directory_on_first_use(tmp_path):
    target = tmp_path / "nested" / "cache"
    tts_cache.configure(target)
    assert not target.exists()                  # not created until something is stored
    tts_cache.save(tts_cache.cache_key("groq", "v", "en", "x"), AUDIO)
    assert target.is_dir()
