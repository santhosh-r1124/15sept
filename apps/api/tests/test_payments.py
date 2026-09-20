"""Integration tests for payments, invoices and refunds (Phase 10). Needs Postgres."""

from __future__ import annotations

import re
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.errors import ServiceUnavailableError
from app.models.payment import Invoice, Payment, Refund
from app.models.user import UserRole
from app.services.payments import MockPaymentProvider
from tests.helpers import (
    Account,
    advance_matter,
    book_matter,
    make_admin,
    register_advocate,
    register_consumer,
)

PAYMENTS = "/api/v1/payments"
ADMIN_PAYMENTS = "/api/v1/admin/payments"
MATTERS = "/api/v1/matters"


async def _paid(
    client: AsyncClient,
    session: Any,
    *,
    stage: str = "PAID",
    quote: str | None = None,
    advocate: Account | None = None,
    **booking: Any,
) -> tuple[Account, Account, dict[str, Any]]:
    consumer = await register_consumer(client)
    advocate = advocate or await register_advocate(client, session)
    matter = await book_matter(client, consumer, advocate, **booking)
    matter = await advance_matter(client, matter, consumer, advocate, stage, quote=quote)
    return consumer, advocate, matter


async def _payment(client: AsyncClient, who: Account, matter_id: str) -> dict[str, Any]:
    resp = await client.get(f"{PAYMENTS}/matters/{matter_id}", headers=who.headers)
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


# --- taking a payment ------------------------------------------------------------------


