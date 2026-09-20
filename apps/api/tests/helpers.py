"""Shared integration-test setup: users of each kind with ready-to-use auth headers.

All of these run through the real HTTP API (register endpoints) and then, where a state has
no public endpoint (verifying an advocate, creating an admin), set it directly on the
shared transactional session — the same approach as test_advocate_search.py.
"""

from __future__ import annotations

from dataclasses import dataclass
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
