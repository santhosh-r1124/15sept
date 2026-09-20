"""Matter (booking) request/response schemas (Phase 8)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.matter import MatterServiceType, MatterStatus
from app.services.matters.pricing import CONSULTATION_MINUTES


class CreateMatterRequest(BaseModel):
    advocate_id: uuid.UUID  # AdvocateProfile.id — the id public search returns
    service_type: MatterServiceType
    consultation_minutes: int | None = None
    title: str = Field(min_length=1, max_length=200)
    requirement: str = Field(min_length=1, max_length=4000)
    preferred_language: str | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def _minutes_match_service(self) -> CreateMatterRequest:
        if self.service_type is MatterServiceType.CONSULTATION:
            if self.consultation_minutes not in CONSULTATION_MINUTES:
                raise ValueError(f"consultation_minutes must be one of {CONSULTATION_MINUTES}")
        elif self.consultation_minutes is not None:
            raise ValueError("consultation_minutes only applies to CONSULTATION")
        return self


class AcceptMatterRequest(BaseModel):
    # Required unless the matter already carries a prefilled quote (consultations).
    quoted_fee: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    note: str | None = Field(default=None, max_length=1000)


class RejectMatterRequest(BaseModel):
    note: str = Field(min_length=1, max_length=1000)


class CancelMatterRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class ScheduleMatterRequest(BaseModel):
    scheduled_at: datetime


class PostMessageRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class MatterAdvocateOut(BaseModel):
    profile_id: uuid.UUID
    display_name: str | None


class MatterConsumerOut(BaseModel):
    display_name: str | None
    # FRD §10 shows the advocate an "anonymous/verified identity" — not the email itself.
    verified: bool


class MatterOut(BaseModel):
    id: uuid.UUID
    service_type: MatterServiceType
    consultation_minutes: int | None
    title: str
    requirement: str
    preferred_language: str | None
    status: MatterStatus
    quoted_fee: Decimal | None
    decision_note: str | None
    scheduled_at: datetime | None
    paid_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    advocate: MatterAdvocateOut
    consumer: MatterConsumerOut


class PaginatedMatters(BaseModel):
    items: list[MatterOut]
    total: int
    limit: int
    offset: int


class MatterMessageOut(BaseModel):
    id: uuid.UUID
    matter_id: uuid.UUID
    sender_id: uuid.UUID
    sender_role: Literal["CONSUMER", "ADVOCATE"]
    body: str
    created_at: datetime
