"""
Interview persistence abstraction.
- MockPersistence: in-memory (for testing/simulator)
- APIPersistence: communicates with backend via HTTP
"""
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

from app.interview.models import InterviewRuntimeContext

logger = logging.getLogger(__name__)


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
    async def save_completion(self, context: InterviewRuntimeContext) -> None:
        """Persist final interview completion state."""
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
    async def update_status(self, session_id: str, status: str) -> None:
        """Update the interview session status."""
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
        }

    async def save_completion(self, context: InterviewRuntimeContext) -> None:
        self.storage[context.session_id] = {
            "status": "COMPLETED",
            "current_phase": context.current_phase.value,
        }
        logger.info(f"[MockPersistence] Saved final state for {context.session_id}")

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

    async def update_status(self, session_id: str, status: str) -> None:
        if session_id not in self.storage:
            self.storage[session_id] = {}
        self.storage[session_id]["status"] = status


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
                "technical": context.technical_progress.model_dump(),
            },
        }
        try:
            async with session.post(
                self._url(context.session_id, "checkpoints"), json=body
            ) as resp:
                if resp.status not in (200, 201):
                    text = await resp.text()
                    logger.error(f"Failed to save checkpoint: {resp.status} {text}")
        except Exception as e:
            logger.error(f"Error saving checkpoint: {e}")

    async def save_completion(self, context: InterviewRuntimeContext) -> None:
        await self.save_checkpoint(context)
        status = "COMPLETED" if context.current_phase == InterviewRuntimeContext.__fields__["current_phase"].default else "TERMINATED"
        # Determine correct status
        if context.current_phase.value == "COMPLETED":
            status = "COMPLETED"
        else:
            status = "TERMINATED"
        await self.update_status(context.session_id, status)

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
                    text_resp = await resp.text()
                    logger.error(f"Failed to save message: {resp.status} {text_resp}")
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
                    text_resp = await resp.text()
                    logger.error(f"Failed to save event: {resp.status} {text_resp}")
        except Exception as e:
            logger.error(f"Error saving event: {e}")

    async def update_status(self, session_id: str, status: str) -> None:
        http = await self._get_session()
        body = {"status": status}
        try:
            async with http.patch(
                self._url(session_id, "status"), json=body
            ) as resp:
                if resp.status not in (200, 201):
                    text_resp = await resp.text()
                    logger.error(f"Failed to update status: {resp.status} {text_resp}")
        except Exception as e:
            logger.error(f"Error updating status: {e}")

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
