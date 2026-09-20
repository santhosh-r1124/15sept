"""In-app notifications and email preferences (Phase 11).

Everything here is scoped to the caller: another user's notification is a 404, never a 403 (its
existence isn't the caller's business). Notifications are *created* by the routes that cause
them (matters, documents, payments, admin) via ``services/notifications.notify`` - there is no
endpoint to create one.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select, update

from app.api.deps import CurrentUser, DbSession
from app.core.errors import NotFoundError
from app.models.notification import Notification
from app.schemas.notification import (
    MarkedReadOut,
    NotificationOut,
    NotificationPreferences,
    PaginatedNotifications,
    UnreadCountOut,
)

router = APIRouter()

Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def _out(n: Notification) -> NotificationOut:
    return NotificationOut(
        id=n.id,
        kind=n.kind,
        title=n.title,
        body=n.body,
        link=n.link,
        read=n.read_at is not None,
        created_at=n.created_at,
    )


async def _unread(db: DbSession, user_id: uuid.UUID) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        )
    ).scalar_one()


@router.get("", response_model=PaginatedNotifications, summary="Your notifications, newest first")
async def list_notifications(
    user: CurrentUser,
    db: DbSession,
    unread_only: bool = False,
    limit: Limit = 25,
    offset: Offset = 0,
) -> PaginatedNotifications:
    conditions = [Notification.user_id == user.id]
    if unread_only:
        conditions.append(Notification.read_at.is_(None))
    total = (
        await db.execute(select(func.count()).select_from(Notification).where(*conditions))
    ).scalar_one()
    rows = (
        (
            await db.execute(
                select(Notification)
                .where(*conditions)
                .order_by(Notification.created_at.desc(), Notification.id)
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return PaginatedNotifications(
        items=[_out(n) for n in rows],
        total=total,
        unread=await _unread(db, user.id),
        limit=limit,
        offset=offset,
    )


@router.get("/unread-count", response_model=UnreadCountOut, summary="Number of unread (the bell)")
async def unread_count(user: CurrentUser, db: DbSession) -> UnreadCountOut:
    return UnreadCountOut(unread=await _unread(db, user.id))


@router.post("/read-all", response_model=MarkedReadOut, summary="Mark everything read")
async def mark_all_read(user: CurrentUser, db: DbSession) -> MarkedReadOut:
    result = await db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    await db.commit()
    return MarkedReadOut(updated=result.rowcount or 0)  # type: ignore[attr-defined]


@router.get("/preferences", response_model=NotificationPreferences, summary="Email preferences")
async def get_preferences(user: CurrentUser) -> NotificationPreferences:
    return NotificationPreferences(email_notifications=user.email_notifications)


@router.put("/preferences", response_model=NotificationPreferences, summary="Set preferences")
async def set_preferences(
    payload: NotificationPreferences, user: CurrentUser, db: DbSession
) -> NotificationPreferences:
    user.email_notifications = payload.email_notifications
    await db.commit()
    return NotificationPreferences(email_notifications=user.email_notifications)


@router.post("/{notification_id}/read", response_model=NotificationOut, summary="Mark one read")
async def mark_read(
    notification_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> NotificationOut:
    notification = await db.scalar(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == user.id
        )
    )
    if notification is None:
        raise NotFoundError("Notification not found.")
    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        await db.commit()
    return _out(notification)
