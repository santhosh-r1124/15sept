"""Integration tests for notifications: the in-app feed and the email outbox (Phase 11).

Needs Postgres. Emails are captured with a fake sender, so nothing leaves the process.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.errors import ServiceUnavailableError
from app.models.notification import EmailStatus, Notification
from app.models.user import UserRole
from app.services.email import set_email_sender
from app.services.notifications import (
    MAX_EMAIL_ATTEMPTS,
    deliver_pending_emails,
    reset_delivery_pause,
)
from app.services.payments import MockPaymentProvider
from tests.helpers import (
    Account,
    advance_matter,
    book_matter,
    make_admin,
    register_advocate,
    register_consumer,
)

NOTIFICATIONS = "/api/v1/notifications"
MATTERS = "/api/v1/matters"
TITLE = "Rental agreement review"  # book_matter's default title


class Outbox:
    """A fake EmailSender: records what would have been sent, and can be told to fail."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []  # (to, subject, body)
        self.attempts = 0
        self.fail = False

    async def send(self, *, to: str, subject: str, body: str) -> None:
        self.attempts += 1
        if self.fail:
            raise ConnectionRefusedError("smtp is down")
        self.sent.append((to, subject, body))

    def to(self, address: str) -> list[tuple[str, str, str]]:
        return [mail for mail in self.sent if mail[0] == address]

    def reset(self) -> None:
        # Registration sends verification emails through the same sender; tests that count
        # notification emails start from a clean slate once their accounts exist.
        self.sent.clear()
        self.attempts = 0
        self.fail = False


@pytest.fixture
def outbox() -> Iterator[Outbox]:
    box = Outbox()
    set_email_sender(box)
    reset_delivery_pause()
    yield box
    set_email_sender(None)
    reset_delivery_pause()


async def _email(client: AsyncClient, who: Account) -> str:
    return str((await client.get("/api/v1/users/me", headers=who.headers)).json()["email"])


async def _feed(client: AsyncClient, who: Account, **params: Any) -> dict[str, Any]:
    resp = await client.get(NOTIFICATIONS, params=params, headers=who.headers)
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


async def _kinds(client: AsyncClient, who: Account) -> list[str]:
    return [n["kind"] for n in (await _feed(client, who))["items"]]  # newest first


async def _pair(
    client: AsyncClient, session: Any, outbox: Outbox, *, fail: bool = False
) -> tuple[Account, Account, dict[str, Any]]:
    """A consumer and advocate, and a booking between them. ``fail`` breaks the mail server for
    the booking (registration still works: it emails through the same sender)."""
    consumer = await register_consumer(client)
    advocate = await register_advocate(client, session)
    outbox.reset()
    outbox.fail = fail
    return consumer, advocate, await book_matter(client, consumer, advocate)


# --- the in-app feed --------------------------------------------------------------------------


async def test_booking_notifies_the_advocate_and_not_the_client(
    db_client: AsyncClient, db_txn_session: Any, outbox: Outbox
) -> None:
    consumer, advocate, matter = await _pair(db_client, db_txn_session, outbox)

    feed = await _feed(db_client, advocate)
    assert feed["total"] == 1
    assert feed["unread"] == 1
    (note,) = feed["items"]
    assert note["kind"] == "MATTER_REQUESTED"
    assert note["read"] is False
    assert note["link"] == f"/matters/{matter['id']}"
    assert TITLE in note["body"]  # in-app text may name the matter
    assert (await _feed(db_client, consumer))["total"] == 0


async def test_each_lifecycle_step_notifies_the_other_party(
    db_client: AsyncClient, db_txn_session: Any, outbox: Outbox
) -> None:
    consumer, advocate, matter = await _pair(db_client, db_txn_session, outbox)

    await advance_matter(db_client, matter, consumer, advocate, "CLOSED")

    assert await _kinds(db_client, advocate) == ["MATTER_PAID", "MATTER_REQUESTED"]
    assert await _kinds(db_client, consumer) == [
        "MATTER_CLOSED",
        "MATTER_SCHEDULED",
        "MATTER_ACCEPTED",
    ]


