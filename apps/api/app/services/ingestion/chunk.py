"""Split cleaned document text into retrieval-sized chunks.

Chunks are a fixed-size sliding window per page, breaking on a paragraph or
sentence boundary near the limit when one exists.

``section``/``article`` are NOT auto-detected. An earlier version tried
line-start regexes (``^Section 43A.``); dropped on principle, not because it
was empirically the cause of the fragmentation below (removing it alone
barely changed chunk counts — see docs/adr/0006-chunking-strategy.md for the
actual root cause). It's still unsound against PDF-extracted text: pypdf's
plain-text extraction preserves no blank-line paragraph breaks and wraps
lines at arbitrary visual positions, so a cross-reference like "...under
section 8 of this Act" can itself start a wrapped line and get misread as the
start of section 8. Real section/article detection needs layout-aware
extraction (font size/boldness — pypdf's plain text discards that).
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_MAX_CHARS = 1500
DEFAULT_OVERLAP_CHARS = 200


@dataclass(frozen=True, slots=True)
class Chunk:
    content: str
    section: str | None
    article: str | None
    page_number: int | None


def chunk_document(
    cleaned_text: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page_number, page_text in enumerate(cleaned_text.split("\f"), start=1):
        page_text = page_text.strip()
        if not page_text:
            continue
        for piece in _sliding_window(page_text, max_chars, overlap_chars):
            piece = piece.strip()
            if piece:
                chunks.append(
                    Chunk(content=piece, section=None, article=None, page_number=page_number)
                )
    return chunks


def _sliding_window(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    """Fixed-size window, snapping to a paragraph/sentence boundary near the
    end when one exists.

    The boundary search only looks in the back half of the window
    (``[start + max_chars // 2, end)``). Searching the *whole* window was an
    earlier bug: a period or blank line sitting right after ``start`` would
    get accepted as "the" boundary, producing a tiny piece; combined with the
    overlap step landing behind ``start``, that degenerated into crawling
    forward one character at a time for hundreds of iterations near any
    sparsely-punctuated stretch (found via real India Code / MeitY PDFs —
    see docs/adr/0006-chunking-strategy.md).
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    min_chunk_chars = max(max_chars // 2, 1)
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            search_from = start + min_chunk_chars
            boundary = text.rfind("\n\n", search_from, end)
            if boundary == -1:
                boundary = text.rfind(". ", search_from, end)
            if boundary != -1:
                end = boundary + 1
        pieces.append(text[start:end])
        if end >= len(text):
            break
        start = max(end - overlap_chars, start + 1)
    return pieces
