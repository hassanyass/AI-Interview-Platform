"""H4-B: `build_context` for real -- what a reconnecting candidate comes
back to.

Every runtime test so far replaced this function with a fake
(`test_runtime.py`'s `fake_build_context`), so the ~110 lines that decide a
resumed session's phase, sequence numbers, ordered-question pointer,
background questions, history and records had no direct coverage. A
mistake in here is invisible until a real candidate reconnects and the
interview restarts from the wrong place.

No LiveKit, no backend: a recording fake stands in for persistence, and
the `/load` payload is a dict of exactly the shape the backend returns.
"""
import pytest

from agent.interview.models import InterviewPhase
from agent.interview.persistence import InterviewPersistence
from agent.runtime.bootstrap import build_context

SESSION_ID = "11111111-2222-3333-4444-555555555555"


class RecordingPersistence(InterviewPersistence):
    def __init__(self):
        self.calls = []

    async def load_session(self, session_id):
        self.calls.append(("load", session_id)); return {}

    async def save_checkpoint(self, context):
        self.calls.append(("checkpoint",))

    async def save_completion(self, context):
        self.calls.append(("completion",)); return True

    async def save_message(self, session_id, sequence, speaker, text, phase=None, metadata=None):
        self.calls.append(("message", sequence, speaker))

    async def save_event(self, session_id, sequence, event_type, phase=None, metadata=None):
        self.calls.append(("event", sequence, event_type))

    async def update_status(self, session_id, status, final_result=None):
        self.calls.append(("status", status)); return True

    async def submit_evaluation(self, context):
        self.calls.append(("evaluation",)); return True

    async def close(self):
        pass


def load_payload(**overrides) -> dict:
    """What GET /internal/interviews/{id}/load returns, trimmed to the keys
    build_context reads."""
    payload = {
        "candidate_profile_id": "cccccccc-0000-0000-0000-000000000000",
        "role": "Backend Engineer",
        "level": "mid",
        "language": "en",
        "duration_minutes": 20,
        "job_description": "Build services.",
        "candidate_profile": {"full_name": "Sam"},
        "sections": [
            {
                "section_type": "VERBAL",
                "time_budget_minutes": 10,
                "questions": [
                    {"id": "q-hr-1", "order_index": 0, "title": "Q1", "text": "Tell me about a service you built."},
                    {"id": "q-hr-2", "order_index": 1, "title": "Q2", "text": "How do you test it?"},
                ],
            }
        ],
        "criteria": [],
        "recent_messages": [],
        "latest_checkpoint": None,
    }
    payload.update(overrides)
    return payload


def question_snapshot(**overrides) -> dict:
    """A complete Question dict, as save_checkpoint writes it. Every field
    matters: Question has five required list/scalar fields, and
    `build_context` calls `Question(**snapshot)` directly."""
    snapshot = {
        "id": "q-snap", "title": "Snapshot", "problem_statement": "Explain it.",
        "difficulty": "mid", "expected_concepts": [], "hints": [], "follow_up_topics": [],
        "time_budget_minutes": 0, "coding_required": False,
    }
    snapshot.update(overrides)
    return snapshot


def greeting(seq: int = 1) -> dict:
    return {"sequence_number": seq, "speaker": "agent", "text": "Hello!", "metadata": {"is_greeting": True}}


# ── fresh start ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_session_with_no_greeting_yet_starts_fresh():
    p = RecordingPersistence()
    context, is_resuming = await build_context(load_payload(), p, SESSION_ID)

    assert is_resuming is False
    assert context.session_id == SESSION_ID and context.role == "Backend Engineer"
    assert context.time_remaining_seconds == 20 * 60
    assert [q.id for q in context.sections["VERBAL"].questions] == ["q-hr-1", "q-hr-2"]
    assert context.sections["VERBAL"].current_index == 0
    assert ("status", "IN_PROGRESS") in p.calls
    assert any(c[0] == "event" and c[2] == "SESSION_STARTED" for c in p.calls)


# ── resume ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_persisted_greeting_is_what_makes_it_a_resume():
    """Not the status: a session can be IN_PROGRESS with nothing said yet."""
    p = RecordingPersistence()
    _, is_resuming = await build_context(
        load_payload(recent_messages=[greeting()], latest_checkpoint={"current_phase": "TECHNICAL"}), p, SESSION_ID
    )
    assert is_resuming is True
    assert any(c[0] == "event" and c[2] == "SESSION_RECONNECTED" for c in p.calls)
    assert ("status", "IN_PROGRESS") in p.calls


@pytest.mark.asyncio
async def test_resume_restores_the_phase_counters_and_clock():
    p = RecordingPersistence()
    checkpoint = {
        "current_phase": "TECHNICAL",
        "question_index": 2,
        "hints_used": 1,
        "followups_used": 3,
        "time_remaining_seconds": 412,
        "last_message_sequence": 9,
        "last_event_sequence": 4,
    }
    context, _ = await build_context(
        load_payload(recent_messages=[greeting()], latest_checkpoint=checkpoint), p, SESSION_ID
    )

    assert context.current_phase is InterviewPhase.TECHNICAL
    assert (context.question_index, context.hints_used, context.followups_used) == (2, 1, 3)
    assert context.time_remaining_seconds == 412          # not reset to duration_minutes * 60
    assert context.message_sequence == 9
    assert context.event_sequence == 5                     # 4 + the reconnect event just written


