"""Integration tests for the advocate dashboard + earnings (Phase 9). Needs Postgres."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from tests.helpers import (
    Account,
    advance_matter,
    book_matter,
    register_advocate,
    register_consumer,
)

DASHBOARD = "/api/v1/advocates/me/dashboard"
EARNINGS = "/api/v1/advocates/me/earnings"


async def _matter_at(
    client: AsyncClient,
    advocate: Account,
    stage: str | None,
    *,
    title: str,
    quote: str | None = "1000.00",
    **booking: Any,
) -> tuple[Account, dict[str, Any]]:
    consumer = await register_consumer(client)
    matter = await book_matter(client, consumer, advocate, title=title, **booking)
    if stage:
        matter = await advance_matter(client, matter, consumer, advocate, stage, quote=quote)
    return consumer, matter


async def test_dashboard_counts_each_bucket_and_lists_upcoming_appointments(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    advocate = await register_advocate(db_client, db_txn_session)
    await _matter_at(db_client, advocate, None, title="new request")
    await _matter_at(db_client, advocate, "ACCEPTED", title="awaiting payment")
    await _matter_at(db_client, advocate, "PAID", title="to schedule")
    await _matter_at(db_client, advocate, "SCHEDULED", title="scheduled")
    await _matter_at(db_client, advocate, "CLOSED", title="finished", quote="2000.00")

    body = (await db_client.get(DASHBOARD, headers=advocate.headers)).json()

    assert body["new_requests"] == 1
    assert body["awaiting_payment"] == 1
    assert body["to_schedule"] == 1
    assert [a["title"] for a in body["upcoming_appointments"]] == ["scheduled"]
    assert body["upcoming_appointments"][0]["consultation_minutes"] == 60
    assert body["earnings"]["gross_earned"] == "2000.00"
    assert body["earnings"]["pending"] == "2000.00"  # the paid + the scheduled one


async def test_dashboard_only_counts_this_advocates_matters(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    mine = await register_advocate(db_client, db_txn_session)
    theirs = await register_advocate(db_client, db_txn_session)
    await _matter_at(db_client, theirs, None, title="someone else's")
    await _matter_at(db_client, theirs, "CLOSED", title="someone else's money")

    body = (await db_client.get(DASHBOARD, headers=mine.headers)).json()

    assert body["new_requests"] == 0
    assert body["earnings"]["gross_earned"] == "0.00"


async def test_awaiting_reply_tracks_who_spoke_last(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    advocate = await register_advocate(db_client, db_txn_session)
    consumer, matter = await _matter_at(db_client, advocate, None, title="chatty")
    url = f"/api/v1/matters/{matter['id']}/messages"

    async def awaiting() -> int:
        return (await db_client.get(DASHBOARD, headers=advocate.headers)).json()["awaiting_reply"]

    assert await awaiting() == 0  # no messages yet
    await db_client.post(url, json={"body": "Hello?"}, headers=consumer.headers)
    assert await awaiting() == 1  # the client spoke last
    await db_client.post(url, json={"body": "Hi, one moment."}, headers=advocate.headers)
    assert await awaiting() == 0  # answered
    await db_client.post(url, json={"body": "Thanks!"}, headers=consumer.headers)
    assert await awaiting() == 1
    await db_client.post(
        f"/api/v1/matters/{matter['id']}/cancel", json={}, headers=consumer.headers
    )
    assert await awaiting() == 0  # ended matters never need a reply


async def test_open_document_requests_count_until_fulfilled(
    db_client: AsyncClient,
    db_txn_session: Any,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    get_settings.cache_clear()
    advocate = await register_advocate(db_client, db_txn_session)
    consumer, matter = await _matter_at(db_client, advocate, "ACCEPTED", title="docs")
    base = f"/api/v1/matters/{matter['id']}"

    created = await db_client.post(
        f"{base}/document-requests", json={"description": "ID proof"}, headers=advocate.headers
    )
    body = (await db_client.get(DASHBOARD, headers=advocate.headers)).json()
    assert body["open_document_requests"] == 1

    await db_client.post(
        f"{base}/files",
        files={"file": ("id.pdf", b"%PDF-1.4 x", "application/pdf")},
        data={"request_id": created.json()["id"]},
        headers=consumer.headers,
    )
    body = (await db_client.get(DASHBOARD, headers=advocate.headers)).json()
    assert body["open_document_requests"] == 0
    get_settings.cache_clear()


async def test_earnings_line_items_and_platform_fee(
    db_client: AsyncClient, db_txn_session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PLATFORM_FEE_PERCENT", "10")
    get_settings.cache_clear()
    advocate = await register_advocate(db_client, db_txn_session)
    await _matter_at(db_client, advocate, "CLOSED", title="done", quote="1500.00")
    await _matter_at(db_client, advocate, "PAID", title="in progress", quote="700.00")
    await _matter_at(db_client, advocate, "ACCEPTED", title="unpaid", quote="999.00")

    body = (await db_client.get(EARNINGS, headers=advocate.headers)).json()

    summary = body["summary"]
    assert summary["gross_earned"] == "1500.00"
    assert summary["platform_fee_percent"] == "10"
    assert summary["platform_fee"] == "150.00"
    assert summary["net_earned"] == "1350.00"
    assert summary["pending"] == "700.00"
    assert {(i["title"], i["status"]) for i in body["items"]} == {
        ("done", "CLOSED"),
        ("in progress", "PAID"),
    }  # unpaid matters are not earnings
    get_settings.cache_clear()


async def test_portal_endpoints_are_advocate_only(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer = await register_consumer(db_client)
    for url in (DASHBOARD, EARNINGS):
        assert (await db_client.get(url)).status_code == 401
        assert (await db_client.get(url, headers=consumer.headers)).status_code == 403
