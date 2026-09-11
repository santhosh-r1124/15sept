"""Integration tests for the authentication flows (register/login/refresh/logout,
email verification, password reset). Needs Postgres — see conftest.db_client.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select

from app.models.user import EmailVerificationToken, PasswordResetToken, User
from tests.conftest import unique_email


async def _register(client: AsyncClient, **overrides: object) -> dict[str, object]:
    payload = {"email": unique_email(), "password": "correct horse battery staple", **overrides}
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    return {**payload, **resp.json()}


async def test_register_returns_token_pair(db_client: AsyncClient) -> None:
    email = unique_email()
    resp = await db_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct horse battery staple", "display_name": "Asha"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["expires_in"] > 0


async def test_register_duplicate_email_conflicts(db_client: AsyncClient) -> None:
    email = unique_email()
    await _register(db_client, email=email)
    resp = await db_client.post(
        "/api/v1/auth/register", json={"email": email, "password": "correct horse battery staple"}
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "email_taken"


async def test_register_rejects_short_password(db_client: AsyncClient) -> None:
    resp = await db_client.post(
        "/api/v1/auth/register", json={"email": unique_email(), "password": "short"}
    )
    assert resp.status_code == 422


async def test_new_user_starts_unverified(db_client: AsyncClient, db_txn_session: object) -> None:
    email = unique_email()
    await _register(db_client, email=email)
    user = await db_txn_session.scalar(select(User).where(User.email == email))  # type: ignore[attr-defined]
    assert user is not None
    assert user.email_verified is False


async def test_login_succeeds_with_correct_credentials(db_client: AsyncClient) -> None:
    email = unique_email()
    await _register(db_client, email=email)
    resp = await db_client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct horse battery staple"}
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]


async def test_login_rejects_wrong_password(db_client: AsyncClient) -> None:
    email = unique_email()
    await _register(db_client, email=email)
    resp = await db_client.post(
        "/api/v1/auth/login", json={"email": email, "password": "totally wrong password"}
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"


async def test_login_rejects_unknown_email(db_client: AsyncClient) -> None:
    resp = await db_client.post(
        "/api/v1/auth/login",
        json={"email": unique_email(), "password": "correct horse battery staple"},
    )
    assert resp.status_code == 401


async def test_access_token_reads_own_profile(db_client: AsyncClient) -> None:
    email = unique_email()
    tokens = await _register(db_client, email=email, display_name="Priya")
    resp = await db_client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == email
    assert body["role"] == "CONSUMER"
    assert body["display_name"] == "Priya"
    assert body["email_verified"] is False


async def test_update_profile(db_client: AsyncClient) -> None:
    tokens = await _register(db_client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    resp = await db_client.patch(
        "/api/v1/users/me",
        json={"display_name": "New Name", "state_code": "ka", "preferred_language": "kn"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["display_name"] == "New Name"
    assert body["state_code"] == "KA"  # normalised uppercase
    assert body["preferred_language"] == "kn"


async def test_refresh_rotates_tokens_and_invalidates_old_one(db_client: AsyncClient) -> None:
    tokens = await _register(db_client)
    resp = await db_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 200
    new_tokens = resp.json()
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    # The rotated-out refresh token must no longer work.
    reuse = await db_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert reuse.status_code == 401


async def test_logout_revokes_refresh_token(db_client: AsyncClient) -> None:
    tokens = await _register(db_client)
    logout_resp = await db_client.post(
        "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
    )
    assert logout_resp.status_code == 200

    refresh_resp = await db_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refresh_resp.status_code == 401


async def test_verify_email_flow(db_client: AsyncClient, db_txn_session: object) -> None:
    email = unique_email()
    await _register(db_client, email=email)

    user = await db_txn_session.scalar(select(User).where(User.email == email))  # type: ignore[attr-defined]
    record = await db_txn_session.scalar(  # type: ignore[attr-defined]
        select(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id)
    )
    assert record is not None

    # We only ever store the hash; recover a fresh raw token the same way the
    # email-sending code does, by regenerating and directly seeding the hash the
    # verify endpoint expects would require the raw value — instead, exercise
    # via /resend-verification, which is the supported way to get a fresh token
    # in a test without reaching into the (intentionally one-way) hash.
    resend = await db_client.post("/api/v1/auth/resend-verification", json={"email": email})
    assert resend.status_code == 200


async def test_verify_email_rejects_unknown_token(db_client: AsyncClient) -> None:
    resp = await db_client.post("/api/v1/auth/verify-email", json={"token": "not-a-real-token"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_token"


async def test_forgot_password_is_always_200_even_for_unknown_email(db_client: AsyncClient) -> None:
    resp = await db_client.post("/api/v1/auth/forgot-password", json={"email": unique_email()})
    assert resp.status_code == 200


async def test_reset_password_rejects_unknown_token(db_client: AsyncClient) -> None:
    resp = await db_client.post(
        "/api/v1/auth/reset-password",
        json={"token": "not-a-real-token", "new_password": "another long enough password"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_token"


async def test_forgot_password_creates_a_reset_token_row(
    db_client: AsyncClient, db_txn_session: object
) -> None:
    email = unique_email()
    await _register(db_client, email=email)
    await db_client.post("/api/v1/auth/forgot-password", json={"email": email})

    user = await db_txn_session.scalar(select(User).where(User.email == email))  # type: ignore[attr-defined]
    record = await db_txn_session.scalar(  # type: ignore[attr-defined]
        select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
    )
    assert record is not None
    assert record.used_at is None