async def test_rejecting_tells_the_client_why_in_app(
    db_client: AsyncClient, db_txn_session: Any, outbox: Outbox
) -> None:
    consumer, advocate, matter = await _pair(db_client, db_txn_session, outbox)

    resp = await db_client.post(
        f"{MATTERS}/{matter['id']}/reject",
        json={"note": "Outside my practice area"},
        headers=advocate.headers,
    )
    assert resp.status_code == 200

    (note,) = (await _feed(db_client, consumer))["items"]
    assert note["kind"] == "MATTER_REJECTED"
    assert "Outside my practice area" in note["body"]


async def test_cancelling_a_paid_matter_tells_the_other_side_and_mentions_the_refund(
    db_client: AsyncClient, db_txn_session: Any, outbox: Outbox
) -> None:
    consumer, advocate, matter = await _pair(db_client, db_txn_session, outbox)
    await advance_matter(db_client, matter, consumer, advocate, "PAID")

    # The client backs out: the advocate hears about it.
    resp = await db_client.post(
        f"{MATTERS}/{matter['id']}/cancel", json={}, headers=consumer.headers
    )
    assert resp.status_code == 200
    latest = (await _feed(db_client, advocate))["items"][0]
    assert latest["kind"] == "MATTER_CANCELLED"
    assert "cancelled by the consumer" in latest["body"]

    # And when the advocate cancels a paid matter, the client hears about the refund.
    other = await book_matter(db_client, consumer, advocate, title="Second matter")
    await advance_matter(db_client, other, consumer, advocate, "PAID")
    await db_client.post(f"{MATTERS}/{other['id']}/cancel", json={}, headers=advocate.headers)
    latest = (await _feed(db_client, consumer))["items"][0]
    assert latest["kind"] == "MATTER_CANCELLED"
    assert "cancelled by the advocate" in latest["body"]
    assert "₹1,200.00 was refunded in full" in latest["body"]


async def test_a_burst_of_messages_is_one_unread_entry_until_it_is_read(
    db_client: AsyncClient, db_txn_session: Any, outbox: Outbox
) -> None:
    consumer, advocate, matter = await _pair(db_client, db_txn_session, outbox)
    await advance_matter(db_client, matter, consumer, advocate, "ACCEPTED")
    url = f"{MATTERS}/{matter['id']}/messages"

    for text in ("Hello", "Are you there?", "Hello??"):
        assert (
            await db_client.post(url, json={"body": text}, headers=consumer.headers)
        ).status_code == 201

    kinds = await _kinds(db_client, advocate)
    assert kinds.count("MESSAGE_RECEIVED") == 1
    # The message text itself never goes into the notification.
    entry = next(
        n for n in (await _feed(db_client, advocate))["items"] if n["kind"] == "MESSAGE_RECEIVED"
    )
    assert "Hello" not in entry["body"]

    await db_client.post(f"{NOTIFICATIONS}/{entry['id']}/read", headers=advocate.headers)
    await db_client.post(url, json={"body": "Ping"}, headers=consumer.headers)
    assert (await _kinds(db_client, advocate)).count("MESSAGE_RECEIVED") == 2


async def test_document_events_notify_the_other_side(
    db_client: AsyncClient, db_txn_session: Any, outbox: Outbox
) -> None:
    consumer, advocate, matter = await _pair(db_client, db_txn_session, outbox)
    await advance_matter(db_client, matter, consumer, advocate, "ACCEPTED")

    resp = await db_client.post(
        f"{MATTERS}/{matter['id']}/document-requests",
        json={"description": "Signed rental agreement"},
        headers=advocate.headers,
    )
    assert resp.status_code == 201
    latest = (await _feed(db_client, consumer))["items"][0]
    assert latest["kind"] == "DOCUMENT_REQUESTED"
    assert "Signed rental agreement" in latest["body"]

    resp = await db_client.post(
        f"{MATTERS}/{matter['id']}/files",
        files={"file": ("agreement.txt", b"the agreement", "text/plain")},
        headers=consumer.headers,
    )
    assert resp.status_code == 201, resp.text
    assert (await _kinds(db_client, advocate))[0] == "DOCUMENT_UPLOADED"


