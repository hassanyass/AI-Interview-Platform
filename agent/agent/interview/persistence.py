"""
Interview persistence abstraction.
- MockPersistence: in-memory (for testing/simulator)
- APIPersistence: communicates with backend via HTTP
"""
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import json

from agent.interview.models import InterviewRuntimeContext

logger = logging.getLogger(__name__)


def build_final_result(context: InterviewRuntimeContext) -> dict:
    """Build the single persisted result envelope used by mock and API stores."""
    completed_questions = sum(1 for r in context.question_records if r.outcome.value == "COMPLETED")
    skipped_questions = sum(1 for r in context.question_records if r.outcome.value == "SKIPPED")
    changed_questions = sum(1 for r in context.question_records if r.outcome.value == "CHANGED")
    return {
        "session_id": context.session_id,
        "role": context.role,
        "level": context.confirmed_level,
        "total_questions": len(context.question_records),
        "completed": completed_questions,
        "skipped": skipped_questions,
        "changed": changed_questions,
        "question_records": [r.model_dump(mode="json") for r in context.question_records],
        "competencies_evaluated": context.competencies_evaluated,
        "technical_submission": context.technical_submission,
        "technical_question_ids_seen": context.technical_question_ids_seen,
        "transcript": [
            {"speaker": "candidate" if m.role == "user" else "agent", "text": m.content}
            for m in context.conversation_history
            if m.role in ("user", "assistant")
        ],
        "evaluation_status": "COMPLETED" if context.final_evaluation else "FAILED",
        "evaluation": context.final_evaluation.model_dump(mode="json") if context.final_evaluation else None,
    }


class InterviewPersistence(ABC):
    """Abstract interface for loading and saving interview state."""

    @abstractmethod
    async def load_session(self, session_id: str) -> Optional[dict]:
        """Load session data for agent bootstrap / recovery."""
        pass

    @abstractmethod
    async def save_checkpoint(self, context: InterviewRuntimeContext) -> None:
        """Save a versioned recovery checkpoint."""
        pass

    @abstractmethod
    async def save_completion(self, context: InterviewRuntimeContext) -> bool:
        """Persist final interview completion state. Returns True iff persistence actually succeeded."""
        pass

    @abstractmethod
    async def save_message(
        self, session_id: str, sequence: int, speaker: str, text: str,
        phase: Optional[str] = None, metadata: Optional[dict] = None,
    ) -> None:
        """Persist a finalized transcript message."""
        pass

    @abstractmethod
    async def save_event(
        self, session_id: str, sequence: int, event_type: str,
        phase: Optional[str] = None, metadata: Optional[dict] = None,
    ) -> None:
        """Persist a meaningful interview event."""
        pass

    @abstractmethod
    async def update_status(self, session_id: str, status: str, final_result: Optional[dict] = None) -> bool:
        """Update the interview session status. Returns True iff the update actually succeeded."""
        pass

    @abstractmethod
    async def submit_evaluation(self, context: InterviewRuntimeContext) -> bool:
        """Persist context.final_evaluation into the normalized Evaluation/Score
        tables (Phase 8C), in addition to (not instead of) the legacy
        final_result JSONB envelope save_completion() already writes. Safe to
        call more than once for the same session -- the backend upserts on
        session_id. Returns True iff persistence actually succeeded; a no-op
        (context.final_evaluation is None -- nothing to submit) also returns
        True, since that isn't a persistence failure."""
        pass

    async def renew_lease(self, session_id: str) -> str:
        """Renew this agent's claim on the session; returns a LeaseState value
        (H2-D). Non-abstract: in-memory persistence has no lease to renew."""
        return "renewed"

    async def close(self) -> None:
        return None


