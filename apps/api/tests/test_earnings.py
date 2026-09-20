"""Unit tests for advocate earnings arithmetic - pure logic."""

from __future__ import annotations

from decimal import Decimal

from app.models.matter import MatterStatus as M
from app.services.matters.earnings import summarize_earnings

D = Decimal


def test_only_closed_matters_count_as_earned_and_paid_in_progress_as_pending() -> None:
    summary = summarize_earnings(
        [
            (M.CLOSED, D("1000.00"), D("0")),
            (M.CLOSED, D("500.50"), D("0")),
            (M.PAID, D("300.00"), D("0")),
            (M.SCHEDULED, D("200.00"), D("0")),
            # Nothing has been paid on these, so they earn nothing.
            (M.REQUESTED, D("999.00"), D("0")),
            (M.ACCEPTED, D("999.00"), D("0")),
            (M.CANCELLED, D("999.00"), D("0")),
            (M.REJECTED, D("999.00"), D("0")),
        ],
        D("0"),
    )
    assert summary.gross_earned == D("1500.50")
    assert summary.pending == D("500.00")


def test_zero_platform_fee_by_default_means_net_equals_gross() -> None:
    summary = summarize_earnings([(M.CLOSED, D("1000.00"), D("0"))], D("0"))
    assert summary.platform_fee == D("0.00")
    assert summary.net_earned == D("1000.00")


def test_platform_fee_applies_to_earned_only_and_rounds_to_paise() -> None:
    summary = summarize_earnings(
        [(M.CLOSED, D("999.99"), D("0")), (M.PAID, D("5000.00"), D("0"))], D("12.5")
    )
    assert summary.platform_fee == D("125.00")  # 124.99875 -> 125.00
    assert summary.net_earned == D("874.99")
    assert summary.pending == D("5000.00")  # the fee isn't taken until the work is delivered


def test_matters_without_a_quote_are_skipped_and_empty_input_is_zero() -> None:
    summary = summarize_earnings([(M.CLOSED, None, D("0"))], D("10"))
    assert (summary.gross_earned, summary.pending) == (D("0.00"), D("0.00"))
    assert summarize_earnings([], D("10")).net_earned == D("0.00")


def test_refunds_come_off_what_the_advocate_earns() -> None:
    summary = summarize_earnings(
        [
            (M.CLOSED, D("1000.00"), D("250.00")),  # partly refunded: keeps 750
            (M.CLOSED, D("500.00"), D("500.00")),  # fully refunded: keeps nothing
            (M.PAID, D("400.00"), D("100.00")),  # pending is net of refunds too
        ],
        D("0"),
    )
    assert summary.gross_earned == D("750.00")
    assert summary.pending == D("300.00")


def test_a_refund_larger_than_the_charge_never_makes_earnings_negative() -> None:
    summary = summarize_earnings([(M.CLOSED, D("100.00"), D("150.00"))], D("0"))
    assert summary.gross_earned == D("0.00")
