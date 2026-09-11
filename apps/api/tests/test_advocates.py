"""Integration tests for advocate registration and self-service profile."""

from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import unique_email


async def _register_advocate(client: AsyncClient, **overrides: object) -> dict[str, object]:
    payload = {
        "email": unique_email("advocate"),
        "password": "correct horse battery staple",
        "display_name": "Adv. Kavya Rao",
        "practice_areas": ["IT_LAW", "CONTRACT_LAW"],
        "state_code": "ka",
        "city": "Bengaluru",
        "languages": ["en", "kn"],
        "consultation_fee": "1500.00",
        "experience_years": 6,
        **overrides,
    }
    resp = await client.post("/api/v1/advocates/register", json=payload)
    assert resp.status_code == 201, resp.text
    return {**payload, **resp.json()}


async def test_advocate_register_returns_tokens(db_client: AsyncClient) -> None:
    tokens = await _register_advocate(db_client)
    assert tokens["access_token"]
    assert tokens["refresh_token"]


async def test_advocate_can_read_own_profile(db_client: AsyncClient) -> None:
    tokens = await _register_advocate(db_client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    resp = await db_client.get("/api/v1/advocates/me", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["state_code"] == "KA"
    assert body["city"] == "Bengaluru"
    assert body["verification_status"] == "PENDING"
    assert set(body["practice_areas"]) == {"IT_LAW", "CONTRACT_LAW"}


async def test_advocate_can_update_own_profile(db_client: AsyncClient) -> None:
    tokens = await _register_advocate(db_client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    resp = await db_client.patch(
        "/api/v1/advocates/me",
        json={"consultation_fee": "2000.00", "bio": "Ten years in IT & data protection law."},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["consultation_fee"] == "2000.00"
    assert body["bio"].startswith("Ten years")


async def test_advocate_endpoints_reject_consumer_accounts(db_client: AsyncClient) -> None:
    consumer = await db_client.post(
        "/api/v1/auth/register",
        json={"email": unique_email("consumer"), "password": "correct horse battery staple"},
    )
    headers = {"Authorization": f"Bearer {consumer.json()['access_token']}"}
    resp = await db_client.get("/api/v1/advocates/me", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


async def test_advocate_register_duplicate_email_conflicts(db_client: AsyncClient) -> None:
    email = unique_email("advocate")
    await _register_advocate(db_client, email=email)
    resp = await db_client.post(
        "/api/v1/advocates/register",
        json={
            "email": email,
            "password": "correct horse battery staple",
            "display_name": "Someone Else",
            "state_code": "MH",
            "city": "Mumbai",
        },
    )
    assert resp.status_code == 409
