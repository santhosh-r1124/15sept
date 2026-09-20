"""Matters: booking an advocate, paying, scheduling, messaging, closing (Phase 8, FRD §9-10).

Lifecycle rules live in ``app.services.matters.lifecycle`` (pure, unit-tested); this module
only loads the matter, works out who the caller is *relative to it*, asks the state machine
whether the action is legal, then persists. Anyone who isn't a participant (or an admin, for
reads) gets a 404 rather than a 403 — a matter's existence isn't something to leak.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession, SettingsDep, require_roles
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.models.matter import Matter, MatterMessage, MatterStatus
from app.models.user import AdvocateProfile, User, UserRole, VerificationStatus
from app.schemas.matter import (
    AcceptMatterRequest,
    CancelMatterRequest,
    CreateMatterRequest,
    MatterAdvocateOut,
    MatterConsumerOut,
    MatterMessageOut,
    MatterOut,
    PaginatedMatters,
    PostMessageRequest,
    RejectMatterRequest,
    ScheduleMatterRequest,
)
from app.services.matters.lifecycle import Action, Actor, can_post_message, transition_for
from app.services.matters.pricing import default_quote
from app.services.payments import get_payment_provider

router = APIRouter()

ConsumerUser = Annotated[User, Depends(require_roles(UserRole.CONSUMER, UserRole.ENTERPRISE_USER))]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]
_ADMIN_ROLES = (UserRole.ADMIN, UserRole.LEGAL_ADMIN)

_MATTER_LOAD_OPTIONS = (
    selectinload(Matter.consumer),
    selectinload(Matter.advocate_profile).selectinload(AdvocateProfile.user),
)


def _to_out(matter: Matter) -> MatterOut:
    return MatterOut(
        id=matter.id,
        service_type=matter.service_type,
        consultation_minutes=matter.consultation_minutes,
        title=matter.title,
        requirement=matter.requirement,
        preferred_language=matter.preferred_language,
        status=matter.status,
        quoted_fee=matter.quoted_fee,
        decision_note=matter.decision_note,
        scheduled_at=matter.scheduled_at,
        paid_at=matter.paid_at,
        closed_at=matter.closed_at,
        created_at=matter.created_at,
        updated_at=matter.updated_at,
        advocate=MatterAdvocateOut(
            profile_id=matter.advocate_profile_id,
            display_name=matter.advocate_profile.user.display_name,
        ),
        consumer=MatterConsumerOut(
            display_name=matter.consumer.display_name, verified=matter.consumer.email_verified
        ),
    )


async def _load_matter(db: DbSession, matter_id: uuid.UUID) -> Matter:
    matter = await db.scalar(
        select(Matter)
        .options(*_MATTER_LOAD_OPTIONS)
        .where(Matter.id == matter_id)
        .execution_options(populate_existing=True)
    )
    if matter is None:
        raise NotFoundError("Matter not found.")
    return matter


def _actor_for(user: User, matter: Matter) -> Actor | None:
    if matter.consumer_id == user.id:
        return Actor.CONSUMER
    if matter.advocate_profile.user_id == user.id:
        return Actor.ADVOCATE
    return None


def _readable_by(user: User, matter: Matter) -> Actor | None:
    """The caller's role on this matter; admins may read any matter (returned as None
    actor but allowed), everyone else must be a participant."""
    actor = _actor_for(user, matter)
    if actor is None and user.role not in _ADMIN_ROLES:
        raise NotFoundError("Matter not found.")
    return actor


def _require_actor(user: User, matter: Matter) -> Actor:
    actor = _actor_for(user, matter)
    if actor is None:
        raise NotFoundError("Matter not found.")
    return actor


def _apply_action(matter: Matter, action: Action, actor: Actor) -> MatterStatus:
    target = transition_for(action, actor, matter.status, matter.service_type)
    if target is None:
        raise ConflictError(
            f"A {actor.value.lower()} can't {action.value.lower()} a matter that is "
            f"{matter.status.value.lower()}.",
            code="invalid_transition",
        )
    return target


async def _commit_and_reload(db: DbSession, matter: Matter) -> MatterOut:
    matter_id = matter.id
    await db.commit()
    return _to_out(await _load_matter(db, matter_id))


@router.post("", response_model=MatterOut, status_code=201, summary="Book an advocate")
async def create_matter(
    payload: CreateMatterRequest, user: ConsumerUser, db: DbSession
) -> MatterOut:
    profile = await db.scalar(
        select(AdvocateProfile).where(
            AdvocateProfile.id == payload.advocate_id,
            AdvocateProfile.verification_status == VerificationStatus.VERIFIED,
        )
    )
    if profile is None:
        raise NotFoundError("Advocate not found.")

    matter = Matter(
        consumer_id=user.id,
        advocate_profile_id=profile.id,
        service_type=payload.service_type,
        consultation_minutes=payload.consultation_minutes,
        title=payload.title,
        requirement=payload.requirement,
        preferred_language=payload.preferred_language,
        quoted_fee=default_quote(
            payload.service_type, payload.consultation_minutes, profile.consultation_fee
        ),
    )
    db.add(matter)
    await db.flush()
    return await _commit_and_reload(db, matter)


@router.get("", response_model=PaginatedMatters, summary="List your matters")
async def list_matters(
    user: CurrentUser,
    db: DbSession,
    status: MatterStatus | None = None,
    limit: Limit = 25,
    offset: Offset = 0,
) -> PaginatedMatters:
    scope: ColumnElement[bool]
    if user.role is UserRole.ADVOCATE:
        scope = Matter.advocate_profile_id.in_(
            select(AdvocateProfile.id).where(AdvocateProfile.user_id == user.id)
        )
    else:
        scope = Matter.consumer_id == user.id
    conditions: list[ColumnElement[bool]] = [scope]
    if status is not None:
        conditions.append(Matter.status == status)

    total = (
        await db.execute(select(func.count()).select_from(Matter).where(*conditions))
    ).scalar_one()
    rows = (
        (
            await db.execute(
                select(Matter)
                .options(*_MATTER_LOAD_OPTIONS)
                .where(*conditions)
                .order_by(Matter.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return PaginatedMatters(
        items=[_to_out(m) for m in rows], total=total, limit=limit, offset=offset
    )


@router.get("/{matter_id}", response_model=MatterOut, summary="Get a matter")
async def get_matter(matter_id: uuid.UUID, user: CurrentUser, db: DbSession) -> MatterOut:
    matter = await _load_matter(db, matter_id)
    _readable_by(user, matter)
    return _to_out(matter)


@router.post("/{matter_id}/accept", response_model=MatterOut, summary="Advocate accepts")
async def accept_matter(
    matter_id: uuid.UUID, payload: AcceptMatterRequest, user: CurrentUser, db: DbSession
) -> MatterOut:
    matter = await _load_matter(db, matter_id)
    actor = _require_actor(user, matter)
    target = _apply_action(matter, Action.ACCEPT, actor)
    fee = payload.quoted_fee if payload.quoted_fee is not None else matter.quoted_fee
    if fee is None:
        raise ValidationAppError(
            "A fee quote is required to accept this matter.",
            details=[{"field": "quoted_fee", "message": "This field is required."}],
        )
    matter.quoted_fee = fee
    matter.decision_note = payload.note
    matter.status = target
    return await _commit_and_reload(db, matter)


@router.post("/{matter_id}/reject", response_model=MatterOut, summary="Advocate rejects")
async def reject_matter(
    matter_id: uuid.UUID, payload: RejectMatterRequest, user: CurrentUser, db: DbSession
) -> MatterOut:
    matter = await _load_matter(db, matter_id)
    matter.status = _apply_action(matter, Action.REJECT, _require_actor(user, matter))
    matter.decision_note = payload.note
    return await _commit_and_reload(db, matter)


@router.post("/{matter_id}/cancel", response_model=MatterOut, summary="Cancel a matter")
async def cancel_matter(
    matter_id: uuid.UUID, payload: CancelMatterRequest, user: CurrentUser, db: DbSession
) -> MatterOut:
    matter = await _load_matter(db, matter_id)
    matter.status = _apply_action(matter, Action.CANCEL, _require_actor(user, matter))
    if payload.note:
        matter.decision_note = payload.note
    return await _commit_and_reload(db, matter)


@router.post("/{matter_id}/pay", response_model=MatterOut, summary="Pay for an accepted matter")
async def pay_matter(
    matter_id: uuid.UUID, user: CurrentUser, db: DbSession, settings: SettingsDep
) -> MatterOut:
    matter = await _load_matter(db, matter_id)
    target = _apply_action(matter, Action.PAY, _require_actor(user, matter))
    if matter.quoted_fee is None:  # ACCEPTED always carries a quote; belt and braces
        raise ConflictError("This matter has no fee quote to pay.", code="no_quote")

    provider = get_payment_provider(settings)
    result = await provider.charge(
        amount=matter.quoted_fee, description=matter.title, idempotency_key=str(matter.id)
    )
    matter.payment_reference = result.reference
    matter.paid_at = datetime.now(UTC)
    matter.status = target
    return await _commit_and_reload(db, matter)


@router.post("/{matter_id}/schedule", response_model=MatterOut, summary="Schedule a consultation")
async def schedule_matter(
    matter_id: uuid.UUID, payload: ScheduleMatterRequest, user: CurrentUser, db: DbSession
) -> MatterOut:
    matter = await _load_matter(db, matter_id)
    target = _apply_action(matter, Action.SCHEDULE, _require_actor(user, matter))
    when = payload.scheduled_at
    if when.tzinfo is None:
        raise ValidationAppError(
            "scheduled_at must include a timezone offset.",
            details=[{"field": "scheduled_at", "message": "Timezone required."}],
        )
    if when <= datetime.now(UTC):
        raise ValidationAppError(
            "scheduled_at must be in the future.",
            details=[{"field": "scheduled_at", "message": "Must be in the future."}],
        )
    matter.scheduled_at = when
    matter.status = target
    return await _commit_and_reload(db, matter)


@router.post("/{matter_id}/close", response_model=MatterOut, summary="Advocate closes the matter")
async def close_matter(matter_id: uuid.UUID, user: CurrentUser, db: DbSession) -> MatterOut:
    matter = await _load_matter(db, matter_id)
    matter.status = _apply_action(matter, Action.CLOSE, _require_actor(user, matter))
    matter.closed_at = datetime.now(UTC)
    return await _commit_and_reload(db, matter)


@router.get(
    "/{matter_id}/messages", response_model=list[MatterMessageOut], summary="Read the thread"
)
async def list_messages(
    matter_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> list[MatterMessageOut]:
    matter = await _load_matter(db, matter_id)
    _readable_by(user, matter)
    rows = (
        (
            await db.execute(
                select(MatterMessage)
                .where(MatterMessage.matter_id == matter.id)
                .order_by(MatterMessage.created_at, MatterMessage.id)
            )
        )
        .scalars()
        .all()
    )
    return [_message_out(m, matter) for m in rows]


@router.post(
    "/{matter_id}/messages",
    response_model=MatterMessageOut,
    status_code=201,
    summary="Post a message",
)
async def post_message(
    matter_id: uuid.UUID, payload: PostMessageRequest, user: CurrentUser, db: DbSession
) -> MatterMessageOut:
    matter = await _load_matter(db, matter_id)
    _require_actor(user, matter)
    if not can_post_message(matter.status):
        raise ConflictError(
            "This matter is closed; its message thread is read-only.", code="matter_closed"
        )
    message = MatterMessage(matter_id=matter.id, sender_id=user.id, body=payload.body)
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return _message_out(message, matter)


def _message_out(message: MatterMessage, matter: Matter) -> MatterMessageOut:
    role = "CONSUMER" if message.sender_id == matter.consumer_id else "ADVOCATE"
    return MatterMessageOut(
        id=message.id,
        matter_id=message.matter_id,
        sender_id=message.sender_id,
        sender_role=role,
        body=message.body,
        created_at=message.created_at,
    )
