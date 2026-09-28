"""Invitation delivery. The concrete service is chosen by
NOTIFICATIONS_PROVIDER in backend.providers.factory (console today; email
routes through the EmailProvider port). Call sites use
``get_notification_service()`` from the factory, never a module singleton.
"""
from backend.providers.notifications.base import NotificationService
from backend.providers.notifications.console import ConsoleNotificationService
from backend.providers.notifications.email import EmailNotificationService

__all__ = ["NotificationService", "ConsoleNotificationService", "EmailNotificationService"]
