"""Unit tests for app.services.ingestion.chunk — pure functions, no I/O.

Chunks are a plain size-based sliding window (see chunk.py's module
docstring for why section/article heading-detection was tried and dropped).
"""

from __future__ import annotations

from app.services.ingestion.chunk import chunk_document


def test_empty_text_returns_no_chunks() -> None:
    assert chunk_document("") == []
    assert chunk_document("   \f  \f  ") == []


def test_tracks_page_number_across_form_feeds() -> None:
    chunks = chunk_document("Page one content.\fPage two content.\fPage three content.")
    assert [c.page_number for c in chunks] == [1, 2, 3]


def test_chunks_are_never_tagged_with_section_or_article() -> None:
    # Auto-detection was removed (see module docstring) — every chunk should
    # come back untagged, even when the text contains "Section N." text.
    chunks = chunk_document("Section 1. Short title.\nThis Act may be called the Test Act.")
    assert all(c.section is None and c.article is None for c in chunks)


def test_splits_long_text_respecting_max_chars() -> None:
    paragraph = "This is a sentence that repeats. " * 20  # ~680 chars
    text = "\n\n".join([paragraph] * 5)  # ~3400 chars
    chunks = chunk_document(text, max_chars=500, overlap_chars=50)
    assert len(chunks) > 1
    for chunk in chunks:
        # A little slack: boundary search can land slightly past max_chars.
        assert len(chunk.content) <= 600


def test_consecutive_chunks_overlap() -> None:
    paragraph = "Word " * 400  # long, no natural paragraph/sentence breaks to snap to
    chunks = chunk_document(paragraph, max_chars=300, overlap_chars=50)
    assert len(chunks) > 1
    # The tail of one chunk should reappear at the head of the next.
    tail = chunks[0].content[-30:]
    assert tail in chunks[1].content


def test_short_text_is_a_single_chunk() -> None:
    chunks = chunk_document("Short.", max_chars=1500, overlap_chars=200)
    assert len(chunks) == 1
    assert chunks[0].content == "Short."


def test_chunk_count_is_reasonable_for_document_length() -> None:
    # Sanity guard: a page-sized document should produce a small handful of
    # chunks sized near max_chars, not hundreds — see
    # test_early_boundary_does_not_cause_a_tiny_chunk_crawl for the specific
    # real bug this protects against (a sliding-window boundary-snap crawl,
    # found by ingesting the actual DPDP Act 2023 PDF).
    page = "Prose text. " * 250  # ~3000 chars, one page
    chunks = chunk_document(page, max_chars=1500, overlap_chars=200)
    assert 1 <= len(chunks) <= 4


def test_early_boundary_does_not_cause_a_tiny_chunk_crawl() -> None:
    # Regression test for the real _sliding_window bug found by ingesting the
    # actual DPDP Act 2023 PDF: a period sitting early in the window used to
    # get accepted as "the" boundary, producing a tiny piece, and the overlap
    # step would then barely move `start` forward — crawling one character at
    # a time for dozens of iterations (observed: pieces of length 200, 199,
    # 198, 197... on real pages) before finally passing the early boundary.
    text = "Short lead-in. " + (
        "word " * 500
    )  # one early period, then ~2500 punctuation-free chars
    chunks = chunk_document(text, max_chars=1500, overlap_chars=200)
    assert len(chunks) <= 4
    assert all(len(c.content) > 100 for c in chunks)