@pytest.mark.asyncio
async def test_the_message_sequence_never_goes_backwards_when_the_checkpoint_lags():
    """Checkpoints are written less often than messages. Taking the
    checkpoint's number alone would re-use sequence numbers the backend has
    already stored, and every later save would collide."""
    p = RecordingPersistence()
    messages = [greeting(1), {"sequence_number": 14, "speaker": "candidate", "text": "I built...", "metadata": {}}]
    context, _ = await build_context(
        load_payload(recent_messages=messages, latest_checkpoint={"current_phase": "TECHNICAL", "last_message_sequence": 6}),
        p, SESSION_ID,
    )
    assert context.message_sequence == 14


@pytest.mark.asyncio
async def test_resume_restores_the_ordered_pointer_and_conversation_history():
    p = RecordingPersistence()
    messages = [
        greeting(1),
        {"sequence_number": 2, "speaker": "candidate", "text": "Hi there", "metadata": {}},
        {"sequence_number": 3, "speaker": "agent", "text": "First question...", "metadata": {}},
    ]
    checkpoint = {
        "current_phase": "TECHNICAL",
        "section_progress": {"verbal": {"current_index": 1, "completed": False}},
    }
    context, _ = await build_context(
        load_payload(recent_messages=messages, latest_checkpoint=checkpoint), p, SESSION_ID
    )

    assert context.sections["VERBAL"].current_index == 1      # resumes on Q2, not Q1
    assert context.sections["VERBAL"].completed is False
    # The question list itself is always the fresh one from /load.
    assert [q.id for q in context.sections["VERBAL"].questions] == ["q-hr-1", "q-hr-2"]
    assert [(m.role, m.content) for m in context.conversation_history] == [
        ("assistant", "Hello!"), ("user", "Hi there"), ("assistant", "First question..."),
    ]


@pytest.mark.asyncio
async def test_background_questions_come_back_from_the_checkpoint_before_the_pointer_is_applied():
    """The pointer counts the background questions, which sit at the front
    of the list -- restoring them after the pointer would resume on the
    wrong question."""
    p = RecordingPersistence()
    checkpoint = {
        "current_phase": "TECHNICAL",
        "section_progress": {
            "verbal": {
                "current_index": 1,
                "background_questions": [
                    question_snapshot(id="q-bg-1", title="Background",
                                      problem_statement="Tell me about your CV.", source="BACKGROUND")
                ],
                "background_deadline_epoch": 1_700_000_000.0,
            }
        },
    }
    context, _ = await build_context(
        load_payload(recent_messages=[greeting()], latest_checkpoint=checkpoint), p, SESSION_ID
    )

    verbal = context.sections["VERBAL"]
    assert [q.id for q in verbal.questions] == ["q-bg-1", "q-hr-1", "q-hr-2"]
    assert verbal.current_index == 1                    # i.e. q-hr-1, exactly where it left off
    assert context.background_deadline_epoch == 1_700_000_000.0


@pytest.mark.asyncio
async def test_resume_restores_question_records_and_evaluation_signals():
    p = RecordingPersistence()
    checkpoint = {
        "current_phase": "TECHNICAL",
        "current_question_snapshot": question_snapshot(id="q-hr-2", title="Q2",
                                                       problem_statement="How do you test it?"),
        "question_records": [{"question_id": "q-hr-1", "outcome": "COMPLETED", "hints_used": 1}],
        "evaluation_signals": [{"communication": 4, "technical_reasoning": 3}],
        "section_progress": {
            "background": {"questions_asked": 2, "completed": True},
            "technical": {"questions_completed": 1, "questions_skipped": 0},
        },
    }
    context, _ = await build_context(
        load_payload(recent_messages=[greeting()], latest_checkpoint=checkpoint), p, SESSION_ID
    )

    assert context.current_question is not None and context.current_question.id == "q-hr-2"
    assert [(r.question_id, r.hints_used) for r in context.question_records] == [("q-hr-1", 1)]
    assert len(context.evaluation_signals) == 1 and context.evaluation_signals[0].communication == 4
    assert context.background_progress.questions_asked == 2 and context.background_progress.completed is True
    assert context.technical_progress.questions_completed == 1


@pytest.mark.asyncio
async def test_an_unreadable_background_snapshot_does_not_stop_the_resume():
    """A snapshot written by an older version must degrade to "no
    background questions", not crash the reconnect."""
    p = RecordingPersistence()
    checkpoint = {
        "current_phase": "TECHNICAL",
        "section_progress": {"verbal": {"current_index": 0, "background_questions": [{"nonsense": True}]}},
    }
    context, is_resuming = await build_context(
        load_payload(recent_messages=[greeting()], latest_checkpoint=checkpoint), p, SESSION_ID
    )
    assert is_resuming is True
    assert [q.id for q in context.sections["VERBAL"].questions] == ["q-hr-1", "q-hr-2"]


@pytest.mark.asyncio
async def test_a_legacy_session_with_no_sections_still_builds():
    """Pre-Phase-7 sessions come from InterviewConfiguration and carry no
    `sections` key at all; they must not crash the worker (they keep
    working until Phase 10)."""
    p = RecordingPersistence()
    payload = load_payload()
    del payload["sections"]
    context, is_resuming = await build_context(payload, p, SESSION_ID)
    assert is_resuming is False and context.sections == {}
