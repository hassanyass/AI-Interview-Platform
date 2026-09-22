"""NotificationService that renders the invitation and hands it to the
EmailProvider port. Selected with NOTIFICATIONS_PROVIDER=email; with the
only EmailProvider today (null) nothing is delivered, but the whole path
is exercised and the outcome is logged."""
from __future__ import annotations

import logging

from backend.providers.email.base import EmailMessage, EmailProvider
from backend.providers.notifications.base import NotificationService

logger = logging.getLogger(__name__)


class EmailNotificationService(NotificationService):
    def __init__(self, email: EmailProvider) -> None:
        self._email = email

    @staticmethod
    def render_invitation(to: str, link: str, context: dict) -> EmailMessage:
        job_title = context.get("job_title", "a role")
        subject = context.get("subject") or f"You're invited to interview for {job_title}"
        body = context.get("body") or (
            f"You have been invited to an interview for {job_title}.\n\n"
            f"Open this link to begin: {link}\n"
        )
        return EmailMessage(to=to, subject=subject, text=body)

    async def send_invitation_email(self, to: str, link: str, context: dict) -> None:
        result = await self._email.send(self.render_invitation(to, link, context))
        if not result.sent:
            logger.warning(
                "Invitation email to %s not delivered via %s: %s", to, result.provider, result.reason
            )
