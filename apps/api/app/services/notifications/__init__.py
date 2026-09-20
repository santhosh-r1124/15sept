"""Notifications: in-app + email outbox (Phase 11). See ``service.py`` and ``content.py``."""

from app.services.notifications.service import (
    MAX_EMAIL_ATTEMPTS,
    DeliveryResult,
    deliver_pending_emails,
    deliver_request_emails,
    notify,
    reset_delivery_pause,
)

__all__ = [
    "MAX_EMAIL_ATTEMPTS",
    "DeliveryResult",
    "deliver_pending_emails",
    "deliver_request_emails",
    "notify",
    "reset_delivery_pause",
]
