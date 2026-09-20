"""Payments, invoices and (admin) refunds (Phase 10).

Reads are open to the payment's two participants and to admins; anyone else gets a 404.
Taking a payment happens in ``POST /matters/{id}/pay`` and cancelling a paid matter refunds it
automatically (both in routes/matters.py) - the only route here that moves money is the admin
refund, for the cases policy doesn't cover (disputes, partial refunds, refunds after a matter
was closed).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import ColumnElement, func, select

from app.api.deps import CurrentUser, DbSession, SettingsDep, require_roles
from app.core.errors import NotFoundError
from app.models.matter import Matter
from app.models.payment import Invoice, Payment, Refund
from app.models.user import AdvocateProfile, User, UserRole
from app.schemas.payment import (
    InvoiceOut,
    MatterPaymentOut,
    PaginatedPayments,
    PaymentOut,
    PaymentSummaryOut,
    RefundOut,
    RefundRequest,
)
from app.services.matters.access import ADMIN_ROLES, load_matter, readable_by
from app.services.payments.invoice import render_invoice_html
from app.services.payments.ledger import get_payment_for_update, issue_refund

router = APIRouter()
admin_router = APIRouter()

AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.LEGAL_ADMIN))]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]

# An invoice is a page served from our own origin; lock down everything but its inline style.
_INVOICE_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "private, no-store",
}


async def _refunds(db: DbSession, payment_id: uuid.UUID) -> list[Refund]:
    rows = await db.execute(
        select(Refund).where(Refund.payment_id == payment_id).order_by(Refund.created_at, Refund.id)
    )
    return list(rows.scalars().all())


def _payment_out(payment: Payment, refunds: list[Refund]) -> PaymentOut:
    return PaymentOut(
        id=payment.id,
        matter_id=payment.matter_id,
        amount=payment.amount,
        refunded_amount=payment.refunded_amount,
        currency=payment.currency,
        status=payment.status,
        provider=payment.provider,
        created_at=payment.created_at,
        refunds=[
            RefundOut(id=r.id, amount=r.amount, reason=r.reason, created_at=r.created_at)
            for r in refunds
        ],
    )


def _invoice_out(invoice: Invoice, payment: Payment) -> InvoiceOut:
    return InvoiceOut(
        id=invoice.id,
        invoice_number=invoice.invoice_number,
        matter_id=invoice.matter_id,
        description=invoice.description,
        client_name=invoice.client_name,
        advocate_name=invoice.advocate_name,
        amount=invoice.amount,
        refunded_amount=payment.refunded_amount,
        currency=invoice.currency,
        issued_at=invoice.issued_at,
    )


async def _load_invoice_for(
    db: DbSession, user: User, invoice_id: uuid.UUID
) -> tuple[Invoice, Payment]:
    row = (
        await db.execute(
            select(Invoice, Payment)
            .join(Payment, Payment.id == Invoice.payment_id)
            .where(Invoice.id == invoice_id)
        )
    ).first()
    if row is None:
        raise NotFoundError("Invoice not found.")
    invoice, payment = row
    is_client = invoice.consumer_id == user.id
    advocate_user_id = await db.scalar(
        select(AdvocateProfile.user_id).where(AdvocateProfile.id == invoice.advocate_profile_id)
    )
    if not (is_client or advocate_user_id == user.id or user.role in ADMIN_ROLES):
        raise NotFoundError("Invoice not found.")
    return invoice, payment


@router.get(
    "/matters/{matter_id}", response_model=MatterPaymentOut, summary="A matter's payment + invoice"
)
async def matter_payment(
    matter_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> MatterPaymentOut:
    matter = await load_matter(db, matter_id)
    readable_by(user, matter)
    row = (
        await db.execute(
            select(Payment, Invoice)
            .join(Invoice, Invoice.payment_id == Payment.id)
            .where(Payment.matter_id == matter.id)
        )
    ).first()
    if row is None:
        raise NotFoundError("This matter hasn't been paid for.")
    payment, invoice = row
    return MatterPaymentOut(
        payment=_payment_out(payment, await _refunds(db, payment.id)),
        invoice=_invoice_out(invoice, payment),
    )


@router.get("/mine", response_model=PaginatedPayments, summary="Payments you made or received")
async def my_payments(
    user: CurrentUser, db: DbSession, limit: Limit = 25, offset: Offset = 0
) -> PaginatedPayments:
    scope: ColumnElement[bool]
    if user.role is UserRole.ADVOCATE:
        scope = Invoice.advocate_profile_id.in_(
            select(AdvocateProfile.id).where(AdvocateProfile.user_id == user.id)
        )
    else:
        scope = Invoice.consumer_id == user.id
    total = (await db.execute(select(func.count()).select_from(Invoice).where(scope))).scalar_one()
    rows = (
        await db.execute(
            select(Payment, Invoice, Matter.title)
            .join(Invoice, Invoice.payment_id == Payment.id)
            .join(Matter, Matter.id == Payment.matter_id)
            .where(scope)
            .order_by(Payment.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return PaginatedPayments(
        items=[
            PaymentSummaryOut(
                payment_id=p.id,
                matter_id=p.matter_id,
                matter_title=title,
                invoice_id=i.id,
                invoice_number=i.invoice_number,
                amount=p.amount,
                refunded_amount=p.refunded_amount,
                currency=p.currency,
                status=p.status,
                created_at=p.created_at,
            )
            for p, i, title in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/invoices/{invoice_id}", response_model=InvoiceOut, summary="An invoice")
async def get_invoice(invoice_id: uuid.UUID, user: CurrentUser, db: DbSession) -> InvoiceOut:
    invoice, payment = await _load_invoice_for(db, user, invoice_id)
    return _invoice_out(invoice, payment)


@router.get(
    "/invoices/{invoice_id}/html",
    response_class=Response,
    summary="Printable invoice (HTML - print to PDF from the browser)",
)
async def get_invoice_html(invoice_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    invoice, payment = await _load_invoice_for(db, user, invoice_id)
    html = render_invoice_html(
        invoice_number=invoice.invoice_number,
        issued_at=invoice.issued_at,
        client_name=invoice.client_name,
        advocate_name=invoice.advocate_name,
        description=invoice.description,
        amount=invoice.amount,
        refunded=payment.refunded_amount,
        currency=invoice.currency,
    )
    return Response(content=html, media_type="text/html; charset=utf-8", headers=_INVOICE_HEADERS)


# ---- admin -----------------------------------------------------------------------------


@admin_router.get("", response_model=PaginatedPayments, summary="All payments")
async def admin_list_payments(
    _admin: AdminUser, db: DbSession, limit: Limit = 25, offset: Offset = 0
) -> PaginatedPayments:
    total = (await db.execute(select(func.count()).select_from(Payment))).scalar_one()
    rows = (
        await db.execute(
            select(Payment, Invoice, Matter.title)
            .join(Invoice, Invoice.payment_id == Payment.id)
            .join(Matter, Matter.id == Payment.matter_id)
            .order_by(Payment.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return PaginatedPayments(
        items=[
            PaymentSummaryOut(
                payment_id=p.id,
                matter_id=p.matter_id,
                matter_title=title,
                invoice_id=i.id,
                invoice_number=i.invoice_number,
                amount=p.amount,
                refunded_amount=p.refunded_amount,
                currency=p.currency,
                status=p.status,
                created_at=p.created_at,
            )
            for p, i, title in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@admin_router.post(
    "/{payment_id}/refund", response_model=PaymentOut, summary="Refund (all or part of) a payment"
)
async def admin_refund_payment(
    payment_id: uuid.UUID,
    payload: RefundRequest,
    admin: AdminUser,
    db: DbSession,
    settings: SettingsDep,
) -> PaymentOut:
    payment = await get_payment_for_update(db, payment_id)
    if payment is None:
        raise NotFoundError("Payment not found.")
    await issue_refund(
        db,
        settings,
        payment,
        requested=payload.amount,
        reason=payload.reason,
        initiated_by_id=admin.id,
    )
    await db.commit()
    await db.refresh(payment)
    return _payment_out(payment, await _refunds(db, payment.id))
