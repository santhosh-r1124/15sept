"""Email sending abstraction.

The default (``EMAIL_BACKEND=console``) logs the email - including any actionable link - instead
of sending it, so no SMTP account is needed to develop or test locally. ``EMAIL_BACKEND=smtp``
sends through any SMTP server (``SmtpEmailSender``); a free Gmail/Outlook app-password account is
enough for low volume, and nothing here requires a paid provider. Both sit behind the
``EmailSender`` protocol, so a provider's HTTP API can be dropped in the same way later.
"""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage
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


class SmtpEmailSender:
    """Sends plain-text mail over SMTP (STARTTLS by default).

    ``smtplib`` is blocking, so the exchange runs in a worker thread with a hard timeout - a
    slow mail server can delay one email, never the event loop. Errors propagate: the caller
    (the notification outbox) decides whether to retry.
    """

    def __init__(self, settings: Settings) -> None:
        self._host = settings.smtp_host
        self._port = settings.smtp_port
        self._username = settings.smtp_username
        self._password = settings.smtp_password
        self._starttls = settings.smtp_starttls
        self._timeout = settings.smtp_timeout_seconds
        self._from = settings.email_from

    def _build(self, to: str, subject: str, body: str) -> EmailMessage:
        message = EmailMessage()
        # EmailMessage rejects CR/LF in header values, so a crafted subject or address can't
        # smuggle extra headers (header injection) - it raises instead.
        message["From"] = self._from
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        return message

    def _send_blocking(self, message: EmailMessage) -> None:
        with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as smtp:
            if self._starttls:
                smtp.starttls(context=ssl.create_default_context())
            if self._username and self._password:
                smtp.login(self._username, self._password)
            smtp.send_message(message)

    async def send(self, *, to: str, subject: str, body: str) -> None:
        message = self._build(to, subject, body)
        await asyncio.to_thread(self._send_blocking, message)


_sender: EmailSender | None = None


def get_email_sender() -> EmailSender:
    global _sender
    if _sender is None:
        _sender = ConsoleEmailSender()
    return _sender


def set_email_sender(sender: EmailSender | None) -> None:
    """Override the process-wide sender (tests, startup wiring). ``None`` resets to the default."""
    global _sender
    _sender = sender


def configure_email_sender(settings: Settings) -> None:
    """Pick the sender from settings. Called once at startup."""
    if settings.email_backend == "smtp":
        set_email_sender(SmtpEmailSender(settings))
        logger.info("email_backend_smtp", host=settings.smtp_host, port=settings.smtp_port)
        return
    set_email_sender(None)
    if settings.app_env.is_production:
        # Not fatal (the app is otherwise usable) but very visible: verification and reset
        # emails would only be written to the log.
        logger.warning("email_console_backend_in_production")


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
