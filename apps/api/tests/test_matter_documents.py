"""Integration tests for matter document exchange (Phase 9). Needs Postgres - see
conftest.db_client. Uploads go to a per-test temp directory."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.models.user import UserRole
from tests.helpers import (
    Account,
    advance_matter,
    book_matter,
    make_admin,
    register_advocate,
    register_consumer,
)

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"


@pytest.fixture
def upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def _names(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir())


def _base(mid: str) -> str:
    return f"/api/v1/matters/{mid}"


async def _upload(
    client: AsyncClient,
    mid: str,
    who: Account,
    *,
    name: str = "contract.pdf",
    data: bytes = PDF,
    content_type: str = "application/pdf",
    **form: Any,
) -> Any:
    return await client.post(
        f"{_base(mid)}/files",
        files={"file": (name, data, content_type)},
        data={k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in form.items()},
        headers=who.headers,
    )


async def _accepted(
    client: AsyncClient, session: Any, **kw: Any
) -> tuple[Account, Account, dict[str, Any]]:
    consumer = await register_consumer(client)
    advocate = await register_advocate(client, session)
    matter = await book_matter(client, consumer, advocate, **kw)
    matter = await advance_matter(client, matter, consumer, advocate, "ACCEPTED")
    return consumer, advocate, matter


async def test_request_upload_fulfil_and_download(
    db_client: AsyncClient, db_txn_session: Any, upload_dir: Path
) -> None:
    consumer, advocate, matter = await _accepted(db_client, db_txn_session)
    mid = matter["id"]

    created = await db_client.post(
        f"{_base(mid)}/document-requests",
        json={"description": "Your current rental agreement"},
        headers=advocate.headers,
    )
    assert created.status_code == 201
    request_id = created.json()["id"]
    assert created.json()["status"] == "OPEN"

    uploaded = await _upload(
        db_client, mid, consumer, name="My Agreement (v2).pdf", request_id=request_id
    )
    assert uploaded.status_code == 201, uploaded.text
    file_id = uploaded.json()["id"]
    assert uploaded.json()["uploader_role"] == "CONSUMER"
    assert uploaded.json()["is_final"] is False

    listing = (await db_client.get(f"{_base(mid)}/documents", headers=advocate.headers)).json()
    assert [r["status"] for r in listing["requests"]] == ["FULFILLED"]
    assert [f["file_name"] for f in listing["files"]] == ["My Agreement (v2).pdf"]

    downloaded = await db_client.get(f"{_base(mid)}/files/{file_id}", headers=advocate.headers)
    assert downloaded.status_code == 200
    assert downloaded.content == PDF
    assert downloaded.headers["content-type"] == "application/pdf"
    assert downloaded.headers["x-content-type-options"] == "nosniff"
    assert downloaded.headers["content-disposition"] == (
        'attachment; filename="My Agreement _v2_.pdf"; '
        "filename*=UTF-8''My%20Agreement%20%28v2%29.pdf"
    )

    # The client's file name never reaches the filesystem: one server-named file on disk.
    on_disk = _names(upload_dir)
    assert len(on_disk) == 1
    assert "Agreement" not in on_disk[0]


async def test_only_the_advocate_can_request_documents_or_upload_finals(
    db_client: AsyncClient, db_txn_session: Any, upload_dir: Path
) -> None:
    consumer, _advocate, matter = await _accepted(db_client, db_txn_session)
    mid = matter["id"]

    as_consumer = await db_client.post(
        f"{_base(mid)}/document-requests", json={"description": "x"}, headers=consumer.headers
    )
    assert as_consumer.status_code == 403
    final_by_consumer = await _upload(db_client, mid, consumer, is_final=True)
    assert final_by_consumer.status_code == 403


async def test_final_documents_need_payment_first_then_reach_the_consumer(
    db_client: AsyncClient, db_txn_session: Any, upload_dir: Path
) -> None:
    consumer, advocate, matter = await _accepted(db_client, db_txn_session)
    mid = matter["id"]

    too_early = await _upload(db_client, mid, advocate, name="final.pdf", is_final=True)
    assert too_early.status_code == 409  # ACCEPTED, client hasn't paid yet

    paid = await db_client.post(f"{_base(mid)}/pay", json={}, headers=consumer.headers)
    assert paid.status_code == 200
    final = await _upload(db_client, mid, advocate, name="final.pdf", is_final=True)
    assert final.status_code == 201
    assert final.json()["is_final"] is True
    assert final.json()["uploader_role"] == "ADVOCATE"

    fetched = await db_client.get(
        f"{_base(mid)}/files/{final.json()['id']}", headers=consumer.headers
    )
    assert fetched.status_code == 200
    assert fetched.content == PDF


async def test_exchange_is_closed_before_accept_and_after_the_matter_ends(
    db_client: AsyncClient, db_txn_session: Any, upload_dir: Path
) -> None:
    consumer = await register_consumer(db_client)
    advocate = await register_advocate(db_client, db_txn_session)
    matter = await book_matter(
        db_client, consumer, advocate, service_type="DOCUMENT_REVIEW", consultation_minutes=None
    )
    mid = matter["id"]

    early = await _upload(db_client, mid, consumer)
    assert early.status_code == 409
    assert early.json()["error"]["code"] == "documents_closed"

    await advance_matter(db_client, matter, consumer, advocate, "CLOSED", quote="900.00")
    late = await _upload(db_client, mid, consumer)
    assert late.status_code == 409
    request = await db_client.post(
        f"{_base(mid)}/document-requests", json={"description": "x"}, headers=advocate.headers
    )
    assert request.status_code == 409


async def test_uploads_are_validated(
    db_client: AsyncClient, db_txn_session: Any, upload_dir: Path
) -> None:
    consumer, _advocate, matter = await _accepted(db_client, db_txn_session)
    mid = matter["id"]

    html = await _upload(
        db_client, mid, consumer, name="x.html", data=b"<script>", content_type="text/html"
    )
    assert html.status_code == 422
    spoofed = await _upload(db_client, mid, consumer, name="fake.pdf", data=b"MZ\x90\x00not a pdf")
    assert spoofed.status_code == 422
    empty = await _upload(db_client, mid, consumer, data=b"")
    assert empty.status_code == 422
    assert _names(upload_dir) == []  # nothing rejected was ever written


async def test_oversized_uploads_are_413(
    db_client: AsyncClient,
    db_txn_session: Any,
    upload_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    consumer, _advocate, matter = await _accepted(db_client, db_txn_session)
    monkeypatch.setenv("UPLOAD_MAX_BYTES", "64")
    get_settings.cache_clear()

    resp = await _upload(db_client, matter["id"], consumer, data=PDF + b"x" * 100)
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "file_too_large"
    assert _names(upload_dir) == []


async def test_request_id_must_belong_to_this_matter(
    db_client: AsyncClient, db_txn_session: Any, upload_dir: Path
) -> None:
    consumer, advocate, matter = await _accepted(db_client, db_txn_session)
    other_consumer = await register_consumer(db_client)
    other = await book_matter(db_client, other_consumer, advocate)
    other = await advance_matter(db_client, other, other_consumer, advocate, "ACCEPTED")
    foreign = await db_client.post(
        f"{_base(other['id'])}/document-requests",
        json={"description": "y"},
        headers=advocate.headers,
    )

    wrong_matter = await _upload(db_client, matter["id"], consumer, request_id=foreign.json()["id"])
    assert wrong_matter.status_code == 404
    unknown = await _upload(db_client, matter["id"], consumer, request_id=uuid.uuid4())
    assert unknown.status_code == 404


async def test_access_control_on_documents(
    db_client: AsyncClient, db_txn_session: Any, upload_dir: Path
) -> None:
    consumer, advocate, matter = await _accepted(db_client, db_txn_session)
    mid = matter["id"]
    uploaded = await _upload(db_client, mid, consumer)
    file_id = uploaded.json()["id"]
    stranger = await register_consumer(db_client)
    other_advocate = await register_advocate(db_client, db_txn_session)
    admin = await make_admin(db_txn_session, UserRole.LEGAL_ADMIN)

    for outsider in (stranger, other_advocate):
        assert (
            await db_client.get(f"{_base(mid)}/documents", headers=outsider.headers)
        ).status_code == 404
        assert (
            await db_client.get(f"{_base(mid)}/files/{file_id}", headers=outsider.headers)
        ).status_code == 404
        assert (await _upload(db_client, mid, outsider)).status_code == 404

    # Admins can read and download, never write.
    assert (
        await db_client.get(f"{_base(mid)}/documents", headers=admin.headers)
    ).status_code == 200
    assert (
        await db_client.get(f"{_base(mid)}/files/{file_id}", headers=admin.headers)
    ).status_code == 200
    assert (await _upload(db_client, mid, admin)).status_code == 404

    # A file id from another matter is not reachable through this one.
    other_consumer = await register_consumer(db_client)
    other = await book_matter(db_client, other_consumer, advocate)
    unknown = await db_client.get(f"{_base(other['id'])}/files/{file_id}", headers=advocate.headers)
    assert unknown.status_code == 404
    assert (await db_client.get(f"{_base(mid)}/documents")).status_code == 401
