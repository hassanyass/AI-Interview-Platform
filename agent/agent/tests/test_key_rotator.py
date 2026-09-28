"""H4-B: the Groq TTS key rotator.

Rotation state is persisted precisely because each candidate session runs
in its own worker process -- an in-memory index would send every new
session back to the exhausted first key. The properties worth pinning are
therefore about the file: one per namespace, survives a restart, resets on
a new UTC day, and never leaves the worker unable to start because the
file is unreadable.
"""
import json

import pytest

from agent.interview.groq_key_rotator import GroqKeyRotator

KEYS = ["key-1", "key-2", "key-3"]


def rotator(tmp_path, namespace="en", keys=None):
    return GroqKeyRotator(namespace, model="m", voice="v", keys=keys if keys is not None else KEYS, state_dir=tmp_path)


def test_a_fresh_rotator_starts_on_the_first_key(tmp_path):
    r = rotator(tmp_path)
    assert r.current_key() == "key-1"
    assert r.total_keys == 3 and r.current_position == 1


def test_rotate_walks_the_keys_then_reports_exhaustion(tmp_path):
    r = rotator(tmp_path)
    assert r.rotate() == "key-2"
    assert r.rotate() == "key-3"
    assert r.rotate() is None, "a fourth rotation must report exhaustion, not wrap around"
    assert r.current_key() == "key-3", "an exhausted rotator stays on the last key"
    assert r.current_position == 3


def test_the_position_survives_a_restart(tmp_path):
    rotator(tmp_path).rotate()                       # now on key-2, persisted
    assert rotator(tmp_path).current_key() == "key-2"


def test_each_namespace_keeps_its_own_state(tmp_path):
    """English and Arabic are independent Groq models with independent
    quotas; sharing one file would have them overwrite each other."""
    english = rotator(tmp_path, "en")
    english.rotate()
    arabic = rotator(tmp_path, "ar")

    assert arabic.current_key() == "key-1", "Arabic inherited English's rotation"
    assert (tmp_path / ".groq_key_state_en.json").exists()
    assert (tmp_path / ".groq_key_state_ar.json").exists()


def test_a_new_utc_day_starts_again_at_the_first_key(tmp_path):
    """The daily quota is what rotation works around, so yesterday's index
    must not pin every session to the last key forever."""
    r = rotator(tmp_path)
    r.rotate(); r.rotate()
    state_file = tmp_path / ".groq_key_state_en.json"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["index"] == 2
    state_file.write_text(json.dumps({"index": 2, "date": "2000-01-01"}), encoding="utf-8")

    assert rotator(tmp_path).current_key() == "key-1"


def test_the_same_day_resumes_where_it_left_off(tmp_path):
    r = rotator(tmp_path)
    r.rotate()
    assert rotator(tmp_path).current_position == 2


def test_a_corrupt_state_file_starts_fresh_instead_of_crashing(tmp_path):
    (tmp_path / ".groq_key_state_en.json").write_text("{ truncated", encoding="utf-8")
    assert rotator(tmp_path).current_key() == "key-1"


def test_a_stale_index_beyond_the_configured_keys_is_clamped(tmp_path):
    """Keys can be removed from the environment between runs; the persisted
    index must not index past the end of the shorter list."""
    (tmp_path / ".groq_key_state_en.json").write_text(
        json.dumps({"index": 6, "date": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).strftime("%Y-%m-%d")}), encoding="utf-8")
    r = rotator(tmp_path, keys=["only-key"])
    assert r.current_key() == "only-key" and r.current_position == 1


def test_no_configured_keys_is_survivable(tmp_path):
    r = rotator(tmp_path, keys=[])
    assert r.total_keys == 0
    assert r.current_key() is None
    assert r.rotate() is None


def test_the_state_write_is_atomic(tmp_path):
    """Written via a temp file and os.replace (H2-D), so a crash mid-write
    cannot leave truncated JSON that every later start fails to parse."""
    r = rotator(tmp_path)
    r.rotate()
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == [".groq_key_state_en.json"], f"temp file left behind: {names}"


@pytest.mark.parametrize("namespace", ["en", "ar"])
def test_the_state_file_is_named_after_the_namespace(tmp_path, namespace):
    rotator(tmp_path, namespace).rotate()
    assert (tmp_path / f".groq_key_state_{namespace}.json").exists()
