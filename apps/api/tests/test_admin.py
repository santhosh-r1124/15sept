"""Integration tests for the admin user-management + advocate-verification endpoints.

There's no public admin-registration route (see app/scripts/create_admin.py), so
these tests seed an ADMIN user directly in the transactional DB session and mint
a real access token for it with the app's own settings.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core import security
from app.core.config import get_settings
from app.models.user import User, UserRole
from tests.conftest import unique_email


async def _admin_headers(db_txn_session: object, role: UserRole = UserRole.ADMIN) -> dict[str, str]:
    user = User(
        email=unique_email("admin"),
        hashed_password=security.hash_password("irrelevant-not-logged-in-with"),
        role=role,
        email_verified=True,
    )
    db_txn_session.add(user)  # type: ignore[attr-defined]
    await db_txn_session.commit()  # type: ignore[attr-defined]
    token = security.create_access_token(user_id=user.id, role=role.value, settings=get_settings())
    return {"Authorization": f"Bearer {token}"}


async def _register_advocate(client: AsyncClient) -> dict[str, object]:
    resp = await client.post(
        "/api/v1/advocates/register",
        json={
            "email": unique_email("advocate"),
            "password": "correct horse battery staple",
            "display_name": "Adv. Test",
            "state_code": "DL",
            "city": "Delhi",
        },
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.LEGAL_ADMIN])
async def test_admin_and_legal_admin_can_list_users(
    db_client: AsyncClient, db_txn_session: object, role: UserRole
) -> None:
    headers = await _admin_headers(db_txn_session, role)
    resp = await db_client.get("/api/v1/admin/users", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert body["limit"] == 25


async def test_consumer_cannot_access_admin_endpoints(db_client: AsyncClient) -> None:
    consumer = await db_client.post(
        "/api/v1/auth/register",
        json={"email": unique_email("consumer"), "password": "correct horse battery staple"},
    )
    headers = {"Authorization": f"Bearer {consumer.json()['access_token']}"}
    resp = await db_client.get("/api/v1/admin/users", headers=headers)
    assert resp.status_code == 403


async def test_admin_can_deactivate_a_user(db_client: AsyncClient, db_txn_session: object) -> None:
    headers = await _admin_headers(db_txn_session)
    register = await db_client.post(
        "/api/v1/auth/register",
        json={"email": unique_email("consumer"), "password": "correct horse battery staple"},
    )
    me = await db_client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {register.json()['access_token']}"},
    )
    user_id = me.json()["id"]

    resp = await db_client.patch(
        f"/api/v1/admin/users/{user_id}", json={"is_active": False}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    # A deactivated user can no longer log in.
    login = await db_client.post(
        "/api/v1/auth/login",
        json={"email": me.json()["email"], "password": "correct horse battery staple"},
    )
    assert login.status_code == 401
    assert login.json()["error"]["code"] == "account_inactive"


async def test_advocate_verification_workflow(
    db_client: AsyncClient, db_txn_session: object
) -> None:
    advocate_tokens = await _register_advocate(db_client)
    admin_headers = await _admin_headers(db_txn_session)

    pending = await db_client.get("/api/v1/admin/advocates/pending", headers=admin_headers)
    assert pending.status_code == 200
    profile_ids = [item["id"] for item in pending.json()["items"]]

    advocate_headers = {"Authorization": f"Bearer {advocate_tokens['access_token']}"}
    own_profile = await db_client.get("/api/v1/advocates/me", headers=advocate_headers)
    profile_id = own_profile.json()["id"]
    assert profile_id in profile_ids

    verify = await db_client.post(
        f"/api/v1/admin/advocates/{profile_id}/verify",
        json={"note": "Bar Council ID confirmed."},
        headers=admin_headers,
    )
    assert verify.status_code == 200
    assert verify.json()["verification_status"] == "VERIFIED"

    # Reflected back on the advocate's own profile view.
    refreshed = await db_client.get("/api/v1/advocates/me", headers=advocate_headers)
    assert refreshed.json()["verification_status"] == "VERIFIED"


async def test_advocate_rejection_requires_a_note(
    db_client: AsyncClient, db_txn_session: object
) -> None:
    advocate_tokens = await _register_advocate(db_client)
    admin_headers = await _admin_headers(db_txn_session)
    advocate_headers = {"Authorization": f"Bearer {advocate_tokens['access_token']}"}
    profile = (await db_client.get("/api/v1/advocates/me", headers=advocate_headers)).json()

    missing_note = await db_client.post(
        f"/api/v1/admin/advocates/{profile['id']}/reject", json={}, headers=admin_headers
    )
    assert missing_note.status_code == 422

    rejected = await db_client.post(
        f"/api/v1/admin/advocates/{profile['id']}/reject",
        json={"note": "Missing enrolment proof."},
        headers=admin_headers,
    )
    assert rejected.status_code == 200
    assert rejected.json()["verification_status"] == "REJECTED"