class MockPersistence(InterviewPersistence):
    """In-memory persistence for the text simulator and unit tests."""

    def __init__(self):
        self.storage: Dict[str, Any] = {}
        self.messages: list = []
        self.events: list = []

    async def load_session(self, session_id: str) -> Optional[dict]:
        return self.storage.get(session_id)

    async def save_checkpoint(self, context: InterviewRuntimeContext) -> None:
        self.storage[context.session_id] = {
            "schema_version": 1,
            "current_phase": context.current_phase.value,
            "question_index": context.question_index,
            "hints_used": context.hints_used,
            "followups_used": context.followups_used,
            "time_remaining_seconds": context.time_remaining_seconds,
            "message_sequence": context.message_sequence,
            "event_sequence": context.event_sequence,
            "current_question_snapshot": context.current_question.model_dump() if context.current_question else None,
            "section_progress": {
                "background": context.background_progress.model_dump(),
                "technical": {
                    **context.technical_progress.model_dump(),
                    "technical_question_ids_seen": context.technical_question_ids_seen,
                    "technical_question_ids_skipped": context.technical_question_ids_skipped,
                    "technical_question_id_submitted": context.technical_question_id_submitted,
                    "technical_submission": context.technical_submission,
                },
                # Phase 7D: only the mutable pointer — the ordered question
                # list itself is always rebuilt fresh from /load on connect.
                "verbal": (
                    {
                        "current_index": context.sections["VERBAL"].current_index,
                        "completed": context.sections["VERBAL"].completed,
                        "background_questions": [
                            q.model_dump(mode="json")
                            for q in context.sections["VERBAL"].background_questions
                        ],
                        "background_deadline_epoch": context.background_deadline_epoch,
                    }
                    if "VERBAL" in context.sections else None
                ),
            },
            "question_records": [r.model_dump(mode="json") for r in context.question_records],
            "evaluation_signals": [e.model_dump(mode="json") for e in context.evaluation_signals],
            "technical_question_ids_seen": context.technical_question_ids_seen,
            "technical_question_ids_skipped": context.technical_question_ids_skipped,
            "technical_question_id_submitted": context.technical_question_id_submitted,
            "technical_submission": context.technical_submission,
            "competencies_evaluated": context.competencies_evaluated,
        }
        logger.info(f"[MockPersistence] Saved checkpoint for {context.session_id} - Phase: {context.current_phase.value}")

    async def save_completion(self, context: InterviewRuntimeContext) -> bool:
        status = "COMPLETED" if context.current_phase.value == "COMPLETED" else "TERMINATED"
        self.storage[context.session_id] = {
            "status": status,
            "current_phase": context.current_phase.value,
        }
        if status == "COMPLETED":
            final_result = build_final_result(context)
            self.storage[context.session_id]["final_result"] = final_result

        logger.info(f"[MockPersistence] Saved final state for {context.session_id}")
        return True

    async def save_message(
        self, session_id: str, sequence: int, speaker: str, text: str,
        phase: Optional[str] = None, metadata: Optional[dict] = None,
    ) -> None:
        self.messages.append({
            "session_id": session_id,
            "sequence": sequence,
            "speaker": speaker,
            "text": text,
            "phase": phase,
        })

    async def save_event(
        self, session_id: str, sequence: int, event_type: str,
        phase: Optional[str] = None, metadata: Optional[dict] = None,
    ) -> None:
        self.events.append({
            "session_id": session_id,
            "sequence": sequence,
            "event_type": event_type,
            "phase": phase,
        })

    async def update_status(self, session_id: str, status: str, final_result: Optional[dict] = None) -> bool:
        if session_id not in self.storage:
            self.storage[session_id] = {}
        self.storage[session_id]["status"] = status
        if final_result is not None:
            self.storage[session_id]["final_result"] = final_result
        return True

    async def submit_evaluation(self, context: InterviewRuntimeContext) -> bool:
        if context.final_evaluation is None:
            return True
        if context.session_id not in self.storage:
            self.storage[context.session_id] = {}
        self.storage[context.session_id]["evaluation_submission"] = context.final_evaluation.model_dump(mode="json")
        return True


class LeaseState:
    """Outcome of renew_lease (H2-D): the worker reacts differently to
    'someone else owns this session' than to 'the backend was unreachable'."""
    RENEWED = "renewed"
    LOST = "lost"        # 409: another agent holds the lease -> stop driving the session
    ERROR = "error"      # transport / 5xx after retries


