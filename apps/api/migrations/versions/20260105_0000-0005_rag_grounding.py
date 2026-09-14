"""rag grounding: legal_chunks.content_tsv (+ GIN index), chat_messages.sources

Phase 4 — production RAG. ``content_tsv`` backs the keyword half of hybrid
search (app/services/rag/retrieval.py); it's a Postgres generated column so it
stays in sync with ``content`` automatically, including for rows inserted
before this migration ran. ``sources`` records which legal_chunks grounded
each assistant reply, for citation display.

Revision ID: 0005_rag_grounding
Revises: 0004_legal_sources
Create Date: 2026-01-05 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_rag_grounding"
down_revision: str | None = "0004_legal_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE legal_chunks ADD COLUMN content_tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('english', content)) STORED"
    )
    op.execute(
        "CREATE INDEX ix_legal_chunks_content_tsv ON legal_chunks USING gin (content_tsv)"
    )
    op.add_column("chat_messages", sa.Column("sources", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_messages", "sources")
    op.execute("DROP INDEX ix_legal_chunks_content_tsv")
    op.execute("ALTER TABLE legal_chunks DROP COLUMN content_tsv")
