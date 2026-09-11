"""Unit tests for app.services.ingestion.clean — pure functions, no I/O."""

from __future__ import annotations

from app.services.ingestion.clean import clean_document_text, clean_page_text


def test_collapses_repeated_whitespace() -> None:
    assert clean_page_text("Hello    world\t\tagain") == "Hello world again"


def test_strips_leading_and_trailing_whitespace_per_line() -> None:
    assert clean_page_text("   Section 1.   \n   Body text.   ") == "Section 1.\nBody text."


def test_removes_bare_page_number_lines() -> None:
    text = "Section 1. Short title.\n42\nThis Act may be called...\n7"
    cleaned = clean_page_text(text)
    assert "42" not in cleaned.splitlines()
    assert "7" not in cleaned.splitlines()
    assert "Section 1. Short title." in cleaned


def test_does_not_remove_numbers_that_are_part_of_a_line() -> None:
    text = "Section 43A deals with compensation."
    assert clean_page_text(text) == text


def test_collapses_three_or_more_blank_lines_to_two() -> None:
    cleaned = clean_page_text("Para one.\n\n\n\n\nPara two.")
    assert cleaned == "Para one.\n\nPara two."


def test_strips_replacement_character_runs() -> None:
    # Defensive: a broken PDF font encoding can decode to runs of U+FFFD via
    # pypdf — pure noise, not content. (The two real Acts fetched during
    # development didn't actually hit this — see clean.py's module comment —
    # but it's cheap insurance against a source list this varied.)
    text = "ARRANGEMENT OF SECTIONS\n�����\nCHAPTER I"
    cleaned = clean_page_text(text)
    assert "�" not in cleaned
    assert "ARRANGEMENT OF SECTIONS" in cleaned
    assert "CHAPTER I" in cleaned


def test_clean_document_text_preserves_page_separators() -> None:
    raw = "Page one   text.\f  99  \nPage two text."
    cleaned = clean_document_text(raw)
    pages = cleaned.split("\f")
    assert len(pages) == 2
    assert pages[0] == "Page one text."
    assert pages[1] == "Page two text."
