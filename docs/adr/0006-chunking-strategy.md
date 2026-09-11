# 0006 — Chunking strategy: plain sliding window, no heading detection

- Status: Accepted
- Date: 2026-09-11
- Deciders: Platform team

## Context

`app/services/ingestion/chunk.py` splits cleaned document text into
retrieval-sized pieces. The first version tried two things: (1) detect
`Section N.` / `Article N` headings via line-start regexes and use them as
chunk boundaries + metadata, falling back to (2) a fixed-size sliding window
with paragraph/sentence-boundary snapping.

Real-world testing (during Phase 3 development, fetching the actual
[IT Act 2000 PDF](https://www.indiacode.nic.in/bitstream/123456789/13116/1/it_act_2000_updated.pdf)
from India Code and the
[DPDP Act 2023 PDF](https://www.meity.gov.in/static/uploads/2024/06/2bf1f0e9f04e6fb4f8fef35e82c42aa5.pdf)
from MeitY, then running the actual pipeline code against them) surfaced two
real bugs the synthetic unit tests hadn't caught:

1. **Heading detection is unsound against PDF-extracted text.** pypdf's plain
   text extraction preserves no blank-line paragraph breaks and wraps lines
   at arbitrary visual positions (a layout artefact, not semantic structure).
   A cross-reference like "...under section 8 of this Act" can itself start a
   wrapped line and gets misread as a new section heading.
2. **The sliding-window boundary snap could crawl.** The window search
   originally looked for a paragraph/sentence break anywhere in
   `[start, end)`. When a boundary (a period, say) sat very close to `start`,
   it got accepted, producing a tiny piece — and the overlap step
   (`start = end - overlap_chars`) could then land *behind* `start`, falling
   back to `start + 1`. That crawled forward one character at a time for
   dozens of iterations near any sparsely-punctuated stretch. Measured
   effect: the DPDP Act (64k chars) chunked into **1230 pieces averaging 156
   characters** instead of a sane ~60 pieces averaging ~1200. This is the
   dominant bug — removing heading detection alone barely moved the count;
   fixing the boundary search (require it to be past the window's own
   midpoint) is what actually fixed it.

## Decision

- `chunk_document` is a plain size-based sliding window per page
  (`DEFAULT_MAX_CHARS = 1500`, `DEFAULT_OVERLAP_CHARS = 200`). No heading
  detection.
- The boundary snap only searches `[start + max_chars // 2, end)` — never
  accepts a boundary in the front half of the window, which is what
  prevents the crawl.
- `Chunk.section` / `Chunk.article` stay in the dataclass (nullable) for a
  future, more reliable implementation, but the current pipeline always
  leaves them `None`.
- Added a **noise filter** in `clean_page_text` for Unicode private-use /
  unassigned / surrogate codepoints (defensive — genuinely broken PDF font
  encodings are plausible across a large, varied source list, even though
  the two real Acts fetched during development turned out fine; what looked
  like garbling in a terminal was legitimate EN DASH separator runs).

## Consequences

- `section`/`article` metadata (from the roadmap's field list) is not
  populated yet. `LegalChunk.section`/`.article` will read `NULL` for
  everything ingested until this is revisited.
- Real section/article detection needs layout-aware extraction (font
  size/boldness/position — plain-text extraction throws that away). Options
  for later: `pdfplumber`'s layout mode, or asking Claude to identify section
  boundaries as a structuring pass over the cleaned text.
- The regression this caused is now covered by
  `tests/test_ingestion_chunk.py::test_early_boundary_does_not_cause_a_tiny_chunk_crawl`,
  which reproduces the exact failure shape (early boundary, long
  punctuation-sparse tail) without needing network access.
- **Lesson for future phases**: synthetic unit tests with evenly-distributed
  punctuation didn't catch either bug — both only showed up against real,
  messy government PDFs. Prefer validating new ingestion/extraction logic
  against at least one real fetched document before considering it done.

## Alternatives considered

- **Keep heading detection, make the regex stricter** — plausible but hard to
  validate confidently without a much larger corpus of real documents than
  available during development; deferred rather than shipped half-tested.
- **Layout-aware extraction now** (`pdfplumber` + font-size heuristics) — the
  actually-correct long-term fix, but a bigger lift than Phase 3's scope;
  revisit alongside Phase 4 (RAG) if chunk quality turns out to matter for
  retrieval results.
