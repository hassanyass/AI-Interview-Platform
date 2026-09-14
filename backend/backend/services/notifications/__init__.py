from backend.services.notifications.console import ConsoleNotificationService

# Single instance call sites import and use. Swapping providers later (P1 in
# docs/CURRENT_DECISIONS.md — still unresolved) means adding a new
# NotificationService implementation and changing this one line, not
# touching any call site.
notification_service = ConsoleNotificationService()

__all__ = ["notification_service"]
