"""Unit tests for app.services.ingestion.extract — no network."""

from __future__ import annotations

import pytest

from app.core.errors import ValidationAppError
from app.services.ingestion.extract import extract_text
from app.services.ingestion.fetch import FetchedDocument


def _doc(content_type: str, raw: bytes, url: str = "https://example.test/doc") -> FetchedDocument:
    import hashlib

    return FetchedDocument(
        url=url, content_type=content_type, raw_bytes=raw, checksum=hashlib.sha256(raw).hexdigest()
    )


def test_extract_html_returns_visible_text() -> None:
    html = b"<html><body><h1>Section 1</h1><p>Short title.</p></body></html>"
    text = extract_text(_doc("text/html", html))
    assert "Section 1" in text
    assert "Short title." in text


def test_extract_html_strips_script_style_nav_header_footer() -> None:
    html = (
        b"<html><body>"
        b"<nav>Skip to content</nav>"
        b"<header>Site Header</header>"
        b"<script>trackPageView();</script>"
        b"<style>.x { color: red; }</style>"
        b"<main><p>The actual legal text.</p></main>"
        b"<footer>Copyright notice</footer>"
        b"</body></html>"
    )
    text = extract_text(_doc("text/html", html))
    assert "The actual legal text." in text
    for excluded in (
        "Skip to content",
        "Site Header",
        "trackPageView",
        "color: red",
        "Copyright notice",
    ):
        assert excluded not in text


def test_extract_by_url_extension_when_content_type_missing() -> None:
    html = b"<p>Hello from a .html file.</p>"
    text = extract_text(_doc("", html, url="https://example.test/doc.html"))
    assert "Hello from a .html file." in text


def test_extract_pdf_invalid_bytes_raises_validation_error() -> None:
    with pytest.raises(ValidationAppError) as exc_info:
        extract_text(_doc("application/pdf", b"not a real pdf"))
    assert exc_info.value.code == "extraction_failed"


def test_unknown_content_type_falls_back_to_plain_text_decode() -> None:
    text = extract_text(_doc("text/plain", "Plain café text.".encode()))
    assert text == "Plain café text."


def test_unknown_content_type_replaces_undecodable_bytes_instead_of_raising() -> None:
    text = extract_text(_doc("application/octet-stream", b"\xff\xfe not valid utf-8"))
    assert isinstance(text, str)
