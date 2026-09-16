"""Integration tests for public advocate discovery (Phase 7). Needs Postgres
— see conftest.db_client. There's no public self-verification endpoint, so
these seed a registered advocate via HTTP then flip ``verification_status``
directly on the shared transactional session (same pattern as
test_legal_sources.py's admin-user seeding).
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select

from app.models.user import AdvocateProfile, User, VerificationStatus
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


async def _register_and_verify(
    db_client: AsyncClient, db_txn_session: object, **overrides: object
) -> AdvocateProfile:
    payload = await _register_advocate(db_client, **overrides)
    profile = await db_txn_session.scalar(  # type: ignore[attr-defined]
        select(AdvocateProfile).join(User).where(User.email == payload["email"])
    )
    assert profile is not None
    profile.verification_status = VerificationStatus.VERIFIED
    await db_txn_session.commit()  # type: ignore[attr-defined]
    return profile


async def test_search_excludes_unverified_advocates(db_client: AsyncClient) -> None:
    await _register_advocate(db_client)  # left PENDING — never verified
    resp = await db_client.get("/api/v1/advocates")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


async def test_search_returns_verified_advocates(
    db_client: AsyncClient, db_txn_session: object
) -> None:
    await _register_and_verify(db_client, db_txn_session)
    resp = await db_client.get("/api/v1/advocates")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    entry = body["items"][0]
    assert entry["display_name"] == "Adv. Kavya Rao"
    assert entry["state_code"] == "KA"
    assert "verification_note" not in entry  # internal field, never public


async def test_search_filters_by_practice_area(
    db_client: AsyncClient, db_txn_session: object
) -> None:
    await _register_and_verify(
        db_client, db_txn_session, practice_areas=["FAMILY_LAW"], display_name="Family Advocate"
    )
    await _register_and_verify(
        db_client, db_txn_session, practice_areas=["IT_LAW"], display_name="IT Advocate"
    )

    resp = await db_client.get("/api/v1/advocates", params={"practice_area": "FAMILY_LAW"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["display_name"] == "Family Advocate"


async def test_search_filters_by_state_and_city(
    db_client: AsyncClient, db_txn_session: object
) -> None:
    await _register_and_verify(
        db_client, db_txn_session, state_code="mh", city="Pune", display_name="Pune Advocate"
    )
    await _register_and_verify(
        db_client, db_txn_session, state_code="ka", city="Bengaluru", display_name="Blr Advocate"
    )

    resp = await db_client.get("/api/v1/advocates", params={"state_code": "mh"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["display_name"] == "Pune Advocate"

    resp = await db_client.get("/api/v1/advocates", params={"city": "pune"})
    assert resp.status_code == 200
    assert resp.json()["items"][0]["display_name"] == "Pune Advocate"


async def test_search_filters_by_language(db_client: AsyncClient, db_txn_session: object) -> None:
    await _register_and_verify(
        db_client, db_txn_session, languages=["hi", "en"], display_name="Hindi Advocate"
    )
    await _register_and_verify(
        db_client, db_txn_session, languages=["ta"], display_name="Tamil Advocate"
    )

    resp = await db_client.get("/api/v1/advocates", params={"language": "hi"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["display_name"] == "Hindi Advocate"


async def test_search_filters_by_experience_and_fee(
    db_client: AsyncClient, db_txn_session: object
) -> None:
    await _register_and_verify(
        db_client,
        db_txn_session,
        experience_years=2,
        consultation_fee="500.00",
        display_name="Junior Advocate",
    )
    await _register_and_verify(
        db_client,
        db_txn_session,
        experience_years=15,
        consultation_fee="5000.00",
        display_name="Senior Advocate",
    )

    resp = await db_client.get("/api/v1/advocates", params={"min_experience_years": 10})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["display_name"] == "Senior Advocate"

    resp = await db_client.get("/api/v1/advocates", params={"max_consultation_fee": "1000.00"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["display_name"] == "Junior Advocate"


async def test_search_orders_most_experienced_first(
    db_client: AsyncClient, db_txn_session: object
) -> None:
    await _register_and_verify(
        db_client, db_txn_session, experience_years=2, display_name="Junior Advocate"
    )
    await _register_and_verify(
        db_client, db_txn_session, experience_years=15, display_name="Senior Advocate"
    )

    resp = await db_client.get("/api/v1/advocates")
    assert resp.status_code == 200
    names = [item["display_name"] for item in resp.json()["items"]]
    assert names == ["Senior Advocate", "Junior Advocate"]


async def test_search_pagination(db_client: AsyncClient, db_txn_session: object) -> None:
    for i in range(3):
        await _register_and_verify(db_client, db_txn_session, display_name=f"Advocate {i}")

    resp = await db_client.get("/api/v1/advocates", params={"limit": 2, "offset": 0})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2


async def test_get_verified_advocate_by_id(db_client: AsyncClient, db_txn_session: object) -> None:
    profile = await _register_and_verify(db_client, db_txn_session)
    resp = await db_client.get(f"/api/v1/advocates/{profile.id}")
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Adv. Kavya Rao"


async def test_get_unverified_advocate_by_id_is_404(db_client: AsyncClient) -> None:
    created = await _register_advocate(db_client)
    # No profile id returned from register (just tokens) — fetch it via /me.
    headers = {"Authorization": f"Bearer {created['access_token']}"}
    me = await db_client.get("/api/v1/advocates/me", headers=headers)
    profile_id = me.json()["id"]

    resp = await db_client.get(f"/api/v1/advocates/{profile_id}")
    assert resp.status_code == 404


async def test_get_unknown_advocate_id_is_404(db_client: AsyncClient) -> None:
    resp = await db_client.get("/api/v1/advocates/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
