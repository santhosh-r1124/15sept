"""Unit tests for upload validation + local storage - no DB, no network."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.errors import ValidationAppError
from app.services.storage import (
    FileTooLargeError,
    LocalFileStorage,
    content_disposition,
    new_storage_key,
    safe_download_name,
    validate_upload,
)

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
DOCX = b"PK\x03\x04" + b"\x00" * 16
DOC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 16
MAX = 1024


@pytest.mark.parametrize(
    ("content_type", "data", "ext"),
    [
        ("application/pdf", PDF, ".pdf"),
        ("image/png", PNG, ".png"),
        ("image/jpeg", JPEG, ".jpg"),
        (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            DOCX,
            ".docx",
        ),
        ("application/msword", DOC, ".doc"),
        ("text/plain", "Plain notes, incl. unicode: ₹500".encode(), ".txt"),
    ],
)
def test_valid_uploads_map_to_an_extension(content_type: str, data: bytes, ext: str) -> None:
    assert validate_upload(content_type, data, max_bytes=MAX) == ext


@pytest.mark.parametrize(
    "content_type", ["text/html", "application/x-msdownload", "image/svg+xml", ""]
)
def test_disallowed_content_types_are_rejected(content_type: str) -> None:
    with pytest.raises(ValidationAppError):
        validate_upload(content_type, PDF, max_bytes=MAX)


def test_contents_must_match_the_declared_type() -> None:
    # A Windows executable (or anything else) claiming to be a PDF.
    with pytest.raises(ValidationAppError):
        validate_upload("application/pdf", b"MZ\x90\x00\x03", max_bytes=MAX)
    with pytest.raises(ValidationAppError):
        validate_upload("image/png", JPEG, max_bytes=MAX)


def test_text_must_be_real_utf8_without_nul_bytes() -> None:
    with pytest.raises(ValidationAppError):
        validate_upload("text/plain", b"\xff\xfe\x00binary", max_bytes=MAX)
    with pytest.raises(ValidationAppError):
        validate_upload("text/plain", b"looks fine\x00but is not", max_bytes=MAX)


def test_empty_and_oversized_uploads_are_rejected() -> None:
    with pytest.raises(ValidationAppError):
        validate_upload("application/pdf", b"", max_bytes=MAX)
    with pytest.raises(FileTooLargeError) as exc:
        validate_upload("application/pdf", PDF + b"x" * MAX, max_bytes=MAX)
    assert exc.value.status_code == 413


def test_storage_keys_are_random_hex_with_the_extension() -> None:
    a, b = new_storage_key(".pdf"), new_storage_key(".pdf")
    assert a != b
    assert a.endswith(".pdf")
    assert len(a) == 32 + 4


@pytest.mark.parametrize(
    "key", ["../etc/passwd", "..\\evil.pdf", "a/b.pdf", "short.pdf", "x" * 32 + ".exe/../y", ""]
)
async def test_storage_refuses_keys_that_could_escape_the_directory(
    tmp_path: Path, key: str
) -> None:
    storage = LocalFileStorage(tmp_path)
    with pytest.raises(ValueError):
        await storage.save(key, b"data")
    with pytest.raises(ValueError):
        await storage.read(key)


async def test_storage_round_trip(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path / "nested" / "uploads")  # created on first save
    key = new_storage_key(".pdf")
    await storage.save(key, PDF)
    assert await storage.read(key) == PDF


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Agreement (final).pdf", "Agreement _final_.pdf"),
        ('evil"; filename="x.exe', "evil__ filename__x.exe"),
        ("line\r\nbreak.pdf", "line__break.pdf"),
        ("../../secret.txt", "_.._secret.txt"),
        ("   ", "document"),
        ("हिन्दी.pdf", "______.pdf"),
    ],
)
def test_download_names_are_safe_for_a_header(raw: str, expected: str) -> None:
    cleaned = safe_download_name(raw)
    assert cleaned == expected
    assert '"' not in cleaned and "\r" not in cleaned and "\n" not in cleaned


def test_content_disposition_keeps_indian_script_names_via_rfc5987() -> None:
    header = content_disposition(
        "\u0939\u093f\u0928\u094d\u0926\u0940 \u0905\u0928\u0941\u092c\u0902\u0927.pdf"
    )
    # ASCII fallback for old clients, real name for modern ones.
    assert header.startswith('attachment; filename="')
    assert "filename*=UTF-8''%E0%A4%B9" in header
    assert header.endswith(".pdf")


def test_content_disposition_cannot_be_used_to_inject_headers_or_paths() -> None:
    header = content_disposition('a"; x=1\r\nSet-Cookie: s=1/../b.pdf')
    assert "\r" not in header and "\n" not in header
    assert header.count('"') == 2  # only the two delimiting the ASCII fallback
    assert "/" not in header.split("filename*=")[1]
