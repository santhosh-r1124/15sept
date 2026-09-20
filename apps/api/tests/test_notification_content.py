"""Unit tests for notification wording (Phase 11). Pure - no database."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.notification import NotificationKind
from app.services.notifications import content as notice

MID = uuid.UUID("11111111-1111-1111-1111-111111111111")
SECRET_TITLE = "Divorce petition against Ramesh"


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (Decimal("0"), "₹0.00"),
        (Decimal("750"), "₹750.00"),
        (Decimal("1000"), "₹1,000.00"),
        (Decimal("12345.5"), "₹12,345.50"),
        (Decimal("123456.78"), "₹1,23,456.78"),
        (Decimal("1234567"), "₹12,34,567.00"),
        (Decimal("12345678.9"), "₹1,23,45,678.90"),
        (Decimal("-2500"), "-₹2,500.00"),
    ],
)
def test_inr_uses_indian_digit_grouping(amount: Decimal, expected: str) -> None:
    assert notice.format_inr(amount) == expected


def test_when_is_shown_in_utc_whatever_zone_it_came_in() -> None:
    ist = timezone(timedelta(hours=5, minutes=30))
    assert notice.format_when(datetime(2026, 9, 20, 16, 0, tzinfo=ist)) == "20 Sep 2026, 10:30 UTC"
    assert notice.format_when(datetime(2026, 1, 5, 9, 5, tzinfo=UTC)) == "5 Jan 2026, 09:05 UTC"


def _all_contents() -> list[notice.Content]:
    return [
        notice.matter_requested(matter_id=MID, title=SECRET_TITLE, client_name="Asha"),
        notice.matter_accepted(
            matter_id=MID, title=SECRET_TITLE, advocate_name="Adv. Rao", fee=Decimal("750")
        ),
        notice.matter_rejected(
            matter_id=MID, title=SECRET_TITLE, advocate_name="Adv. Rao", note="Conflict of interest"
        ),
        notice.matter_cancelled(
            matter_id=MID, title=SECRET_TITLE, cancelled_by="advocate", refunded=Decimal("750")
        ),
        notice.matter_paid(
            matter_id=MID, title=SECRET_TITLE, client_name="Asha", amount=Decimal("750")
        ),
        notice.matter_scheduled(matter_id=MID, title=SECRET_TITLE, when=datetime.now(UTC)),
        notice.matter_closed(matter_id=MID, title=SECRET_TITLE),
        notice.message_received(matter_id=MID, title=SECRET_TITLE, sender_name="Asha"),
        notice.call_waiting(matter_id=MID, title=SECRET_TITLE, who="Asha"),
        notice.document_requested(
            matter_id=MID, title=SECRET_TITLE, description="Marriage certificate"
        ),
        notice.document_uploaded(matter_id=MID, title=SECRET_TITLE, is_final=True),
        notice.refund_issued(
            matter_id=MID, title=SECRET_TITLE, amount=Decimal("100"), reason="Goodwill"
        ),
        notice.advocate_verified(),
        notice.advocate_rejected(note="Bar council number not found"),
    ]


def test_every_notification_kind_has_content() -> None:
    assert {c.kind for c in _all_contents()} == set(NotificationKind)


def test_in_app_text_names_the_matter() -> None:
    accepted = notice.matter_accepted(
        matter_id=MID, title="Tenant deposit", advocate_name="Adv. Rao", fee=Decimal("750")
    )
    assert accepted.body == "Adv. Rao accepted “Tenant deposit”. Fee: ₹750.00. Pay to confirm it."
    assert accepted.link == f"/matters/{MID}"


@pytest.mark.parametrize("content", _all_contents(), ids=lambda c: c.kind.value)
def test_emails_never_carry_matter_details(content: notice.Content) -> None:
    rendered = notice.render_email(content, base_url="https://app.example.com")
    if rendered is None:
        return
    subject, body = rendered
    text = f"{subject}\n{body}"
    # Legal matters are sensitive and email isn't private: no titles, names, notes or amounts.
    for leaked in (
        SECRET_TITLE,
        "Ramesh",
        "Asha",
        "Adv. Rao",
        "Conflict of interest",
        "Marriage certificate",
        "Goodwill",
        "Bar council",
        "₹",
    ):
        assert leaked not in text


def test_email_links_into_the_right_app_and_offers_an_opt_out() -> None:
    content = notice.matter_closed(matter_id=MID, title="x")
    _subject, body = notice.render_email(content, base_url="https://app.example.com/") or ("", "")
    assert f"Open it here: https://app.example.com/matters/{MID}" in body  # no double slash
    assert "turn these emails off" in body


def test_chat_like_events_are_in_app_only() -> None:
    message = notice.message_received(matter_id=MID, title="x", sender_name="Asha")
    upload = notice.document_uploaded(matter_id=MID, title="x", is_final=False)
    assert notice.render_email(message, base_url="https://a.example") is None
    assert notice.render_email(upload, base_url="https://a.example") is None


def test_long_user_text_is_clipped_and_whitespace_collapsed() -> None:
    content = notice.matter_requested(matter_id=MID, title="word " * 400, client_name="A\n\nB")
    assert len(content.body) <= 500
    assert content.body.endswith("…")
    assert "\n" not in content.body


def test_a_missing_name_falls_back_to_a_neutral_word() -> None:
    assert notice.matter_requested(matter_id=MID, title="x", client_name=None).body.startswith(
        "A client"
    )
    assert notice.matter_paid(
        matter_id=MID, title="x", client_name=None, amount=Decimal("1")
    ).body.startswith("The client")