async def test_admin_actions_notify_the_people_they_affect(
    db_client: AsyncClient, db_txn_session: Any, outbox: Outbox
) -> None:
    admin = await make_admin(db_txn_session, UserRole.ADMIN)
    pending = await register_advocate(db_client, db_txn_session, verified=False)
    rejected = await register_advocate(db_client, db_txn_session, verified=False)
    outbox.reset()

    ok = await db_client.post(
        f"/api/v1/admin/advocates/{pending.profile_id}/verify", json={}, headers=admin.headers
    )
    no = await db_client.post(
        f"/api/v1/admin/advocates/{rejected.profile_id}/reject",
        json={"note": "Bar council number not found"},
        headers=admin.headers,
    )
    assert ok.status_code == 200
    assert no.status_code == 200

    assert await _kinds(db_client, pending) == ["ADVOCATE_VERIFIED"]
    (note,) = (await _feed(db_client, rejected))["items"]
    assert note["kind"] == "ADVOCATE_REJECTED"
    assert "Bar council number not found" in note["body"]
    assert len(outbox.sent) == 2  # both are emailed


async def test_an_admin_refund_notifies_the_client(
    db_client: AsyncClient, db_txn_session: Any, outbox: Outbox
) -> None:
    consumer, advocate, matter = await _pair(db_client, db_txn_session, outbox)
    await advance_matter(db_client, matter, consumer, advocate, "CLOSED")
    admin = await make_admin(db_txn_session, UserRole.ADMIN)
    payment = (
        await db_client.get(f"/api/v1/payments/matters/{matter['id']}", headers=consumer.headers)
    ).json()["payment"]

    resp = await db_client.post(
        f"/api/v1/admin/payments/{payment['id']}/refund",
        json={"amount": "100.00", "reason": "Goodwill gesture"},
        headers=admin.headers,
    )
    assert resp.status_code == 200, resp.text

    latest = (await _feed(db_client, consumer))["items"][0]
    assert latest["kind"] == "REFUND_ISSUED"
    assert "₹100.00" in latest["body"]


# --- reading, marking, preferences -----------------------------------------------------------


async def test_marking_read_and_the_unread_filter(
    db_client: AsyncClient, db_txn_session: Any, outbox: Outbox
) -> None:
    consumer, advocate, matter = await _pair(db_client, db_txn_session, outbox)
    await advance_matter(db_client, matter, consumer, advocate, "PAID")  # consumer: 1, advocate: 2
    feed = await _feed(db_client, advocate)
    assert (
        await db_client.get(f"{NOTIFICATIONS}/unread-count", headers=advocate.headers)
    ).json() == {"unread": 2}

    one = feed["items"][0]["id"]
    resp = await db_client.post(f"{NOTIFICATIONS}/{one}/read", headers=advocate.headers)
    assert resp.status_code == 200
    assert resp.json()["read"] is True

    unread = await _feed(db_client, advocate, unread_only="true")
    assert unread["total"] == 1
    assert unread["unread"] == 1
    assert unread["items"][0]["id"] != one
    page = await _feed(db_client, advocate, limit=1, offset=1)
    assert len(page["items"]) == 1
    assert page["total"] == 2


async def test_mark_all_read(db_client: AsyncClient, db_txn_session: Any, outbox: Outbox) -> None:
    consumer, advocate, matter = await _pair(db_client, db_txn_session, outbox)
    await advance_matter(db_client, matter, consumer, advocate, "PAID")

    first = await db_client.post(f"{NOTIFICATIONS}/read-all", headers=advocate.headers)
    second = await db_client.post(f"{NOTIFICATIONS}/read-all", headers=advocate.headers)

    assert first.json() == {"updated": 2}
    assert second.json() == {"updated": 0}
    assert (await _feed(db_client, advocate))["unread"] == 0
    assert (await _feed(db_client, consumer))["unread"] == 1  # somebody else's stay unread


