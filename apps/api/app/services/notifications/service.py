"""Writing notifications and delivering their emails (Phase 11).

    route ──notify()──▶ Notification row (in the request's transaction)
                              │ commit
                              ▼
          deliver_request_emails() ──▶ EmailSender ──▶ row marked SENT / attempts+1

Why an outbox rather than "send the email in the route":

* the row is committed atomically with the action, so a failed action can never have emailed
  anyone, and a successful one can't lose its notification if the mail server is down;
* a failed send leaves the row PENDING, so ``python -m app.scripts.send_pending_emails`` (cron)
  can retry it later - no queue infrastructure needed.

Delivery in the request path only ever touches *this request's* rows, and pauses itself for a
minute after a failure, so a dead SMTP server costs one timeout, not one per request.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.notification import EmailStatus, Notification
from app.models.user import User, UserRole
from app.services.email import get_email_sender
from app.services.notifications.content import Content, render_email

logger = get_logger("app.notifications")

MAX_EMAIL_ATTEMPTS = 5
_PAUSE_SECONDS = 60.0
_PENDING_KEY = "notification_ids"

_paused_until = 0.0


def reset_delivery_pause() -> None:
    """Clear the post-failure pause (tests; also handy from a shell)."""
    global _paused_until
    _paused_until = 0.0


def _base_url(settings: Settings, recipient: User) -> str:
    return (
        settings.portal_base_url
        if recipient.role is UserRole.ADVOCATE
        else settings.frontend_base_url
    )


async def notify(
    db: AsyncSession,
    settings: Settings,
    recipient: User,
    content: Content,
    *,
    coalesce: bool = False,
) -> Notification | None:
    """Stage a notification for ``recipient`` in the caller's transaction.

    Nothing is sent here; the email (if the event has one, and the user hasn't opted out) is
    recorded as PENDING and goes out after the caller commits.

    ``coalesce`` collapses a burst: if the recipient already has an *unread* notification of the
    same kind for the same link, no second one is added (ten chat messages while they were away
    are one bell entry, not ten). Returns None in that case.
    """
    if coalesce:
        already = await db.scalar(
            select(Notification.id)
            .where(
                Notification.user_id == recipient.id,
                Notification.kind == content.kind.value,
                Notification.link == content.link,
                Notification.read_at.is_(None),
            )
            .limit(1)
        )
        if already is not None:
            return None
    email = render_email(content, base_url=_base_url(settings, recipient))
    wants_email = email is not None and recipient.email_notifications and recipient.is_active
    notification = Notification(
        id=uuid.uuid4(),
        user_id=recipient.id,
        kind=content.kind.value,
        title=content.title,
        body=content.body,
        link=content.link,
        email_status=(EmailStatus.PENDING if wants_email else EmailStatus.SKIPPED).value,
        email_subject=email[0] if wants_email and email else None,
        email_body=email[1] if wants_email and email else None,
    )
    db.add(notification)
    if wants_email:
        # Remember which rows this request created; if it rolls back they simply won't exist.
        db.info.setdefault(_PENDING_KEY, []).append(notification.id)
    return notification


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    sent: int
    failed: bool  # a send raised; the row stays PENDING (or FAILED after the last attempt)


async def deliver_pending_emails(
    db: AsyncSession, *, ids: Sequence[uuid.UUID] | None = None, batch_size: int = 50
) -> DeliveryResult:
    """Send PENDING notification emails (all of them, or just ``ids``).

    A failure is recorded (``email_attempts``; FAILED after ``MAX_EMAIL_ATTEMPTS``) and the batch
    stops - if the mail server is down, the rest would only time out one by one.
    """
    stmt = (
        select(Notification, User.email)
        .join(User, User.id == Notification.user_id)
        .where(
            Notification.email_status == EmailStatus.PENDING.value,
            Notification.email_attempts < MAX_EMAIL_ATTEMPTS,
        )
        .order_by(Notification.created_at)
        .limit(batch_size)
        .with_for_update(skip_locked=True, of=Notification)
    )
    if ids is not None:
        stmt = stmt.where(Notification.id.in_(ids))

    sender = get_email_sender()
    sent = 0
    failed = False
    for notification, to in (await db.execute(stmt)).all():
        try:
            await sender.send(
                to=to,
                subject=notification.email_subject or "Legal Advisor",
                body=notification.email_body or "",
            )
        except Exception as exc:
            notification.email_attempts += 1
            if notification.email_attempts >= MAX_EMAIL_ATTEMPTS:
                notification.email_status = EmailStatus.FAILED.value
            logger.warning(
                "notification_email_failed",
                notification_id=str(notification.id),
                attempts=notification.email_attempts,
                error_type=type(exc).__name__,
            )
            failed = True
            break
        notification.email_status = EmailStatus.SENT.value
        notification.emailed_at = datetime.now(UTC)
        sent += 1
    await db.commit()
    return DeliveryResult(sent=sent, failed=failed)


async def deliver_request_emails(db: AsyncSession) -> None:
    """Send the emails staged by this request. Call *after* committing. Never raises."""
    global _paused_until
    ids: list[uuid.UUID] = db.info.pop(_PENDING_KEY, [])
    if not ids or time.monotonic() < _paused_until:
        return  # nothing to do, or the mail server failed recently: the outbox retries later
    try:
        result = await deliver_pending_emails(db, ids=ids)
    except Exception:
        logger.exception("notification_delivery_error")
        await db.rollback()
        result = DeliveryResult(sent=0, failed=True)
    if result.failed:
        _paused_until = time.monotonic() + _PAUSE_SECONDS
