"""Advocate earnings arithmetic (Phase 9) - pure, so it's unit-tested without a database.

Money is only counted once the client has paid. Two buckets:

* **earned**  - matters the advocate has CLOSED (the work is delivered);
* **pending** - matters that are PAID or SCHEDULED (paid for, work still in progress).

The platform's cut (``Settings.platform_fee_percent``) applies to *earned* only; it defaults
to 0 because the commission model is a business decision the FRD leaves open (section 16).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.models.matter import MatterStatus

_CENT = Decimal("0.01")
_HUNDRED = Decimal(100)
EARNED_STATUSES = (MatterStatus.CLOSED,)
PENDING_STATUSES = (MatterStatus.PAID, MatterStatus.SCHEDULED)


@dataclass(frozen=True, slots=True)
class EarningsSummary:
    gross_earned: Decimal
    platform_fee: Decimal
    net_earned: Decimal
    pending: Decimal


def summarize_earnings(
    rows: Iterable[tuple[MatterStatus, Decimal | None]], fee_percent: Decimal
) -> EarningsSummary:
    earned = Decimal(0)
    pending = Decimal(0)
    for status, amount in rows:
        if amount is None:
            continue
        if status in EARNED_STATUSES:
            earned += amount
        elif status in PENDING_STATUSES:
            pending += amount
    fee = (earned * fee_percent / _HUNDRED).quantize(_CENT, rounding=ROUND_HALF_UP)
    return EarningsSummary(
        gross_earned=earned.quantize(_CENT),
        platform_fee=fee,
        net_earned=(earned - fee).quantize(_CENT),
        pending=pending.quantize(_CENT),
    )