async def test_you_cannot_touch_someone_elses_notification(
    db_client: AsyncClient, db_txn_session: Any, outbox: Outbox
) -> None:
    consumer, advocate, _matter = await _pair(db_client, db_txn_session, outbox)
    theirs = (await _feed(db_client, advocate))["items"][0]["id"]

    resp = await db_client.post(f"{NOTIFICATIONS}/{theirs}/read", headers=consumer.headers)

    assert resp.status_code == 404  # not 403: don't confirm it exists
    assert (await _feed(db_client, advocate))["unread"] == 1


async def test_notifications_require_login(db_client: AsyncClient) -> None:
    assert (await db_client.get(NOTIFICATIONS)).status_code == 401
    assert (await db_client.get(f"{NOTIFICATIONS}/unread-count")).status_code == 401
    assert (await db_client.post(f"{NOTIFICATIONS}/read-all")).status_code == 401


async def test_email_preference_defaults_on_and_can_be_turned_off(
    db_client: AsyncClient, db_txn_session: Any, outbox: Outbox
) -> None:
    consumer = await register_consumer(db_client)
    url = f"{NOTIFICATIONS}/preferences"

    assert (await db_client.get(url, headers=consumer.headers)).json() == {
        "email_notifications": True
    }
    resp = await db_client.put(url, json={"email_notifications": False}, headers=consumer.headers)
    assert resp.status_code == 200
    assert (await db_client.get(url, headers=consumer.headers)).json() == {
        "email_notifications": False
    }


# --- email delivery --------------------------------------------------------------------------


async def test_emails_go_to_the_right_app_and_leak_nothing(
    db_client: AsyncClient, db_txn_session: Any, outbox: Outbox
) -> None:
    consumer, advocate, matter = await _pair(db_client, db_txn_session, outbox)
    await advance_matter(db_client, matter, consumer, advocate, "ACCEPTED")
    settings = get_settings()

    (to_advocate,) = outbox.to(await _email(db_client, advocate))
    (to_client,) = outbox.to(await _email(db_client, consumer))
    # Each side is linked into *their* app.
    assert f"{settings.portal_base_url}/matters/{matter['id']}" in to_advocate[2]
    assert f"{settings.frontend_base_url}/matters/{matter['id']}" in to_client[2]
    for _to, subject, body in outbox.sent:
        assert TITLE not in subject
        assert TITLE not in body
        assert "₹" not in body

    statuses = (await db_txn_session.execute(select(Notification.email_status))).scalars().all()
    assert set(statuses) == {EmailStatus.SENT.value}


async def test_opting_out_keeps_the_in_app_entry_but_sends_no_email(
    db_client: AsyncClient, db_txn_session: Any, outbox: Outbox
) -> None:
    consumer, advocate, matter = await _pair(db_client, db_txn_session, outbox)
    await db_client.put(
        f"{NOTIFICATIONS}/preferences",
        json={"email_notifications": False},
        headers=consumer.headers,
    )
    outbox.sent.clear()

    await advance_matter(db_client, matter, consumer, advocate, "ACCEPTED")

    assert outbox.to(await _email(db_client, consumer)) == []
    assert await _kinds(db_client, consumer) == ["MATTER_ACCEPTED"]
    row = await db_txn_session.scalar(
        select(Notification).where(Notification.user_id == consumer.user_id)
    )
    assert row.email_status == EmailStatus.SKIPPED.value
    assert row.email_body is None


async def test_chat_like_events_send_no_email(
    db_client: AsyncClient, db_txn_session: Any, outbox: Outbox
) -> None:
    consumer, advocate, matter = await _pair(db_client, db_txn_session, outbox)
    await advance_matter(db_client, matter, consumer, advocate, "ACCEPTED")
    sent_before = len(outbox.sent)

    await db_client.post(
        f"{MATTERS}/{matter['id']}/messages", json={"body": "Hi"}, headers=consumer.headers
    )

    assert len(outbox.sent) == sent_before
    assert "MESSAGE_RECEIVED" in await _kinds(db_client, advocate)


