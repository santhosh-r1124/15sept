"""Payments / refunds / invoices schemas (Phase 10)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.payment import PaymentStatus


class RefundOut(BaseModel):
    id: uuid.UUID
    amount: Decimal
    reason: str
    created_at: datetime


class PaymentOut(BaseModel):
    id: uuid.UUID
    matter_id: uuid.UUID
    amount: Decimal
    refunded_amount: Decimal
    currency: str
    status: PaymentStatus
    provider: str
    created_at: datetime
    refunds: list[RefundOut]


class InvoiceOut(BaseModel):
    id: uuid.UUID
    invoice_number: str
    matter_id: uuid.UUID
    description: str
    client_name: str
    advocate_name: str
    amount: Decimal
    refunded_amount: Decimal
    currency: str
    issued_at: datetime


class MatterPaymentOut(BaseModel):
    payment: PaymentOut
    invoice: InvoiceOut


class PaymentSummaryOut(BaseModel):
    """One row of "my payments" - enough to link to the matter and its invoice."""

    payment_id: uuid.UUID
    matter_id: uuid.UUID
    matter_title: str
    invoice_id: uuid.UUID
    invoice_number: str
    amount: Decimal
    refunded_amount: Decimal
    currency: str
    status: PaymentStatus
    created_at: datetime


class PaginatedPayments(BaseModel):
    items: list[PaymentSummaryOut]
    total: int
    limit: int
    offset: int


class RefundRequest(BaseModel):
    # Omit to refund everything still refundable.
    amount: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    reason: str = Field(min_length=1, max_length=1000)
