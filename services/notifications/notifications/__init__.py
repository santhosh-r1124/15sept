"""Notification service (Phase 11).

    event  ->  notification service  ->  { email, SMS, in-app }

Events: OTP, booking confirmation, consultation reminders, advocate request
notifications, document notifications, payment notifications. Provider adapters
(email / SMS) sit behind a common interface; templates are versioned.
"""

__all__: list[str] = []
