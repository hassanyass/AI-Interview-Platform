"""Default NotificationService implementation — logs instead of sending.

This is what Phase 6 runs on until P1 (email provider) is resolved.
"""
import logging

from backend.services.notifications.base import NotificationService

logger = logging.getLogger(__name__)


class ConsoleNotificationService(NotificationService):
    async def send_invitation_email(self, to: str, link: str, context: dict) -> None:
        job_title = context.get("job_title", "a role")
        logger.info(
            "[Invitation email — console stub] To: %s | Job: %s | Link: %s",
            to,
            job_title,
            link,
        )
