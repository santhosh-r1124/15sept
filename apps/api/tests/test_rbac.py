"""Auth-gate behaviour that never needs a real database.

``get_current_user`` rejects a missing/malformed/invalid-signature token before
it ever touches the DB, so these run with the plain (DB-less) ``client`` fixture.
"""

from __future__ import annotations

import jwt
from httpx import AsyncClient

from app.core.config import get_settings

PROTECTED_ENDPOINTS = [
    ("GET", "/api/v1/users/me"),
    ("GET", "/api/v1/advocates/me"),
    ("GET", "/api/v1/admin/users"),
]


async def test_protected_endpoints_require_a_token(client: AsyncClient) -> None:
    for method, path in PROTECTED_ENDPOINTS:
        resp = await client.request(method, path)
        assert resp.status_code == 401, path
        assert resp.json()["error"]["code"] == "unauthorized"


async def test_protected_endpoint_rejects_garbage_token(client: AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/users/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert resp.status_code == 401


async def test_protected_endpoint_rejects_token_signed_with_wrong_secret(
    client: AsyncClient,
) -> None:
    bogus = jwt.encode(
        {"sub": "11111111-1111-1111-1111-111111111111", "role": "ADMIN", "typ": "access"},
        "not-the-real-secret-but-still-32-bytes-long",
        algorithm="HS256",
    )
    resp = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {bogus}"})
    assert resp.status_code == 401


async def test_protected_endpoint_rejects_refresh_token_used_as_access_token(
    client: AsyncClient,
) -> None:
    settings = get_settings()
    refresh_shaped = jwt.encode(
        {
            "sub": "11111111-1111-1111-1111-111111111111",
            "role": "CONSUMER",
            "typ": "refresh",
            "jti": "x",
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    resp = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {refresh_shaped}"}
    )
    assert resp.status_code == 401


async def test_missing_bearer_scheme_is_rejected(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/users/me", headers={"Authorization": "Token abc"})
    assert resp.status_code == 401
