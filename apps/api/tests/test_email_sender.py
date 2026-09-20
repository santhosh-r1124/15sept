"""Unit tests for the SMTP email sender and backend selection (Phase 11). No network."""

from __future__ import annotations

from email.message import EmailMessage
from typing import Any

import pytest

from app.core.config import Settings
from app.services import email as email_module
from app.services.email import (
    ConsoleEmailSender,
    SmtpEmailSender,
    configure_email_sender,
    get_email_sender,
    set_email_sender,
)


class FakeSmtp:
    """Stands in for smtplib.SMTP and records what was done to it."""

    instances: list[FakeSmtp] = []  # noqa: RUF012 - test double

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host, self.port, self.timeout = host, port, timeout
        self.calls: list[str] = []
        self.sent: EmailMessage | None = None
        FakeSmtp.instances.append(self)

    def __enter__(self) -> FakeSmtp:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def starttls(self, context: Any) -> None:
        self.calls.append("starttls")

    def login(self, username: str, password: str) -> None:
        self.calls.append(f"login:{username}")

    def send_message(self, message: EmailMessage) -> None:
        self.calls.append("send")
        self.sent = message


@pytest.fixture(autouse=True)
def _fake_smtp(monkeypatch: pytest.MonkeyPatch) -> Any:
    FakeSmtp.instances = []
    monkeypatch.setattr(email_module.smtplib, "SMTP", FakeSmtp)
    yield
    set_email_sender(None)


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "email_backend": "smtp",
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_username": "mailer",
        "smtp_password": "app-password",
        "email_from": "Legal Advisor <hello@example.com>",
    }
    return Settings(_env_file=None, **{**base, **overrides})  # type: ignore[call-arg]


async def test_smtp_sender_uses_starttls_logs_in_and_sends() -> None:
    sender = SmtpEmailSender(_settings())

    await sender.send(to="asha@example.com", subject="Hello", body="Body text")

    (smtp,) = FakeSmtp.instances
    assert (smtp.host, smtp.port) == ("smtp.example.com", 587)
    assert smtp.timeout == 10  # a slow server can't hang a request for long
    assert smtp.calls == ["starttls", "login:mailer", "send"]
    assert smtp.sent is not None
    assert smtp.sent["To"] == "asha@example.com"
    assert smtp.sent["From"] == "Legal Advisor <hello@example.com>"
    assert smtp.sent["Subject"] == "Hello"
    assert smtp.sent.get_content().strip() == "Body text"


async def test_smtp_sender_skips_tls_and_login_when_not_configured() -> None:
    sender = SmtpEmailSender(_settings(smtp_starttls=False, smtp_username=None, smtp_password=None))

    await sender.send(to="asha@example.com", subject="Hi", body="x")

    assert FakeSmtp.instances[0].calls == ["send"]


@pytest.mark.parametrize(
    ("to", "subject"),
    [
        ("asha@example.com\r\nBcc: victim@example.com", "Hi"),
        ("asha@example.com", "Hi\r\nBcc: victim@example.com"),
    ],
)
async def test_header_injection_is_refused(to: str, subject: str) -> None:
    sender = SmtpEmailSender(_settings())

    with pytest.raises(ValueError):
        await sender.send(to=to, subject=subject, body="x")

    assert FakeSmtp.instances == []  # nothing was even connected to


async def test_smtp_errors_propagate_so_the_outbox_can_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Down(FakeSmtp):
        def send_message(self, message: EmailMessage) -> None:
            raise ConnectionRefusedError("smtp down")

    monkeypatch.setattr(email_module.smtplib, "SMTP", Down)
    sender = SmtpEmailSender(_settings())

    with pytest.raises(ConnectionRefusedError):
        await sender.send(to="asha@example.com", subject="Hi", body="x")


def test_configure_picks_the_backend_from_settings() -> None:
    configure_email_sender(_settings(email_backend="smtp"))
    assert isinstance(get_email_sender(), SmtpEmailSender)

    configure_email_sender(_settings(email_backend="console"))
    assert isinstance(get_email_sender(), ConsoleEmailSender)
