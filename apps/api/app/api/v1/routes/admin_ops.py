"""Admin & legal-ops endpoints (Phase 12): the platform overview, matter oversight, the full
advocate list, and the high-risk query review queue.

User management, advocate verification, legal-source management and refunds already exist
(``admin.py``, ``legal_sources.py``, ``payments.py``); this module adds what the dashboard was
missing. All of it is ADMIN / LEGAL_ADMIN only.

Chat content is private. Reviewers get the question, the answer and the classification, but never
the asker's identity (see ``QueryReviewOut``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import ColumnElement, case, func, select
from sqlalchemy.orm import aliased

from app.api.deps import DbSession, require_roles
from app.core.errors import NotFoundError
from app.models.chat import ChatMessage, Conversation, MessageRole
from app.models.legal_document import IngestionStatus, LegalDocument
from app.models.matter import Matter, MatterStatus
from app.models.notification import EmailStatus, Notification
from app.models.payment import Payment
from app.models.user import AdvocateProfile, User, UserRole, VerificationStatus
from app.schemas.admin_ops import (
    AdminAdvocateOut,
    AdminMatterOut,
    OverviewOut,
    PaginatedAdminAdvocates,
    PaginatedAdminMatters,
    PaginatedQueryReviews,
    PaymentTotals,
    QueryReviewOut,
    ReviewRequest,
)
from app.schemas.advocate import AdvocateProfileOut

router = APIRouter()

AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.LEGAL_ADMIN))]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]

_HIGH_RISK = ("HIGH", "CRITICAL")


async def _counts(db: DbSession, column: Any) -> dict[str, int]:  # any mapped column
    rows = (await db.execute(select(column, func.count()).group_by(column))).all()
    return {str(getattr(key, "value", key)): count for key, count in rows}


def _zero_filled(counts: dict[str, int], keys: list[str]) -> dict[str, int]:
    return {key: counts.get(key, 0) for key in keys}


@router.get("/overview", response_model=OverviewOut, summary="Platform overview")
async def overview(_admin: AdminUser, db: DbSession) -> OverviewOut:
    users = await _counts(db, User.role)
    advocates = await _counts(db, AdvocateProfile.verification_status)
    matters = await _counts(db, Matter.status)
    sources = await _counts(db, LegalDocument.ingestion_status)

    count, gross, refunded = (
        await db.execute(
            select(
                func.count(Payment.id),
                func.coalesce(func.sum(Payment.amount), 0),
                func.coalesce(func.sum(Payment.refunded_amount), 0),
            )
        )
    ).one()
    reviews_pending = (
        await db.execute(
            select(func.count())
            .select_from(ChatMessage)
            .where(ChatMessage.risk_level.in_(_HIGH_RISK), ChatMessage.reviewed_at.is_(None))
        )
    ).scalar_one()
    email_counts = await _counts(db, Notification.email_status)

    return OverviewOut(
        users_by_role=_zero_filled(users, [r.value for r in UserRole]),
        advocates_by_status=_zero_filled(advocates, [s.value for s in VerificationStatus]),
        matters_by_status=_zero_filled(matters, [s.value for s in MatterStatus]),
        sources_by_status=_zero_filled(sources, [s.value for s in IngestionStatus]),
        payments=PaymentTotals(count=count, gross=gross, refunded=refunded),
        advocates_pending=advocates.get(VerificationStatus.PENDING.value, 0)
        + advocates.get(VerificationStatus.IN_REVIEW.value, 0),
        reviews_pending=reviews_pending,
        emails_pending=email_counts.get(EmailStatus.PENDING.value, 0),
        emails_failed=email_counts.get(EmailStatus.FAILED.value, 0),
    )


# ---- matters ---------------------------------------------------------------------------------


@router.get("/matters", response_model=PaginatedAdminMatters, summary="All matters")
async def list_matters(
    _admin: AdminUser,
    db: DbSession,
    status: MatterStatus | None = None,
    limit: Limit = 25,
    offset: Offset = 0,
) -> PaginatedAdminMatters:
    consumer = aliased(User)
    advocate = aliased(User)
    conditions: list[ColumnElement[bool]] = []
    if status is not None:
        conditions.append(Matter.status == status)

    total = (
        await db.execute(select(func.count()).select_from(Matter).where(*conditions))
    ).scalar_one()
    rows = (
        await db.execute(
            select(Matter, consumer.display_name, advocate.display_name)
            .join(consumer, consumer.id == Matter.consumer_id)
            .join(AdvocateProfile, AdvocateProfile.id == Matter.advocate_profile_id)
            .join(advocate, advocate.id == AdvocateProfile.user_id)
            .where(*conditions)
            .order_by(Matter.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return PaginatedAdminMatters(
        items=[
            AdminMatterOut(
                id=m.id,
                title=m.title,
                service_type=m.service_type,
                status=m.status,
                quoted_fee=m.quoted_fee,
                consumer_name=consumer_name,
                advocate_name=advocate_name,
                created_at=m.created_at,
                updated_at=m.updated_at,
            )
            for m, consumer_name, advocate_name in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


# ---- advocates -------------------------------------------------------------------------------


@router.get(
    "/advocates",
    response_model=PaginatedAdminAdvocates,
    summary="All advocate profiles (any verification status)",
)
async def list_advocates(
    _admin: AdminUser,
    db: DbSession,
    status: VerificationStatus | None = None,
    limit: Limit = 25,
    offset: Offset = 0,
) -> PaginatedAdminAdvocates:
    conditions: list[ColumnElement[bool]] = []
    if status is not None:
        conditions.append(AdvocateProfile.verification_status == status)

    total = (
        await db.execute(select(func.count()).select_from(AdvocateProfile).where(*conditions))
    ).scalar_one()
    rows = (
        await db.execute(
            select(AdvocateProfile, User.display_name, User.email)
            .join(User, User.id == AdvocateProfile.user_id)
            .where(*conditions)
            .order_by(AdvocateProfile.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return PaginatedAdminAdvocates(
        items=[
            AdminAdvocateOut(
                **AdvocateProfileOut.model_validate(profile).model_dump(),
                display_name=name,
                email=email,
                created_at=profile.created_at,
            )
            for profile, name, email in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


# ---- high-risk query review -----------------------------------------------------------------


def _review_out(
    message: ChatMessage, owner_id: uuid.UUID | None, reply: ChatMessage | None
) -> QueryReviewOut:
    return QueryReviewOut(
        id=message.id,
        conversation_id=message.conversation_id,
        created_at=message.created_at,
        risk_level=message.risk_level or "",
        legal_category=message.legal_category,
        jurisdiction_scope=message.jurisdiction_scope,
        question=message.content,
        answer=reply.content if reply else None,
        answer_source_count=len(reply.sources or []) if reply else None,
        registered=owner_id is not None,
        reviewed_at=message.reviewed_at,
        review_note=message.review_note,
    )


@router.get(
    "/reviews", response_model=PaginatedQueryReviews, summary="High-risk chat queries to review"
)
async def list_reviews(
    _admin: AdminUser,
    db: DbSession,
    status: Literal["pending", "reviewed", "all"] = "pending",
    risk_level: Literal["HIGH", "CRITICAL"] | None = None,
    limit: Limit = 25,
    offset: Offset = 0,
) -> PaginatedQueryReviews:
    conditions: list[ColumnElement[bool]] = [
        ChatMessage.role == MessageRole.USER,
        ChatMessage.risk_level.in_((risk_level,) if risk_level else _HIGH_RISK),
    ]
    if status == "pending":
        conditions.append(ChatMessage.reviewed_at.is_(None))
    elif status == "reviewed":
        conditions.append(ChatMessage.reviewed_at.is_not(None))

    total = (
        await db.execute(select(func.count()).select_from(ChatMessage).where(*conditions))
    ).scalar_one()
    severity = case((ChatMessage.risk_level == "CRITICAL", 0), else_=1)
    rows = (
        await db.execute(
            select(ChatMessage, Conversation.user_id)
            .join(Conversation, Conversation.id == ChatMessage.conversation_id)
            .where(*conditions)
            # Worst first, then longest-waiting first; reviewed ones newest-reviewed first.
            .order_by(
                severity if status != "reviewed" else ChatMessage.reviewed_at.desc(),
                ChatMessage.created_at,
                ChatMessage.id,
            )
            .limit(limit)
            .offset(offset)
        )
    ).all()

    # The assistant's reply to each question: the first assistant message at or after it.
    answers: dict[uuid.UUID, list[ChatMessage]] = {}
    conversation_ids = {m.conversation_id for m, _ in rows}
    if conversation_ids:
        replies = (
            (
                await db.execute(
                    select(ChatMessage)
                    .where(
                        ChatMessage.conversation_id.in_(conversation_ids),
                        ChatMessage.role == MessageRole.ASSISTANT,
                    )
                    .order_by(ChatMessage.created_at, ChatMessage.id)
                )
            )
            .scalars()
            .all()
        )
        for reply in replies:
            answers.setdefault(reply.conversation_id, []).append(reply)

    items = [
        _review_out(
            message,
            owner_id,
            next(
                (
                    r
                    for r in answers.get(message.conversation_id, [])
                    if r.created_at >= message.created_at
                ),
                None,
            ),
        )
        for message, owner_id in rows
    ]
    return PaginatedQueryReviews(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/reviews/{message_id}/review",
    response_model=QueryReviewOut,
    summary="Mark a high-risk query as reviewed (or update the note)",
)
async def review_query(
    message_id: uuid.UUID, payload: ReviewRequest, admin: AdminUser, db: DbSession
) -> QueryReviewOut:
    message = await db.scalar(
        select(ChatMessage).where(
            ChatMessage.id == message_id,
            ChatMessage.role == MessageRole.USER,
            ChatMessage.risk_level.in_(_HIGH_RISK),
        )
    )
    if message is None:
        raise NotFoundError("That query isn't in the review queue.")
    if message.reviewed_at is None:
        message.reviewed_at = datetime.now(UTC)
        message.reviewed_by_id = admin.id
    message.review_note = payload.note
    await db.commit()

    owner_id = await db.scalar(
        select(Conversation.user_id).where(Conversation.id == message.conversation_id)
    )
    reply = await db.scalar(
        select(ChatMessage)
        .where(
            ChatMessage.conversation_id == message.conversation_id,
            ChatMessage.role == MessageRole.ASSISTANT,
            ChatMessage.created_at >= message.created_at,
        )
        .order_by(ChatMessage.created_at, ChatMessage.id)
        .limit(1)
    )
    return _review_out(message, owner_id, reply)
