"""Unit tests for advocate earnings arithmetic - pure logic."""

from __future__ import annotations

from decimal import Decimal

from app.models.matter import MatterStatus as M
from app.services.matters.earnings import summarize_earnings

D = Decimal


def test_only_closed_matters_count_as_earned_and_paid_in_progress_as_pending() -> None:
    summary = summarize_earnings(
        [
            (M.CLOSED, D("1000.00")),
            (M.CLOSED, D("500.50")),
            (M.PAID, D("300.00")),
            (M.SCHEDULED, D("200.00")),
            # Nothing has been paid on these, so they earn nothing.
            (M.REQUESTED, D("999.00")),
            (M.ACCEPTED, D("999.00")),
            (M.CANCELLED, D("999.00")),
            (M.REJECTED, D("999.00")),
        ],
        D("0"),
    )
    assert summary.gross_earned == D("1500.50")
    assert summary.pending == D("500.00")


def test_zero_platform_fee_by_default_means_net_equals_gross() -> None:
    summary = summarize_earnings([(M.CLOSED, D("1000.00"))], D("0"))
    assert summary.platform_fee == D("0.00")
    assert summary.net_earned == D("1000.00")


def test_platform_fee_applies_to_earned_only_and_rounds_to_paise() -> None:
    summary = summarize_earnings([(M.CLOSED, D("999.99")), (M.PAID, D("5000.00"))], D("12.5"))
    assert summary.platform_fee == D("125.00")  # 124.99875 -> 125.00
    assert summary.net_earned == D("874.99")
    assert summary.pending == D("5000.00")  # the fee isn't taken until the work is delivered


def test_matters_without_a_quote_are_skipped_and_empty_input_is_zero() -> None:
    summary = summarize_earnings([(M.CLOSED, None)], D("10"))
    assert (summary.gross_earned, summary.pending) == (D("0.00"), D("0.00"))
    assert summarize_earnings([], D("10")).net_earned == D("0.00")
