"""Unit tests for the pure payment rules + invoice rendering - no DB, no network."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.errors import ValidationAppError
from app.models.payment import PaymentStatus
from app.services.payments.invoice import render_invoice_html
from app.services.payments.rules import (
    format_invoice_number,
    money,
    remaining_refundable,
    resolve_refund_amount,
    status_after_refund,
)

D = Decimal


def test_money_rounds_half_up_to_paise() -> None:
    assert money(D("10.005")) == D("10.01")
    assert money(D("10.004")) == D("10.00")
    assert money(D("7")) == D("7.00")


def test_remaining_refundable() -> None:
    assert remaining_refundable(D("750.00"), D("0")) == D("750.00")
    assert remaining_refundable(D("750.00"), D("250.00")) == D("500.00")
    assert remaining_refundable(D("750.00"), D("750.00")) == D("0.00")


def test_omitting_the_amount_refunds_everything_that_is_left() -> None:
    assert resolve_refund_amount(None, amount=D("750.00"), refunded=D("0")) == D("750.00")
    assert resolve_refund_amount(None, amount=D("750.00"), refunded=D("250.00")) == D("500.00")


def test_partial_refund_amounts_are_accepted_and_quantised() -> None:
    assert resolve_refund_amount(D("100"), amount=D("750.00"), refunded=D("0")) == D("100.00")
    assert resolve_refund_amount(D("500.00"), amount=D("750.00"), refunded=D("250.00")) == D(
        "500.00"
    )


@pytest.mark.parametrize("requested", [D("0"), D("-5.00")])
def test_non_positive_refunds_are_rejected(requested: Decimal) -> None:
    with pytest.raises(ValidationAppError):
        resolve_refund_amount(requested, amount=D("750.00"), refunded=D("0"))


def test_you_cannot_refund_more_than_was_paid() -> None:
    with pytest.raises(ValidationAppError) as exc:
        resolve_refund_amount(D("750.01"), amount=D("750.00"), refunded=D("0"))
    assert "750.00" in exc.value.message
    with pytest.raises(ValidationAppError):
        resolve_refund_amount(D("300.00"), amount=D("750.00"), refunded=D("500.00"))


def test_refunding_a_fully_refunded_payment_says_so() -> None:
    with pytest.raises(ValidationAppError) as exc:
        resolve_refund_amount(None, amount=D("750.00"), refunded=D("750.00"))
    assert "Nothing left" in exc.value.message


def test_payment_status_follows_the_refunded_total() -> None:
    assert status_after_refund(D("750.00"), D("0")) is PaymentStatus.SUCCEEDED
    assert status_after_refund(D("750.00"), D("0.01")) is PaymentStatus.PARTIALLY_REFUNDED
    assert status_after_refund(D("750.00"), D("749.99")) is PaymentStatus.PARTIALLY_REFUNDED
    assert status_after_refund(D("750.00"), D("750.00")) is PaymentStatus.REFUNDED


def test_invoice_numbers_are_year_prefixed_and_zero_padded() -> None:
    assert format_invoice_number(2026, 42) == "INV-2026-000042"
    assert format_invoice_number(2027, 1234567) == "INV-2027-1234567"  # grows, never truncates


def _render(**overrides: object) -> str:
    kwargs: dict[str, object] = {
        "invoice_number": "INV-2026-000001",
        "issued_at": datetime(2026, 9, 20, tzinfo=UTC),
        "client_name": "Demo Consumer",
        "advocate_name": "Adv. Kavya Rao",
        "description": "Rental agreement review",
        "amount": D("750.00"),
        "refunded": D("0"),
        "currency": "INR",
        **overrides,
    }
    return render_invoice_html(**kwargs)  # type: ignore[arg-type]


def test_invoice_shows_the_essentials_and_the_tax_caveat() -> None:
    html = _render()
    for expected in (
        "INV-2026-000001",
        "Demo Consumer",
        "Adv. Kavya Rao",
        "INR 750.00",
        "20 Sep 2026",
    ):
        assert expected in html
    assert "not calculated" in html  # no tax is computed - the document says so
    assert "Refunded" not in html


def test_invoice_shows_refunds_and_the_net_paid() -> None:
    html = _render(refunded=D("250.00"))
    assert "-INR 250.00" in html
    assert "Net paid" in html and "INR 500.00" in html


@pytest.mark.parametrize("field", ["client_name", "advocate_name", "description", "invoice_number"])
def test_user_supplied_text_is_html_escaped(field: str) -> None:
    html = _render(**{field: '<script>alert("x")</script>&<img src=x onerror=y>'})
    assert "<script>" not in html
    assert "<img" not in html
    assert "&lt;script&gt;" in html
