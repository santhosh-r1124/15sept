"""Plain-text extraction from a fetched document (PDF or HTML).

PDF pages are joined with a form-feed (``\\f``) so downstream chunking can
recover ``page_number``; HTML has no such concept so it's extracted as one
page.
"""

from __future__ import annotations

import io

from bs4 import BeautifulSoup
from pypdf import PdfReader

from app.core.errors import ValidationAppError
from app.services.ingestion.fetch import FetchedDocument


def extract_text(document: FetchedDocument) -> str:
    if "pdf" in document.content_type or document.url.lower().endswith(".pdf"):
        return _extract_pdf(document.raw_bytes)
    if "html" in document.content_type or document.url.lower().endswith((".htm", ".html")):
        return _extract_html(document.raw_bytes)
    return document.raw_bytes.decode("utf-8", errors="replace")


def _extract_pdf(raw_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(raw_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise ValidationAppError(f"Could not parse PDF: {exc}", code="extraction_failed") from exc
    return "\f".join(pages)


def _extract_html(raw_bytes: bytes) -> str:
    try:
        soup = BeautifulSoup(raw_bytes, "html.parser")
    except Exception as exc:
        raise ValidationAppError(f"Could not parse HTML: {exc}", code="extraction_failed") from exc
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    return soup.get_text(separator="\n")