class APIPersistence(InterviewPersistence):
    """
    Production persistence that communicates with the FastAPI backend
    via HTTP. The agent remains independent of backend SQLAlchemy models.

    H2-D: one `_request` transport with a per-request timeout and bounded
    retries on transport errors / 5xx (never on 4xx), plus an in-memory
    outbox for messages, events and checkpoints that still fail: they are
    replayed before the next request and on every lease tick. Replays are
    idempotent -- the backend keys messages/events on (session_id,
    sequence_number) and checkpoints are append-only snapshots.
    """

    RETRYABLE_STATUSES = frozenset({500, 502, 503, 504})

    def __init__(
        self,
        backend_url: str,
        agent_secret: str,
        agent_id: str,
        *,
        timeout_seconds: float = 10.0,
        retry_attempts: int = 3,
    ):
        self.backend_url = backend_url.rstrip("/")
        self.agent_secret = agent_secret
        self.agent_id = agent_id
        self.timeout_seconds = timeout_seconds
        self.retry_attempts = max(0, retry_attempts)
        self._session = None  # aiohttp session
        # (method, path, kwargs) of writes that failed after retries; FIFO.
        self._outbox: list[tuple[str, str, dict]] = []

    async def _get_session(self):
        if self._session is None or self._session.closed:
            import aiohttp
            self._session = aiohttp.ClientSession(
                headers={"X-Agent-Secret": self.agent_secret},
                timeout=aiohttp.ClientTimeout(total=self.timeout_seconds),
            )
        return self._session

    async def close(self):
        if self._outbox:
            await self.flush_outbox()
        if self._session and not self._session.closed:
            await self._session.close()

    def _url(self, session_id: str, path: str) -> str:
        return f"{self.backend_url}/api/v1/internal/interviews/{session_id}/{path}"

    # ── transport ──────────────────────────────────────────────────────────

    async def _request(self, method: str, url: str, **kwargs) -> tuple[Optional[int], Any]:
        """Returns (status, parsed body). status is None when every attempt
        failed at the transport level. Retries transport errors and 5xx with
        0.5s/1s/2s backoff; a 4xx is returned immediately."""
        import asyncio
        import aiohttp
        http = await self._get_session()
        last_error: Optional[BaseException] = None
        for attempt in range(self.retry_attempts + 1):
            try:
                async with http.request(method, url, **kwargs) as resp:
                    if resp.status in self.RETRYABLE_STATUSES and attempt < self.retry_attempts:
                        logger.warning("%s %s -> %s; retry %d/%d", method, url, resp.status, attempt + 1, self.retry_attempts)
                        await asyncio.sleep(0.5 * (2 ** attempt))
                        continue
                    ctype = resp.headers.get("Content-Type", "")
                    body = await resp.json() if "json" in ctype else await resp.text()
                    return resp.status, body
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e
                if attempt < self.retry_attempts:
                    logger.warning("%s %s transport error (%s); retry %d/%d", method, url, e, attempt + 1, self.retry_attempts)
                    await asyncio.sleep(0.5 * (2 ** attempt))
                    continue
        logger.error("%s %s failed after %d attempts: %s", method, url, self.retry_attempts + 1, last_error)
        return None, None

    async def _write(self, session_id: str, path: str, body: dict, *, queue_on_failure: bool) -> bool:
        """POST a JSON body; on failure (after retries) optionally park it in
        the outbox for later replay. Flushes the outbox first so ordering is
        preserved for callers that care (messages/events carry sequences)."""
        if self._outbox:
            await self.flush_outbox()
        status, resp_body = await self._request(
            "POST", self._url(session_id, path),
            data=json.dumps(body, default=str), headers={"Content-Type": "application/json"},
        )
        if status in (200, 201):
            return True
        logger.error("Failed to save %s for %s: %s %s", path, session_id, status, str(resp_body)[:300])
        if queue_on_failure and (status is None or status in self.RETRYABLE_STATUSES):
            self._outbox.append(("POST", self._url(session_id, path), {
                "data": json.dumps(body, default=str), "headers": {"Content-Type": "application/json"},
            }))
            logger.warning("Parked %s for %s in the outbox (%d pending)", path, session_id, len(self._outbox))
        return False

    async def flush_outbox(self) -> int:
        """Replay parked writes in order; stops at the first one that still
        fails (it and everything after it stay parked). Returns how many
        were delivered."""
        delivered = 0
        while self._outbox:
            method, url, kwargs = self._outbox[0]
            status, _ = await self._request(method, url, **kwargs)
            if status in (200, 201):
                self._outbox.pop(0)
                delivered += 1
            else:
                break
        if delivered:
            logger.info("Outbox: delivered %d parked write(s), %d still pending", delivered, len(self._outbox))
        return delivered

    @property
    def outbox_size(self) -> int:
        return len(self._outbox)

    # ── reads ──────────────────────────────────────────────────────────────

    async def load_session(self, session_id: str) -> Optional[dict]:
        status, body = await self._request("GET", self._url(session_id, "load"), params={"agent_id": self.agent_id})
        if status == 200:
            return body
        if status == 409:
            logger.warning(f"Session conflict: {(body or {}).get('detail') if isinstance(body, dict) else body}")
            return None
        if status == 404:
            logger.warning(f"Session {session_id} not found in backend.")
            return None
        logger.error(f"Failed to load session: {status}")
        return None

    # ── writes ─────────────────────────────────────────────────────────────

    async def save_checkpoint(self, context: InterviewRuntimeContext) -> None:
        body = {
            "schema_version": 1,
            "current_phase": context.current_phase.value,
            "current_question_id": context.current_question.id if context.current_question else None,
            "question_index": context.question_index,
            "section": context.current_phase.value,
            "hints_used": context.hints_used,
            "followups_used": context.followups_used,
            "background_questions_asked": context.background_progress.questions_asked,
            "competencies_evaluated": context.competencies_evaluated,
            "time_remaining_seconds": context.time_remaining_seconds,
            "last_message_sequence": context.message_sequence,
            "last_event_sequence": context.event_sequence,
            "current_question_snapshot": (
                context.current_question.model_dump() if context.current_question else None
            ),
            "section_progress": {
                "background": context.background_progress.model_dump(),
                "technical": {
                    **context.technical_progress.model_dump(),
                    "technical_question_ids_seen": context.technical_question_ids_seen,
                    "technical_question_ids_skipped": context.technical_question_ids_skipped,
                    "technical_question_id_submitted": context.technical_question_id_submitted,
                    "technical_submission": context.technical_submission,
                },
                # Phase 7D: only the mutable pointer — the ordered question
                # list itself is always rebuilt fresh from /load on connect.
                "verbal": (
                    {
                        "current_index": context.sections["VERBAL"].current_index,
                        "completed": context.sections["VERBAL"].completed,
                        # Background subsection: the ONLY questions that are
                        # not rebuildable from /load -- they were generated
                        # for this session. main.py's resume path restores
                        # them from here (restore_background_questions) so
                        # the pointer above keeps its meaning.
                        "background_questions": [
                            q.model_dump(mode="json")
                            for q in context.sections["VERBAL"].background_questions
                        ],
                        "background_deadline_epoch": context.background_deadline_epoch,
                    }
                    if "VERBAL" in context.sections else None
                ),
            },
            "question_records": [r.model_dump(mode="json") for r in context.question_records],
            "evaluation_signals": [e.model_dump(mode="json") for e in context.evaluation_signals],
        }
        await self._write(context.session_id, "checkpoints", body, queue_on_failure=True)

    async def save_completion(self, context: InterviewRuntimeContext) -> bool:
        await self.save_checkpoint(context)
        status = "COMPLETED" if context.current_phase.value == "COMPLETED" else "TERMINATED"

        final_result = None
        if status == "COMPLETED":
            # Generate the final result schema
            final_result = build_final_result(context)

        return await self.update_status(context.session_id, status, final_result=final_result)

    async def save_message(
        self, session_id: str, sequence: int, speaker: str, text: str,
        phase: Optional[str] = None, metadata: Optional[dict] = None,
    ) -> None:
        body = {
            "sequence_number": sequence,
            "speaker": speaker,
            "text": text,
            "phase": phase,
            "metadata": metadata,
        }
        await self._write(session_id, "messages", body, queue_on_failure=True)

    async def save_event(
        self, session_id: str, sequence: int, event_type: str,
        phase: Optional[str] = None, metadata: Optional[dict] = None,
    ) -> None:
        body = {
            "event_type": event_type,
            "phase": phase,
            "sequence_number": sequence,
            "metadata": metadata,
        }
        await self._write(session_id, "events", body, queue_on_failure=True)

    async def update_status(self, session_id: str, status: str, final_result: Optional[dict] = None) -> bool:
        if self._outbox:
            await self.flush_outbox()
        body = {"status": status}
        if final_result is not None:
            body["final_result"] = final_result
        code, resp_body = await self._request(
            "PATCH", self._url(session_id, "status"),
            data=json.dumps(body, default=str), headers={"Content-Type": "application/json"},
        )
        if code in (200, 201):
            return True
        logger.error(f"Failed to update status: {code} {str(resp_body)[:300]}")
        return False

    async def submit_evaluation(self, context: InterviewRuntimeContext) -> bool:
        if context.final_evaluation is None:
            return True
        body = context.final_evaluation.model_dump(mode="json")
        # Not parked: the caller retries this at teardown and the backend
        # upserts on session_id, so a late replay would only race a newer one.
        return await self._write(context.session_id, "evaluation", body, queue_on_failure=False)

    async def renew_lease(self, session_id: str) -> str:
        """Returns LeaseState.RENEWED / LOST / ERROR (H2-D). Also the moment
        parked writes get another chance."""
        if self._outbox:
            await self.flush_outbox()
        status, body = await self._request("POST", self._url(session_id, "renew-lease"), params={"agent_id": self.agent_id})
        if status == 200:
            return LeaseState.RENEWED
        if status == 409:
            logger.error("Lease for %s is held by another agent: %s", session_id, body)
            return LeaseState.LOST
        logger.warning(f"Lease renewal failed: {status}")
        return LeaseState.ERROR
