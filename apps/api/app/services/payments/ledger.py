"""Payments ledger operations (Phase 10): take a payment + issue its invoice, and refund.

Every function runs inside the caller's transaction and only ``flush``es - the route commits, so
a provider failure part-way through leaves nothing behind (the matter never becomes PAID without
a payment row, or CANCELLED without its refund).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ConflictError, ServiceUnavailableError
from app.models.matter import Matter
from app.models.payment import Invoice, Payment, Refund
from app.models.user import User
from app.services.payments import get_payment_provider
from app.services.payments.rules import (
    format_invoice_number,
    money,
    remaining_refundable,
    resolve_refund_amount,
    status_after_refund,
)


async def _next_invoice_number(db: AsyncSession) -> str:
    value = (await db.execute(text("SELECT nextval('invoice_number_seq')"))).scalar_one()
    return format_invoice_number(datetime.now(UTC).year, int(value))


async def record_payment(
    db: AsyncSession, settings: Settings, matter: Matter, payer: User
) -> tuple[Payment, Invoice]:
    """Charge the matter's quoted fee and issue its invoice (matter must be ACCEPTED)."""
    if matter.quoted_fee is None:  # ACCEPTED always carries a quote; belt and braces
        raise ConflictError("This matter has no fee quote to pay.", code="no_quote")

    provider = get_payment_provider(settings)
    result = await provider.charge(
        amount=matter.quoted_fee, description=matter.title, idempotency_key=str(matter.id)
    )
    payment = Payment(
        matter_id=matter.id,
        payer_id=payer.id,
        amount=money(result.amount),
        currency=result.currency,
        provider=provider.name,
        provider_reference=result.reference,
    )
    db.add(payment)
    await db.flush()

    invoice = Invoice(
        invoice_number=await _next_invoice_number(db),
        payment_id=payment.id,
        matter_id=matter.id,
        consumer_id=matter.consumer_id,
        advocate_profile_id=matter.advocate_profile_id,
        description=matter.title[:300],
        client_name=(matter.consumer.display_name or "Client")[:150],
        advocate_name=(matter.advocate_profile.user.display_name or "Advocate")[:150],
        amount=payment.amount,
        currency=payment.currency,
    )
    db.add(invoice)
    await db.flush()
    return payment, invoice


async def get_payment_for_update(db: AsyncSession, payment_id: uuid.UUID) -> Payment | None:
    """Row-locked, so two concurrent refunds can't both pass the "how much is left" check."""
    payment: Payment | None = await db.scalar(
        select(Payment)
        .where(Payment.id == payment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return payment


async def issue_refund(
    db: AsyncSession,
    settings: Settings,
    payment: Payment,
    *,
    requested: Decimal | None,
    reason: str,
    initiated_by_id: uuid.UUID | None,
) -> Refund:
    """Refund ``requested`` (or everything left) of ``payment`` through its provider."""
    amount = resolve_refund_amount(
        requested, amount=payment.amount, refunded=payment.refunded_amount
    )
    provider = get_payment_provider(settings)
    if provider.name != payment.provider:
        # Refunds must go back through whoever took the money; a config change since then means
        # this needs a human, not a silent refund via the wrong gateway.
        raise ServiceUnavailableError(
            "This payment was taken through a different payment provider than the one "
            "currently configured.",
            code="payment_provider_mismatch",
        )

    prior = (
        await db.execute(
            select(func.count()).select_from(Refund).where(Refund.payment_id == payment.id)
        )
    ).scalar_one()
    result = await provider.refund(
        payment_reference=payment.provider_reference,
        amount=amount,
        idempotency_key=f"{payment.id}-{prior + 1}",
    )
    refund = Refund(
        payment_id=payment.id,
        amount=amount,
        reason=reason,
        provider_reference=result.reference,
        initiated_by_id=initiated_by_id,
    )
    db.add(refund)
    payment.refunded_amount = money(payment.refunded_amount + amount)
    payment.status = status_after_refund(payment.amount, payment.refunded_amount)
    await db.flush()
    return refund


async def refund_matter_in_full(
    db: AsyncSession,
    settings: Settings,
    matter: Matter,
    *,
    reason: str,
    initiated_by_id: uuid.UUID,
) -> Refund | None:
    """Refund whatever is left of a matter's payment (used when a paid matter is cancelled).
    Returns None if the matter was never paid or is already fully refunded."""
    payment = await db.scalar(
        select(Payment)
        .where(Payment.matter_id == matter.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if payment is None or remaining_refundable(payment.amount, payment.refunded_amount) <= 0:
        return None
    return await issue_refund(
        db, settings, payment, requested=None, reason=reason, initiated_by_id=initiated_by_id
    )