async def test_a_dead_mail_server_never_breaks_the_request(
    db_client: AsyncClient, db_txn_session: Any, outbox: Outbox
) -> None:
    # The booking still succeeds with the mail server down.
    _consumer, advocate, _matter = await _pair(db_client, db_txn_session, outbox, fail=True)

    assert (await _feed(db_client, advocate))["total"] == 1  # the in-app entry is there
    row = await db_txn_session.scalar(select(Notification))
    assert row.email_status == EmailStatus.PENDING.value
    assert row.email_attempts == 1
    assert outbox.sent == []


async def test_after_a_failure_requests_stop_hammering_the_mail_server(
    db_client: AsyncClient, db_txn_session: Any, outbox: Outbox
) -> None:
    consumer, advocate, matter = await _pair(db_client, db_txn_session, outbox, fail=True)
    assert outbox.attempts == 1

    # More emails are triggered, but the sender is paused after the failure.
    await advance_matter(db_client, matter, consumer, advocate, "PAID")

    assert outbox.attempts == 1
    pending = (
        (
            await db_txn_session.execute(
                select(Notification).where(Notification.email_status == EmailStatus.PENDING.value)
            )
        )
        .scalars()
        .all()
    )
    assert len(pending) == 3  # booking, accepted, paid


async def test_the_outbox_retries_when_the_server_comes_back(
    db_client: AsyncClient, db_txn_session: Any, outbox: Outbox
) -> None:
    consumer, advocate, matter = await _pair(db_client, db_txn_session, outbox, fail=True)
    await advance_matter(db_client, matter, consumer, advocate, "ACCEPTED")
    outbox.fail = False

    result = await deliver_pending_emails(db_txn_session)

    assert result.sent == 2
    assert result.failed is False
    assert len(outbox.sent) == 2
    assert (await deliver_pending_emails(db_txn_session)).sent == 0  # nothing left


async def test_an_email_is_given_up_on_after_the_attempt_limit(
    db_client: AsyncClient, db_txn_session: Any, outbox: Outbox
) -> None:
    await _pair(db_client, db_txn_session, outbox, fail=True)  # attempt 1 (in the request)

    for _ in range(MAX_EMAIL_ATTEMPTS - 1):
        result = await deliver_pending_emails(db_txn_session)
        assert result.failed is True

    row = await db_txn_session.scalar(select(Notification))
    assert row.email_attempts == MAX_EMAIL_ATTEMPTS
    assert row.email_status == EmailStatus.FAILED.value
    outbox.fail = False
    assert (await deliver_pending_emails(db_txn_session)).sent == 0  # FAILED is not retried


async def test_a_rolled_back_action_leaves_no_notification_and_no_email(
    db_client: AsyncClient, db_txn_session: Any, outbox: Outbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    consumer, advocate, matter = await _pair(db_client, db_txn_session, outbox)
    await advance_matter(db_client, matter, consumer, advocate, "PAID")
    notes_before = await _kinds(db_client, consumer)
    sent_before = len(outbox.sent)

    async def broken_refund(self: object, **_kw: object) -> None:
        raise ServiceUnavailableError("gateway down", code="payments_error")

    monkeypatch.setattr(MockPaymentProvider, "refund", broken_refund)
    resp = await db_client.post(
        f"{MATTERS}/{matter['id']}/cancel", json={}, headers=advocate.headers
    )
    assert resp.status_code == 503
    monkeypatch.undo()

    # The cancel was rolled back, so nobody was told it happened...
    assert await _kinds(db_client, consumer) == notes_before
    assert "MATTER_CANCELLED" not in await _kinds(db_client, consumer)
    # ...and the next unrelated email is the only one sent (no ghost "cancelled" email).
    await book_matter(db_client, consumer, advocate, title="Another")
    new = outbox.sent[sent_before:]
    assert len(new) == 1
    assert new[0][1].startswith("You have a new request")
