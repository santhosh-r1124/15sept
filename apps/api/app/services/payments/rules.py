"""Pure money rules for payments and refunds (Phase 10) - no DB, no I/O.

Kept separate from the ledger so the arithmetic that decides how much can be refunded, and
what a payment's status becomes, is unit-tested exhaustively.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.core.errors import ValidationAppError
from app.models.payment import PaymentStatus

_CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    """Quantise to paise, half-up."""
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def remaining_refundable(amount: Decimal, refunded: Decimal) -> Decimal:
    return money(amount - refunded)


def resolve_refund_amount(
    requested: Decimal | None, *, amount: Decimal, refunded: Decimal
) -> Decimal:
    """The amount to refund: the whole remainder when ``requested`` is None, else ``requested``
    - which must be positive and no more than what's left (you can't refund more than was paid).
    """
    remaining = remaining_refundable(amount, refunded)
    if requested is None:
        requested = remaining
    requested = money(requested)
    if requested <= 0:
        raise ValidationAppError(
            "Nothing left to refund." if remaining <= 0 else "The refund amount must be positive.",
            details=[{"field": "amount", "message": "Must be greater than zero."}],
        )
    if requested > remaining:
        raise ValidationAppError(
            f"Only {remaining} of this payment can still be refunded.",
            details=[{"field": "amount", "message": f"At most {remaining}."}],
        )
    return requested


def status_after_refund(amount: Decimal, refunded: Decimal) -> PaymentStatus:
    if refunded <= 0:
        return PaymentStatus.SUCCEEDED
    if refunded >= amount:
        return PaymentStatus.REFUNDED
    return PaymentStatus.PARTIALLY_REFUNDED


def format_invoice_number(year: int, sequence_value: int) -> str:
    return f"INV-{year}-{sequence_value:06d}"
