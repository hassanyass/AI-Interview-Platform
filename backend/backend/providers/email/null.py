"""Inert email adapter: logs what would have been sent and reports it was not."""
from __future__ import annotations

import logging

from backend.providers.email.base import EmailMessage, EmailProvider, EmailSendResult

logger = logging.getLogger(__name__)


class NullEmailProvider(EmailProvider):
    name = "null"

    async def send(self, message: EmailMessage) -> EmailSendResult:
        logger.info(
            "[email not sent - no provider configured] To: %s | Subject: %s",
            message.to, message.subject,
        )
        return EmailSendResult(sent=False, provider=self.name, reason="no email provider configured")
