"""Text cleaning: whitespace normalization + noise removal.

Operates one page at a time (split the raw text on ``\\f`` first) so the
form-feed page separators survive cleaning for the chunker to use.
"""

from __future__ import annotations

import re
import unicodedata

_WHITESPACE_RUN = re.compile(r"[ \t]+")
_BLANK_LINES = re.compile(r"\n{3,}")
_PAGE_NUMBER_LINE = re.compile(r"^\d{1,4}$")
# Unicode categories that are never real document content: private-use (Co —
# what symbol/bullet fonts fall back to when a PDF's font encoding can't be
# resolved), unassigned (Cn), and surrogates (Cs). Defensive — genuinely
# broken font encodings are plausible across a large, varied source list even
# though the two real Acts fetched during development (IT Act 2000, DPDP Act
# 2023) turned out fine once checked codepoint-by-codepoint; what looked like
# garbling in a terminal was legitimate EN DASH (U+2013) separator runs.
# Deliberately excludes Cc (control) — \n/\r/\t/\f are structural, not noise.
_NOISE_CATEGORIES = frozenset({"Co", "Cn", "Cs"})
_REPLACEMENT_CHAR = "�"


def _strip_noise_chars(text: str) -> str:
    return "".join(
        ch
        for ch in text
        if ch != _REPLACEMENT_CHAR and unicodedata.category(ch) not in _NOISE_CATEGORIES
    )


def clean_page_text(text: str) -> str:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = _strip_noise_chars(raw_line)
        line = _WHITESPACE_RUN.sub(" ", line).strip()
        if _PAGE_NUMBER_LINE.match(line):
            continue  # drop bare page-number lines (headers/footers)
        lines.append(line)  # blank lines are kept — they mark paragraph breaks
    cleaned = "\n".join(lines)
    cleaned = _BLANK_LINES.sub("\n\n", cleaned)
    return cleaned.strip()


def clean_document_text(raw_text: str) -> str:
    """Clean every page in a ``\\f``-joined document, preserving the separators."""
    return "\f".join(clean_page_text(page) for page in raw_text.split("\f"))
