"""Realtime (voice room + recording) port. LiveKit Cloud is the only adapter."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import timedelta

from backend.providers.storage.base import S3Destination


@dataclass(frozen=True)
class RecordingStart:
    egress_id: str
    failed: bool          # the provider reported an immediate failure/abort
    status: str           # provider's own status name, for logs
    error: str = ""


class RealtimeProvider(ABC):
    @abstractmethod
    def mint_participant_token(self, *, room: str, identity: str, name: str, ttl: timedelta) -> str:
        """Signed join token for one participant in one room."""

    @abstractmethod
    async def start_room_recording(self, *, room: str, output_path: str, destination: S3Destination) -> RecordingStart:
        """Start a composite recording of the room, written straight to
        ``destination``. Retries while the room does not exist yet (the
        caller schedules this right after handing out the first token).
        Raises on any other error."""

    @abstractmethod
    async def stop_recording(self, egress_id: str) -> None:
        """Raises on failure; callers decide whether that is fatal."""

    @abstractmethod
    async def delete_room(self, room: str) -> None:
        """Force-end a room, disconnecting everyone. Raises if the room is
        unknown/already gone; callers treat that as expected."""
