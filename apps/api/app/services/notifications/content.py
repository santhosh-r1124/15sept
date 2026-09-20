"""What each notification says (Phase 11). Pure: no I/O, so it is unit-tested directly.

Two texts per event, on purpose:

* the **in-app** notification may name the matter ("Tenant deposit dispute") - it is only shown to
  the recipient, inside their logged-in session;
* the **email** is generic ("an advocate accepted your request") plus a link. Legal matters are
  sensitive and email is neither private nor authenticated, so titles, fees, dates and messages
  never travel by email - the recipient logs in to see them.

Chat-like events (a new message, an uploaded file) are in-app only: an email per message would
be noise, and the bell already covers it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from app.models.notification import NotificationKind


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def format_inr(amount: Decimal) -> str:
    """₹ with Indian digit grouping: 1234567.5 -> ₹12,34,567.50."""
    whole, _, frac = f"{amount:.2f}".partition(".")
    sign = "-" if whole.startswith("-") else ""
    whole = whole.lstrip("-")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join([*groups, tail])
    return f"{sign}₹{whole}.{frac}"


def format_when(when: datetime) -> str:
    """UTC time for in-app text ("20 Sep 2026, 10:30 UTC"); the reader's zone isn't known."""
    utc = when.astimezone(UTC)
    return f"{utc.day} {utc:%b %Y, %H:%M} UTC"


@dataclass(frozen=True, slots=True)
class Content:
    kind: NotificationKind
    title: str
    body: str
    link: str | None
    # None -> this event is in-app only.
    email_subject: str | None = None
    email_line: str | None = None


def _matter_link(matter_id: uuid.UUID) -> str:
    return f"/matters/{matter_id}"


def matter_requested(*, matter_id: uuid.UUID, title: str, client_name: str | None) -> Content:
    who = client_name or "A client"
    return Content(
        NotificationKind.MATTER_REQUESTED,
        "New request",
        _clip(f"{who} requested “{title}”.", 500),
        _matter_link(matter_id),
        "You have a new request — Legal Advisor",
        "You have a new request from a client.",
    )


def matter_accepted(
    *, matter_id: uuid.UUID, title: str, advocate_name: str | None, fee: Decimal | None
) -> Content:
    who = advocate_name or "The advocate"
    price = f" Fee: {format_inr(fee)}." if fee is not None else ""
    return Content(
        NotificationKind.MATTER_ACCEPTED,
        "Request accepted",
        _clip(f"{who} accepted “{title}”.{price} Pay to confirm it.", 500),
        _matter_link(matter_id),
        "Your request was accepted — Legal Advisor",
        "An advocate accepted your request. Log in to review the quote and pay to confirm.",
    )


def matter_rejected(
    *, matter_id: uuid.UUID, title: str, advocate_name: str | None, note: str | None
) -> Content:
    who = advocate_name or "The advocate"
    reason = f" Note: {_clip(note, 300)}" if note else ""
    return Content(
        NotificationKind.MATTER_REJECTED,
        "Request declined",
        _clip(f"{who} declined “{title}”.{reason}", 500),
        _matter_link(matter_id),
        "An update on your request — Legal Advisor",
        "An advocate responded to your request. Log in to see the details.",
    )


def matter_cancelled(
    *, matter_id: uuid.UUID, title: str, cancelled_by: str, refunded: Decimal | None
) -> Content:
    refund = f" {format_inr(refunded)} was refunded in full." if refunded else ""
    return Content(
        NotificationKind.MATTER_CANCELLED,
        "Matter cancelled",
        _clip(f"“{title}” was cancelled by the {cancelled_by}.{refund}", 500),
        _matter_link(matter_id),
        "A matter was cancelled — Legal Advisor",
        "A matter you are part of was cancelled. Log in to see the details.",
    )


def matter_paid(
    *, matter_id: uuid.UUID, title: str, client_name: str | None, amount: Decimal
) -> Content:
    who = client_name or "The client"
    return Content(
        NotificationKind.MATTER_PAID,
        "Payment received",
        _clip(f"{who} paid {format_inr(amount)} for “{title}”. You can go ahead.", 500),
        _matter_link(matter_id),
        "A client has paid — Legal Advisor",
        "A client has paid for one of your matters. Log in to schedule or start the work.",
    )


def matter_scheduled(*, matter_id: uuid.UUID, title: str, when: datetime) -> Content:
    return Content(
        NotificationKind.MATTER_SCHEDULED,
        "Consultation scheduled",
        _clip(f"“{title}” is scheduled for {format_when(when)}.", 500),
        _matter_link(matter_id),
        "Your consultation was scheduled — Legal Advisor",
        "Your consultation has been scheduled. Log in to see when.",
    )


def matter_closed(*, matter_id: uuid.UUID, title: str) -> Content:
    return Content(
        NotificationKind.MATTER_CLOSED,
        "Matter closed",
        _clip(f"“{title}” was completed and closed.", 500),
        _matter_link(matter_id),
        "Your matter was completed — Legal Advisor",
        "Your matter has been completed. Log in to see the final documents.",
    )


def message_received(*, matter_id: uuid.UUID, title: str, sender_name: str | None) -> Content:
    who = sender_name or "Someone"
    return Content(
        NotificationKind.MESSAGE_RECEIVED,
        "New message",
        _clip(f"{who} sent a message on “{title}”.", 500),
        _matter_link(matter_id),
    )


def document_requested(*, matter_id: uuid.UUID, title: str, description: str) -> Content:
    return Content(
        NotificationKind.DOCUMENT_REQUESTED,
        "Document requested",
        _clip(f"Your advocate asked for a document on “{title}”: {description}", 500),
        _matter_link(matter_id),
        "A document was requested — Legal Advisor",
        "Your advocate has asked you for a document. Log in to upload it.",
    )


def document_uploaded(*, matter_id: uuid.UUID, title: str, is_final: bool) -> Content:
    what = "the final document" if is_final else "a document"
    return Content(
        NotificationKind.DOCUMENT_UPLOADED,
        "Final document ready" if is_final else "Document uploaded",
        _clip(f"{what.capitalize()} was uploaded to “{title}”.", 500),
        _matter_link(matter_id),
    )


def refund_issued(*, matter_id: uuid.UUID, title: str, amount: Decimal, reason: str) -> Content:
    return Content(
        NotificationKind.REFUND_ISSUED,
        "Refund issued",
        _clip(f"{format_inr(amount)} was refunded for “{title}”. Reason: {reason}", 500),
        _matter_link(matter_id),
        "A refund was issued — Legal Advisor",
        "A refund has been issued to you. Log in to see the details.",
    )


def advocate_verified() -> Content:
    return Content(
        NotificationKind.ADVOCATE_VERIFIED,
        "Profile verified",
        "Your advocate profile was verified. Clients can now find and book you.",
        "/",
        "Your profile was verified — Legal Advisor",
        "Your advocate profile has been verified. Clients can now find and book you.",
    )


def advocate_rejected(*, note: str | None) -> Content:
    reason = f" Note: {_clip(note, 300)}" if note else ""
    return Content(
        NotificationKind.ADVOCATE_REJECTED,
        "Profile not verified",
        f"Your advocate profile was not verified.{reason}",
        "/profile",
        "An update on your profile — Legal Advisor",
        "Your advocate profile was reviewed. Log in to see the outcome.",
    )


def render_email(content: Content, *, base_url: str) -> tuple[str, str] | None:
    """(subject, body) for the notification's email, or None when it is in-app only."""
    if content.email_subject is None or content.email_line is None:
        return None
    lines = [content.email_line]
    if content.link:
        lines += ["", f"Open it here: {base_url.rstrip('/')}{content.link}"]
    lines += [
        "",
        "You are receiving this because of activity on your Legal Advisor account. "
        "You can turn these emails off in your notification settings.",
    ]
    return content.email_subject, "\n".join(lines)


__all__ = [
    "Content",
    "advocate_rejected",
    "advocate_verified",
    "document_requested",
    "document_uploaded",
    "format_inr",
    "format_when",
    "matter_accepted",
    "matter_cancelled",
    "matter_closed",
    "matter_paid",
    "matter_rejected",
    "matter_requested",
    "matter_scheduled",
    "message_received",
    "refund_issued",
    "render_email",
]
