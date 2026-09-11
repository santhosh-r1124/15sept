"""Email sending abstraction.

The Phase 1 default logs the email (including the actionable link) via
structlog instead of sending anything — no SMTP/provider account is needed to
develop or test the auth flows locally. ``services/notifications`` (Phase 11)
is where a real provider (SES/Postmark/etc.) gets wired in behind this same
``EmailSender`` protocol.
"""

from __future__ import annotations

from typing import Protocol

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger("app.email")


class EmailSender(Protocol):
    async def send(self, *, to: str, subject: str, body: str) -> None: ...


class ConsoleEmailSender:
    """Dev/test default: logs instead of sending."""

    async def send(self, *, to: str, subject: str, body: str) -> None:
        logger.info("email_dev_send", to=to, subject=subject, body=body)


_sender: EmailSender | None = None


def get_email_sender() -> EmailSender:
    global _sender
    if _sender is None:
        _sender = ConsoleEmailSender()
    return _sender


def set_email_sender(sender: EmailSender) -> None:
    """Override the process-wide sender — used by tests and, later, Phase 11 wiring."""
    global _sender
    _sender = sender


async def send_verification_email(*, to: str, token: str, settings: Settings) -> None:
    link = f"{settings.frontend_base_url}/verify-email?token={token}"
    await get_email_sender().send(
        to=to,
        subject="Verify your email — Legal Advisor",
        body=f"Confirm your email address: {link}\n\nThis link expires in 24 hours.",
    )


async def send_password_reset_email(*, to: str, token: str, settings: Settings) -> None:
    link = f"{settings.frontend_base_url}/reset-password?token={token}"
    await get_email_sender().send(
        to=to,
        subject="Reset your password — Legal Advisor",
        body=f"Reset your password: {link}\n\nThis link expires in 1 hour. "
        "If you didn't request this, you can ignore this email.",
    )
