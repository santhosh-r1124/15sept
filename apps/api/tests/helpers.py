"""Shared integration-test setup: users of each kind with ready-to-use auth headers.

All of these run through the real HTTP API (register endpoints) and then, where a state has
no public endpoint (verifying an advocate, creating an admin), set it directly on the
shared transactional session — the same approach as test_advocate_search.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select

from app.core import security
from app.core.config import get_settings
from app.models.user import AdvocateProfile, User, UserRole, VerificationStatus
from tests.conftest import unique_email

PASSWORD = "correct horse battery staple"


@dataclass(frozen=True)
class Account:
    headers: dict[str, str]
    user_id: str
    profile_id: str | None = None  # AdvocateProfile.id, advocates only


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def register_consumer(client: AsyncClient, **overrides: Any) -> Account:
    payload = {"email": unique_email("consumer"), "password": PASSWORD, **overrides}
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    headers = _bearer(resp.json()["access_token"])
    me = await client.get("/api/v1/users/me", headers=headers)
    return Account(headers=headers, user_id=me.json()["id"])


async def register_advocate(
    client: AsyncClient, session: Any, *, verified: bool = True, **overrides: Any
) -> Account:
    payload = {
        "email": unique_email("advocate"),
        "password": PASSWORD,
        "display_name": "Adv. Kavya Rao",
        "practice_areas": ["IT_LAW", "CONTRACT_LAW"],
        "state_code": "KA",
        "city": "Bengaluru",
        "languages": ["en", "kn"],
        "consultation_fee": "1200.00",
        "experience_years": 6,
        **overrides,
    }
    resp = await client.post("/api/v1/advocates/register", json=payload)
    assert resp.status_code == 201, resp.text
    headers = _bearer(resp.json()["access_token"])
    profile = await session.scalar(
        select(AdvocateProfile).join(User).where(User.email == payload["email"])
    )
    assert profile is not None
    if verified:
        profile.verification_status = VerificationStatus.VERIFIED
        await session.commit()
    return Account(headers=headers, user_id=str(profile.user_id), profile_id=str(profile.id))


async def make_admin(session: Any, role: UserRole = UserRole.ADMIN) -> Account:
    user = User(
        email=unique_email("admin"),
        hashed_password=security.hash_password("irrelevant-not-logged-in-with"),
        role=role,
        email_verified=True,
    )
    session.add(user)
    await session.flush()
    token = security.create_access_token(user_id=user.id, role=role.value, settings=get_settings())
    return Account(headers=_bearer(token), user_id=str(user.id))


def future_iso(days: int = 2) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


async def book_matter(
    client: AsyncClient, consumer: Account, advocate: Account, **overrides: Any
) -> dict[str, Any]:
    payload = {
        "advocate_id": advocate.profile_id,
        "service_type": "CONSULTATION",
        "consultation_minutes": 60,
        "title": "Rental agreement review",
        "requirement": "Review my rental agreement before I sign.",
        **overrides,
    }
    resp = await client.post("/api/v1/matters", json=payload, headers=consumer.headers)
    assert resp.status_code == 201, resp.text
    return dict(resp.json())


async def advance_matter(
    client: AsyncClient,
    matter: dict[str, Any],
    consumer: Account,
    advocate: Account,
    to: str,
    *,
    quote: str | None = None,
) -> dict[str, Any]:
    """Drive a REQUESTED matter to ``to``: ACCEPTED, PAID, SCHEDULED (consultations) or CLOSED."""
    mid = matter["id"]
    steps: list[tuple[str, Account, dict[str, Any]]] = [
        ("accept", advocate, {"quoted_fee": quote} if quote else {}),
        ("pay", consumer, {}),
        ("schedule", advocate, {"scheduled_at": future_iso()}),
        ("close", advocate, {}),
    ]
    reached = {"ACCEPTED": 1, "PAID": 2, "SCHEDULED": 3, "CLOSED": 4}[to]
    latest = matter
    for action, who, body in steps[:reached]:
        if action == "schedule" and matter["service_type"] != "CONSULTATION":
            continue  # document services skip scheduling
        resp = await client.post(f"/api/v1/matters/{mid}/{action}", json=body, headers=who.headers)
        assert resp.status_code == 200, f"{action}: {resp.text}"
        latest = resp.json()
    return dict(latest)
