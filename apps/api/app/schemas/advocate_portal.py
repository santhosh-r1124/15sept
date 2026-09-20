"""Advocate portal (dashboard + earnings) schemas (Phase 9, FRD 10)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.matter import MatterStatus


class UpcomingAppointmentOut(BaseModel):
    matter_id: uuid.UUID
    title: str
    scheduled_at: datetime
    consultation_minutes: int | None
    client_name: str | None


class EarningsSummaryOut(BaseModel):
    currency: str = "INR"
    gross_earned: Decimal
    platform_fee_percent: Decimal
    platform_fee: Decimal
    net_earned: Decimal
    pending: Decimal


class AdvocateDashboardOut(BaseModel):
    new_requests: int  # REQUESTED - waiting for the advocate to accept/reject
    awaiting_payment: int  # ACCEPTED - quote sent, client hasn't paid
    to_schedule: int  # PAID consultations with no appointment yet
    open_document_requests: int  # documents the advocate asked for and hasn't received
    awaiting_reply: int  # open matters whose latest message is from the client
    upcoming_appointments: list[UpcomingAppointmentOut]
    earnings: EarningsSummaryOut


class EarningsLineItemOut(BaseModel):
    matter_id: uuid.UUID
    title: str
    amount: Decimal
    status: MatterStatus
    paid_at: datetime | None
    closed_at: datetime | None


class EarningsOut(BaseModel):
    summary: EarningsSummaryOut
    items: list[EarningsLineItemOut]
