"""Legal source ingestion pipeline (Phase 3).

    fetch -> extract -> clean -> chunk -> embed -> persist (pgvector)

Each stage is a small, independently testable, dependency-free-where-possible
function; ``pipeline.ingest_source`` wires them together and persists the
result. This currently lives in ``apps/api`` rather than
``services/document-processing`` — see docs/adr/0004-ingestion-lives-in-api.md
for why, and when that should change.
"""
