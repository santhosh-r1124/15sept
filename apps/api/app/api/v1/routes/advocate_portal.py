"""Advocate operating dashboard + earnings (Phase 9, FRD 10). Mounted at ``/advocates/me``.

Everything is scoped to the calling advocate's own matters. Actions on those matters (accept,
schedule, message, ...) are the existing ``/matters`` endpoints - this module is read-only
summaries for the portal's landing page and earnings screen.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, SettingsDep, require_roles
from app.core.errors import NotFoundError
from app.models.matter import Matter, MatterMessage, MatterServiceType, MatterStatus
from app.models.matter_document import MatterDocumentRequest, MatterDocumentRequestStatus
from app.models.payment import Payment
from app.models.user import AdvocateProfile, User, UserRole
from app.schemas.advocate_portal import (
    AdvocateDashboardOut,
    EarningsLineItemOut,
    EarningsOut,
    EarningsSummaryOut,
    UpcomingAppointmentOut,
)
from app.services.matters.earnings import (
    EARNED_STATUSES,
    PENDING_STATUSES,
    summarize_earnings,
)
from app.services.matters.lifecycle import TERMINAL_STATUSES

router = APIRouter()

AdvocateUser = Annotated[User, Depends(require_roles(UserRole.ADVOCATE))]
_UPCOMING_LIMIT = 5


async def _profile_id(db: DbSession, user: User) -> uuid.UUID:
    profile_id = await db.scalar(
        select(AdvocateProfile.id).where(AdvocateProfile.user_id == user.id)
    )
    if profile_id is None:
        raise NotFoundError("Advocate profile not found.")
    return profile_id


def _summary_out(
    rows: list[tuple[MatterStatus, Decimal | None, Decimal]], fee_percent: Decimal
) -> EarningsSummaryOut:
    summary = summarize_earnings(rows, fee_percent)
    return EarningsSummaryOut(
        gross_earned=summary.gross_earned,
        platform_fee_percent=fee_percent,
        platform_fee=summary.platform_fee,
        net_earned=summary.net_earned,
        pending=summary.pending,
    )


@router.get("/dashboard", response_model=AdvocateDashboardOut, summary="Dashboard summary")
async def dashboard(
    user: AdvocateUser, db: DbSession, settings: SettingsDep
) -> AdvocateDashboardOut:
    pid = await _profile_id(db, user)
    mine = Matter.advocate_profile_id == pid
    open_matter = Matter.status.not_in(TERMINAL_STATUSES)

    status_rows = (
        await db.execute(select(Matter.status, func.count()).where(mine).group_by(Matter.status))
    ).all()
    counts: dict[MatterStatus, int] = {row[0]: row[1] for row in status_rows}
    to_schedule = (
        await db.execute(
            select(func.count())
            .select_from(Matter)
            .where(
                mine,
                Matter.status == MatterStatus.PAID,
                Matter.service_type == MatterServiceType.CONSULTATION,
            )
        )
    ).scalar_one()
    open_requests = (
        await db.execute(
            select(func.count())
            .select_from(MatterDocumentRequest)
            .join(Matter, Matter.id == MatterDocumentRequest.matter_id)
            .where(
                mine, open_matter, MatterDocumentRequest.status == MatterDocumentRequestStatus.OPEN
            )
        )
    ).scalar_one()

    # Latest message per matter; a matter "awaits a reply" when that message is the client's.
    latest = (
        select(MatterMessage.matter_id, MatterMessage.sender_id)
        .where(MatterMessage.matter_id.in_(select(Matter.id).where(mine)))
        .distinct(MatterMessage.matter_id)
        .order_by(MatterMessage.matter_id, MatterMessage.created_at.desc(), MatterMessage.id.desc())
        .subquery()
    )
    awaiting_reply = (
        await db.execute(
            select(func.count())
            .select_from(Matter)
            .join(latest, latest.c.matter_id == Matter.id)
            .where(mine, open_matter, latest.c.sender_id == Matter.consumer_id)
        )
    ).scalar_one()

    upcoming = (
        (
            await db.execute(
                select(Matter)
                .options(selectinload(Matter.consumer))
                .where(
                    mine,
                    Matter.status == MatterStatus.SCHEDULED,
                    Matter.scheduled_at >= datetime.now(UTC),
                )
                .order_by(Matter.scheduled_at)
                .limit(_UPCOMING_LIMIT)
            )
        )
        .scalars()
        .all()
    )

    money_rows = (
        await db.execute(
            select(Matter.status, Matter.quoted_fee, func.coalesce(Payment.refunded_amount, 0))
            .outerjoin(Payment, Payment.matter_id == Matter.id)
            .where(mine, Matter.status.in_(EARNED_STATUSES + PENDING_STATUSES))
        )
    ).all()

    return AdvocateDashboardOut(
        new_requests=counts.get(MatterStatus.REQUESTED, 0),
        awaiting_payment=counts.get(MatterStatus.ACCEPTED, 0),
        to_schedule=to_schedule,
        open_document_requests=open_requests,
        awaiting_reply=awaiting_reply,
        upcoming_appointments=[
            UpcomingAppointmentOut(
                matter_id=m.id,
                title=m.title,
                scheduled_at=m.scheduled_at,
                consultation_minutes=m.consultation_minutes,
                client_name=m.consumer.display_name,
            )
            for m in upcoming
        ],
        earnings=_summary_out(
            [(s, a, Decimal(r)) for s, a, r in money_rows], settings.platform_fee_percent
        ),
    )


@router.get("/earnings", response_model=EarningsOut, summary="Earnings summary and line items")
async def earnings(user: AdvocateUser, db: DbSession, settings: SettingsDep) -> EarningsOut:
    pid = await _profile_id(db, user)
    rows = (
        await db.execute(
            select(Matter, func.coalesce(Payment.refunded_amount, 0))
            .outerjoin(Payment, Payment.matter_id == Matter.id)
            .where(
                Matter.advocate_profile_id == pid,
                Matter.status.in_(EARNED_STATUSES + PENDING_STATUSES),
                Matter.quoted_fee.is_not(None),
            )
            .order_by(Matter.paid_at.desc().nulls_last(), Matter.created_at.desc())
        )
    ).all()
    return EarningsOut(
        summary=_summary_out(
            [(m.status, m.quoted_fee, Decimal(r)) for m, r in rows],
            settings.platform_fee_percent,
        ),
        items=[
            EarningsLineItemOut(
                matter_id=m.id,
                title=m.title,
                amount=m.quoted_fee,
                refunded=Decimal(r),
                status=m.status,
                paid_at=m.paid_at,
                closed_at=m.closed_at,
            )
            for m, r in rows
        ],
    )
