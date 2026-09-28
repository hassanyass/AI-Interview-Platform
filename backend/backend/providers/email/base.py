"""Email transport port. No real vendor is chosen yet (P1 in
docs/CURRENT_DECISIONS.md); this is the integration point a vendor adapter
plugs into (plan decision S6). Until then NullEmailProvider is the only
implementation."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text: str
    html: str | None = None


@dataclass(frozen=True)
class EmailSendResult:
    sent: bool
    provider: str
    message_id: str | None = None
    reason: str | None = None


class EmailProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    async def send(self, message: EmailMessage) -> EmailSendResult:
        """Deliver ``message``. Must not raise for 'not configured'; return
        ``sent=False`` with a reason so callers can record it."""
