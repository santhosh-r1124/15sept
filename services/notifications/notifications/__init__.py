"""Notification service (Phase 11) - stub. The real implementation is in
``apps/api/app/services/notifications/`` (same Docker build-context reasoning as the other
stubs, see docs/adr/0004):

    event  ->  notify()  ->  { in-app row, email outbox }

In-app + email only. SMS / OTP is deliberately not built: every Indian SMS route is a paid,
DLT-registered provider, which is an owner decision (docs/adr/0013).
"""

__all__: list[str] = []