async def test_paying_records_a_payment_and_issues_an_invoice(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer, advocate, matter = await _paid(db_client, db_txn_session, consultation_minutes=30)

    body = await _payment(db_client, consumer, matter["id"])

    assert body["payment"]["amount"] == "600.00"  # 1200/hr, 30 minutes
    assert body["payment"]["status"] == "SUCCEEDED"
    assert body["payment"]["refunded_amount"] == "0.00"
    assert body["payment"]["provider"] == "mock"
    assert re.fullmatch(r"INV-\d{4}-\d{6}", body["invoice"]["invoice_number"])
    assert body["invoice"]["description"] == "Rental agreement review"
    assert body["invoice"]["advocate_name"] == "Adv. Kavya Rao"
    # The advocate sees the same record.
    assert (await _payment(db_client, advocate, matter["id"]))["invoice"]["id"] == body["invoice"][
        "id"
    ]


async def test_a_matter_is_charged_exactly_once(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer, _advocate, matter = await _paid(db_client, db_txn_session)

    again = await db_client.post(f"{MATTERS}/{matter['id']}/pay", json={}, headers=consumer.headers)

    assert again.status_code == 409
    payments = (
        await db_txn_session.execute(select(func.count()).select_from(Payment))
    ).scalar_one()
    invoices = (
        await db_txn_session.execute(select(func.count()).select_from(Invoice))
    ).scalar_one()
    assert (payments, invoices) == (1, 1)


async def test_an_unpaid_matter_has_no_payment(db_client: AsyncClient, db_txn_session: Any) -> None:
    consumer, _advocate, matter = await _paid(db_client, db_txn_session, stage="ACCEPTED")
    resp = await db_client.get(f"{PAYMENTS}/matters/{matter['id']}", headers=consumer.headers)
    assert resp.status_code == 404


async def test_invoice_numbers_are_unique_and_increase(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    numbers = []
    for _ in range(3):
        consumer, _adv, matter = await _paid(db_client, db_txn_session)
        numbers.append(
            (await _payment(db_client, consumer, matter["id"]))["invoice"]["invoice_number"]
        )
    assert len(set(numbers)) == 3
    assert numbers == sorted(numbers)


async def test_invoice_html_is_printable_escaped_and_locked_down(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer, _advocate, matter = await _paid(
        db_client, db_txn_session, title='<script>alert("x")</script> lease'
    )
    invoice = (await _payment(db_client, consumer, matter["id"]))["invoice"]

    resp = await db_client.get(
        f"{PAYMENTS}/invoices/{invoice['id']}/html", headers=consumer.headers
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "default-src 'none'" in resp.headers["content-security-policy"]
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert invoice["invoice_number"] in resp.text
    assert "<script>" not in resp.text
    assert "&lt;script&gt;" in resp.text


# --- cancelling a paid matter refunds it ---------------------------------------------------


async def test_advocate_cancelling_a_paid_matter_refunds_the_client_in_full(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer, advocate, matter = await _paid(db_client, db_txn_session, stage="SCHEDULED")

    resp = await db_client.post(
        f"{MATTERS}/{matter['id']}/cancel", json={"note": "Emergency"}, headers=advocate.headers
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"
    payment = (await _payment(db_client, consumer, matter["id"]))["payment"]
    assert payment["status"] == "REFUNDED"
    assert payment["refunded_amount"] == payment["amount"]
    assert len(payment["refunds"]) == 1
    assert "advocate" in payment["refunds"][0]["reason"]


async def test_consumer_can_cancel_a_paid_unscheduled_consultation_for_a_full_refund(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer, _advocate, matter = await _paid(db_client, db_txn_session)

    resp = await db_client.post(
        f"{MATTERS}/{matter['id']}/cancel", json={}, headers=consumer.headers
    )

    assert resp.json()["status"] == "CANCELLED"
    assert (await _payment(db_client, consumer, matter["id"]))["payment"]["status"] == "REFUNDED"


async def test_consumer_cannot_self_cancel_a_paid_document_service_or_scheduled_consultation(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer, _a, document = await _paid(
        db_client,
        db_txn_session,
        service_type="DOCUMENT_REVIEW",
        consultation_minutes=None,
        quote="900.00",
    )
    assert (
        await db_client.post(
            f"{MATTERS}/{document['id']}/cancel", json={}, headers=consumer.headers
        )
    ).status_code == 409

    consumer2, _b, scheduled = await _paid(db_client, db_txn_session, stage="SCHEDULED")
    assert (
        await db_client.post(
            f"{MATTERS}/{scheduled['id']}/cancel", json={}, headers=consumer2.headers
        )
    ).status_code == 409
    for matter, who in ((document, consumer), (scheduled, consumer2)):
        assert (await _payment(db_client, who, matter["id"]))["payment"]["status"] == "SUCCEEDED"


async def test_cancelling_an_unpaid_matter_involves_no_refund(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer, _advocate, matter = await _paid(db_client, db_txn_session, stage="ACCEPTED")
    resp = await db_client.post(
        f"{MATTERS}/{matter['id']}/cancel", json={}, headers=consumer.headers
    )
    assert resp.status_code == 200
    refunds = (await db_txn_session.execute(select(func.count()).select_from(Refund))).scalar_one()
    assert refunds == 0


async def test_a_failing_refund_rolls_the_cancellation_back(
    db_client: AsyncClient, db_txn_session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    consumer, advocate, matter = await _paid(db_client, db_txn_session)

    async def broken_refund(self: object, **_kw: object) -> None:
        raise ServiceUnavailableError("gateway down", code="payments_error")

    monkeypatch.setattr(MockPaymentProvider, "refund", broken_refund)
    resp = await db_client.post(
        f"{MATTERS}/{matter['id']}/cancel", json={}, headers=advocate.headers
    )

    assert resp.status_code == 503
    monkeypatch.undo()
    # Neither half happened: still PAID, nothing refunded.
    assert (await db_client.get(f"{MATTERS}/{matter['id']}", headers=consumer.headers)).json()[
        "status"
    ] == "PAID"
    assert (await _payment(db_client, consumer, matter["id"]))["payment"][
        "refunded_amount"
    ] == "0.00"


# --- admin refunds ------------------------------------------------------------------------


async def test_admin_partial_then_full_refunds_and_over_refund_is_rejected(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer, _advocate, matter = await _paid(
        db_client, db_txn_session, stage="CLOSED", quote="1000.00"
    )
    admin = await make_admin(db_txn_session, UserRole.LEGAL_ADMIN)
    payment_id = (await _payment(db_client, consumer, matter["id"]))["payment"]["id"]
    url = f"{ADMIN_PAYMENTS}/{payment_id}/refund"

    first = await db_client.post(
        url, json={"amount": "250.00", "reason": "Partial goodwill"}, headers=admin.headers
    )
    assert first.status_code == 200
    assert first.json()["status"] == "PARTIALLY_REFUNDED"
    assert first.json()["refunded_amount"] == "250.00"

    too_much = await db_client.post(
        url, json={"amount": "800.00", "reason": "x"}, headers=admin.headers
    )
    assert too_much.status_code == 422

    rest = await db_client.post(url, json={"reason": "Dispute upheld"}, headers=admin.headers)
    assert rest.json()["status"] == "REFUNDED"
    assert rest.json()["refunded_amount"] == "1000.00"
    assert [r["amount"] for r in rest.json()["refunds"]] == ["250.00", "750.00"]

    nothing_left = await db_client.post(url, json={"reason": "again"}, headers=admin.headers)
    assert nothing_left.status_code == 422
    assert "Nothing left" in nothing_left.json()["error"]["message"]


async def test_refunds_reduce_what_the_advocate_earned(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer, advocate, matter = await _paid(
        db_client, db_txn_session, stage="CLOSED", quote="1000.00"
    )
    admin = await make_admin(db_txn_session)
    earnings = "/api/v1/advocates/me/earnings"
    assert (await db_client.get(earnings, headers=advocate.headers)).json()["summary"][
        "gross_earned"
    ] == "1000.00"

    payment_id = (await _payment(db_client, consumer, matter["id"]))["payment"]["id"]
    await db_client.post(
        f"{ADMIN_PAYMENTS}/{payment_id}/refund",
        json={"amount": "250.00", "reason": "x"},
        headers=admin.headers,
    )

    body = (await db_client.get(earnings, headers=advocate.headers)).json()
    assert body["summary"]["gross_earned"] == "750.00"
    assert body["items"][0]["refunded"] == "250.00"


async def test_only_admins_can_refund(db_client: AsyncClient, db_txn_session: Any) -> None:
    consumer, advocate, matter = await _paid(db_client, db_txn_session)
    payment_id = (await _payment(db_client, consumer, matter["id"]))["payment"]["id"]
    url = f"{ADMIN_PAYMENTS}/{payment_id}/refund"

    for who in (consumer, advocate):
        assert (
            await db_client.post(url, json={"reason": "x"}, headers=who.headers)
        ).status_code == 403
    assert (await db_client.post(url, json={"reason": "x"})).status_code == 401
    admin = await make_admin(db_txn_session)
    unknown = await db_client.post(
        f"{ADMIN_PAYMENTS}/00000000-0000-0000-0000-000000000000/refund",
        json={"reason": "x"},
        headers=admin.headers,
    )
    assert unknown.status_code == 404
    assert (
        await db_client.post(url, json={"reason": ""}, headers=admin.headers)
    ).status_code == 422


# --- visibility --------------------------------------------------------------------------


async def test_payments_and_invoices_are_only_visible_to_participants_and_admins(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer, advocate, matter = await _paid(db_client, db_txn_session)
    invoice_id = (await _payment(db_client, consumer, matter["id"]))["invoice"]["id"]
    stranger = await register_consumer(db_client)
    other_advocate = await register_advocate(db_client, db_txn_session)
    admin = await make_admin(db_txn_session)

    for outsider in (stranger, other_advocate):
        assert (
            await db_client.get(f"{PAYMENTS}/matters/{matter['id']}", headers=outsider.headers)
        ).status_code == 404
        assert (
            await db_client.get(f"{PAYMENTS}/invoices/{invoice_id}", headers=outsider.headers)
        ).status_code == 404
        assert (
            await db_client.get(f"{PAYMENTS}/invoices/{invoice_id}/html", headers=outsider.headers)
        ).status_code == 404
    for insider in (consumer, advocate, admin):
        assert (
            await db_client.get(f"{PAYMENTS}/invoices/{invoice_id}", headers=insider.headers)
        ).status_code == 200
    assert (await db_client.get(f"{PAYMENTS}/invoices/{invoice_id}")).status_code == 401


async def test_my_payments_are_scoped_to_the_caller(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer, advocate, _matter = await _paid(db_client, db_txn_session)
    other_consumer, _other_advocate, _other = await _paid(db_client, db_txn_session)

    mine = (await db_client.get(f"{PAYMENTS}/mine", headers=consumer.headers)).json()
    received = (await db_client.get(f"{PAYMENTS}/mine", headers=advocate.headers)).json()
    admin = await make_admin(db_txn_session)
    everything = (await db_client.get(ADMIN_PAYMENTS, headers=admin.headers)).json()

    assert mine["total"] == 1 and received["total"] == 1
    assert mine["items"][0]["payment_id"] == received["items"][0]["payment_id"]
    assert (await db_client.get(f"{PAYMENTS}/mine", headers=other_consumer.headers)).json()[
        "total"
    ] == 1
    assert everything["total"] == 2
    assert (await db_client.get(ADMIN_PAYMENTS, headers=consumer.headers)).status_code == 403


# --- the production guard ----------------------------------------------------------------


async def test_the_mock_provider_cannot_take_payments_in_production(
    db_client: AsyncClient, db_txn_session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    consumer, _advocate, matter = await _paid(db_client, db_txn_session, stage="ACCEPTED")
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()

    resp = await db_client.post(f"{MATTERS}/{matter['id']}/pay", json={}, headers=consumer.headers)

    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "payments_not_configured"
    monkeypatch.undo()
    get_settings.cache_clear()
    # No money moved and the matter is still payable.
    assert (await db_client.get(f"{MATTERS}/{matter['id']}", headers=consumer.headers)).json()[
        "status"
    ] == "ACCEPTED"
    assert (
        await db_txn_session.execute(select(func.count()).select_from(Payment))
    ).scalar_one() == 0
