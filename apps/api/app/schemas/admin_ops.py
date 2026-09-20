"""Admin & legal-ops schemas: overview, matters, advocate list, query review (Phase 12)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.matter import MatterServiceType, MatterStatus
from app.schemas.advocate import AdvocateProfileOut


class PaymentTotals(BaseModel):
    count: int
    gross: Decimal
    refunded: Decimal


class OverviewOut(BaseModel):
    """Every breakdown lists *all* keys (zero-filled) so the UI never has to guess."""

    users_by_role: dict[str, int]
    advocates_by_status: dict[str, int]
    matters_by_status: dict[str, int]
    sources_by_status: dict[str, int]
    payments: PaymentTotals
    # Things a person has to act on:
    advocates_pending: int
    reviews_pending: int
    # Notification emails that haven't gone out (mail server trouble).
    emails_pending: int
    emails_failed: int


class AdminAdvocateOut(AdvocateProfileOut):
    """The advocate profile plus who it belongs to - which the public/own views leave out."""

    display_name: str | None
    email: str
    created_at: datetime


class PaginatedAdminAdvocates(BaseModel):
    items: list[AdminAdvocateOut]
    total: int
    limit: int
    offset: int


class AdminMatterOut(BaseModel):
    id: uuid.UUID
    title: str
    service_type: MatterServiceType
    status: MatterStatus
    quoted_fee: Decimal | None
    consumer_name: str | None
    advocate_name: str | None
    created_at: datetime
    updated_at: datetime


class PaginatedAdminMatters(BaseModel):
    items: list[AdminMatterOut]
    total: int
    limit: int
    offset: int


class QueryReviewOut(BaseModel):
    """A high-risk chat query for legal-ops review.

    Deliberately *no* user id or email: reviewers need the question, the answer and the
    classification - not who asked. ``registered`` only says whether it was a logged-in user.
    """

    id: uuid.UUID  # the user's message
    conversation_id: uuid.UUID
    created_at: datetime
    risk_level: str
    legal_category: str | None
    jurisdiction_scope: str | None
    question: str
    answer: str | None
    answer_source_count: int | None
    registered: bool
    reviewed_at: datetime | None
    review_note: str | None


class PaginatedQueryReviews(BaseModel):
    items: list[QueryReviewOut]
    total: int
    limit: int
    offset: int


class ReviewRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1000)
