"""
NotificationService interface — Phase 6.

P1 (which real email provider — Resend/SendGrid/other) is still unresolved
per docs/CURRENT_DECISIONS.md. This interface exists so Phase 6 is fully
functional and testable end-to-end without picking a provider: swap in a
real implementation later by adding a new class here and changing the one
instantiation line in backend/backend/services/notifications/__init__.py,
without touching any call site.
"""
from abc import ABC, abstractmethod


class NotificationService(ABC):
    @abstractmethod
    async def send_invitation_email(self, to: str, link: str, context: dict) -> None:
        """Send (or otherwise deliver) an interview invitation to `to`.

        `link` is the full candidate-facing invite URL. `context` carries
        display info for the email body (e.g. job title, admin name) —
        implementations may use as much or as little of it as they need.
        """
        raise NotImplementedError
