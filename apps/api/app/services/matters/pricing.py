"""Fee quoting for a matter (Phase 8).

``AdvocateProfile.consultation_fee`` is a single number with no stated duration, while the
FRD offers 15/30/60-minute consultations (§9). Assumption, recorded in
docs/adr/0010-matter-lifecycle-and-payments.md: the profile fee is the price of a
**60-minute** consultation, prorated linearly for 15 and 30 minutes. The advocate can
always overwrite the figure when accepting, and document services have no formula at all
(scope varies too much), so those are quoted by the advocate on accept.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.models.matter import MatterServiceType

CONSULTATION_MINUTES = (15, 30, 60)
_BASE_MINUTES = Decimal(60)
_CENT = Decimal("0.01")


def default_quote(
    service_type: MatterServiceType, minutes: int | None, profile_fee: Decimal | None
) -> Decimal | None:
    if service_type is not MatterServiceType.CONSULTATION or minutes is None or profile_fee is None:
        return None
    return (profile_fee * Decimal(minutes) / _BASE_MINUTES).quantize(_CENT, rounding=ROUND_HALF_UP)
