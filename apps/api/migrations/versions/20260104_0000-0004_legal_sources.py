"""legal sources: legal_documents, legal_chunks (+ pgvector HNSW index)

Phase 3 — Indian legal knowledge base. Matches ``app/models/legal_document.py``.
Embedding column dimension (768) must match ``EMBEDDING_DIM`` there and
``Settings.embedding_dimensions``.

Revision ID: 0004_legal_sources
Revises: 0003_chat_tables
Create Date: 2026-01-04 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0004_legal_sources"
down_revision: str | None = "0003_chat_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 768  # keep in sync with app/models/legal_document.py::EMBEDDING_DIM

# Type lifecycle is managed explicitly below (create()/drop()); create_type=False
# stops SQLAlchemy from also trying to (re)create/drop it as a table DDL side effect.
_DOCUMENT_TYPE = postgresql.ENUM(
    "ACT", "RULES", "REGULATION", "NOTIFICATION", "JUDGMENT", "OTHER",
    name="legal_document_type",
    create_type=False,
)
_INGESTION_STATUS = postgresql.ENUM(
    "PENDING", "PROCESSING", "COMPLETED", "FAILED",
    name="ingestion_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    _DOCUMENT_TYPE.create(bind, checkfirst=False)
    _INGESTION_STATUS.create(bind, checkfirst=False)

    op.create_table(
        "legal_documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("law_name", sa.String(300), nullable=True),
        sa.Column("jurisdiction", sa.String(10), nullable=False, server_default="IN"),
        sa.Column("state_code", sa.String(2), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("document_type", _DOCUMENT_TYPE, nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("version", sa.String(50), nullable=True),
        sa.Column("checksum", sa.String(64), nullable=False, server_default=""),
        sa.Column(
            "ingestion_status", _INGESTION_STATUS, nullable=False, server_default="PENDING"
        ),
        sa.Column("ingestion_error", sa.Text(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_legal_documents_document_type", "legal_documents", ["document_type"]
    )
    op.create_index("ix_legal_documents_jurisdiction", "legal_documents", ["jurisdiction"])

    op.create_table(
        "legal_chunks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "legal_documents.id", ondelete="CASCADE", name="fk_legal_chunks_document_id_legal_documents"
            ),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(50), nullable=True),
        sa.Column("article", sa.String(50), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_legal_chunks_document_id", "legal_chunks", ["document_id"])
    # Approximate nearest-neighbour index for cosine-distance search
    # (app/services/ingestion/search.py). HNSW needs no training step, unlike
    # ivfflat, so it works fine on an empty/small table too.
    op.execute(
        "CREATE INDEX ix_legal_chunks_embedding_hnsw ON legal_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_table("legal_chunks")
    op.drop_table("legal_documents")

    bind = op.get_bind()
    _INGESTION_STATUS.drop(bind, checkfirst=False)
    _DOCUMENT_TYPE.drop(bind, checkfirst=False)
