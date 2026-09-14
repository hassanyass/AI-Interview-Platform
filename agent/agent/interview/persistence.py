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


class APIPersistence(InterviewPersistence):
    """
    Production persistence that communicates with the FastAPI backend
    via HTTP. The agent remains independent of backend SQLAlchemy models.
    """

    def __init__(self, backend_url: str, agent_secret: str, agent_id: str):
        self.backend_url = backend_url.rstrip("/")
        self.agent_secret = agent_secret
        self.agent_id = agent_id
        self._session = None  # aiohttp session

    async def _get_session(self):
        if self._session is None or self._session.closed:
            import aiohttp
            self._session = aiohttp.ClientSession(
                headers={"X-Agent-Secret": self.agent_secret},
                timeout=aiohttp.ClientTimeout(total=10),
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _url(self, session_id: str, path: str) -> str:
        return f"{self.backend_url}/api/v1/internal/interviews/{session_id}/{path}"

    async def load_session(self, session_id: str) -> Optional[dict]:
        session = await self._get_session()
        try:
            async with session.get(
                self._url(session_id, "load"),
                params={"agent_id": self.agent_id},
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                elif resp.status == 409:
                    body = await resp.json()
                    logger.warning(f"Session conflict: {body.get('detail')}")
                    return None
                elif resp.status == 404:
                    logger.warning(f"Session {session_id} not found in backend.")
                    return None
                else:
                    logger.error(f"Failed to load session: {resp.status}")
                    return None
        except Exception as e:
            logger.error(f"Error loading session from backend: {e}")
            return None

    async def save_checkpoint(self, context: InterviewRuntimeContext) -> None:
        session = await self._get_session()
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
                    }
                    if "VERBAL" in context.sections else None
                ),
            },
            "question_records": [r.model_dump(mode="json") for r in context.question_records],
            "evaluation_signals": [e.model_dump(mode="json") for e in context.evaluation_signals],
        }
        try:
            body_json = json.dumps(body, default=str)
            async with session.post(
                self._url(context.session_id, "checkpoints"), 
                data=body_json,
                headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status not in (200, 201):
                    text = await resp.text()
                    logger.error(f"Failed to save checkpoint: {resp.status} {text}")
        except Exception as e:
            logger.error(f"Error saving checkpoint: {e}")

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
        session = await self._get_session()
        body = {
            "sequence_number": sequence,
            "speaker": speaker,
            "text": text,
            "phase": phase,
            "metadata": metadata,
        }
        try:
            async with session.post(
                self._url(session_id, "messages"), json=body
            ) as resp:
                if resp.status not in (200, 201):
                    logger.error(f"Failed to save message: {resp.status}")
        except Exception as e:
            logger.error(f"Error saving message: {e}")

    async def save_event(
        self, session_id: str, sequence: int, event_type: str,
        phase: Optional[str] = None, metadata: Optional[dict] = None,
    ) -> None:
        session = await self._get_session()
        body = {
            "event_type": event_type,
            "phase": phase,
            "sequence_number": sequence,
            "metadata": metadata,
        }
        try:
            async with session.post(
                self._url(session_id, "events"), json=body
            ) as resp:
                if resp.status not in (200, 201):
                    logger.error(f"Failed to save event: {resp.status}")
        except Exception as e:
            logger.error(f"Error saving event: {e}")

    async def update_status(self, session_id: str, status: str, final_result: Optional[dict] = None) -> bool:
        http = await self._get_session()
        body = {"status": status}
        if final_result is not None:
            body["final_result"] = final_result
        try:
            body_json = json.dumps(body, default=str)
            async with http.patch(
                self._url(session_id, "status"),
                data=body_json,
                headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status not in (200, 201):
                    text_resp = await resp.text()
                    logger.error(f"Failed to update status: {resp.status} {text_resp}")
                    return False
                return True
        except Exception as e:
            logger.error(f"Error updating status: {e}")
            return False

    async def submit_evaluation(self, context: InterviewRuntimeContext) -> bool:
        if context.final_evaluation is None:
            return True
        http = await self._get_session()
        body = context.final_evaluation.model_dump(mode="json")
        try:
            body_json = json.dumps(body, default=str)
            async with http.post(
                self._url(context.session_id, "evaluation"),
                data=body_json,
                headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status not in (200, 201):
                    text_resp = await resp.text()
                    logger.error(f"Failed to submit evaluation: {resp.status} {text_resp}")
                    return False
                return True
        except Exception as e:
            logger.error(f"Error submitting evaluation: {e}")
            return False

    async def renew_lease(self, session_id: str) -> None:
        session = await self._get_session()
        try:
            async with session.post(
                self._url(session_id, "renew-lease"),
                params={"agent_id": self.agent_id},
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"Lease renewal failed: {resp.status}")
        except Exception as e:
            logger.error(f"Error renewing lease: {e}")
