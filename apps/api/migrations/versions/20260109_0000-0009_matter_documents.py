"""matter_document_requests + matter_files (advocate portal document exchange, Phase 9)

Matches ``app/models/matter_document.py``. File bytes are not in the database - only metadata
and the server-generated storage key.

Revision ID: 0009_matter_documents
Revises: 0008_matters
Create Date: 2026-01-09 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_matter_documents"
down_revision: str | None = "0008_matters"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REQUEST_STATUS = postgresql.ENUM(
    "OPEN", "FULFILLED", name="matter_document_request_status", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    _REQUEST_STATUS.create(bind, checkfirst=False)

    op.create_table(
        "matter_document_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "matter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "matters.id", ondelete="CASCADE", name="fk_matter_document_requests_matter_id_matters"
            ),
            nullable=False,
        ),
        sa.Column(
            "requested_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "users.id",
                ondelete="CASCADE",
                name="fk_matter_document_requests_requested_by_id_users",
            ),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", _REQUEST_STATUS, nullable=False, server_default="OPEN"),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("clock_timestamp()")
        ),
    )
    op.create_index(
        "ix_matter_document_requests_matter_id", "matter_document_requests", ["matter_id"]
    )

    op.create_table(
        "matter_files",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "matter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matters.id", ondelete="CASCADE", name="fk_matter_files_matter_id_matters"),
            nullable=False,
        ),
        sa.Column(
            "uploader_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_matter_files_uploader_id_users"),
            nullable=False,
        ),
        sa.Column(
            "request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "matter_document_requests.id",
                ondelete="SET NULL",
                name="fk_matter_files_request_id_matter_document_requests",
            ),
            nullable=True,
        ),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(80), nullable=False, unique=True),
        sa.Column("is_final", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("clock_timestamp()")
        ),
    )
    op.create_index("ix_matter_files_matter_id", "matter_files", ["matter_id"])


def downgrade() -> None:
    op.drop_table("matter_files")
    op.drop_table("matter_document_requests")

    bind = op.get_bind()
    _REQUEST_STATUS.drop(bind, checkfirst=False)
