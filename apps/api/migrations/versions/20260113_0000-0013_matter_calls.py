"""matter_calls (voice / video consultation sessions) - metadata only, no media

Matches ``app/models/call.py``.

Revision ID: 0013_matter_calls
Revises: 0012_query_review
Create Date: 2026-01-13 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_matter_calls"
down_revision: str | None = "0012_query_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "matter_calls",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "matter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matters.id", ondelete="CASCADE", name="fk_matter_calls_matter_id_matters"),
            nullable=False,
        ),
        sa.Column("opened_by", sa.String(10), nullable=False),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.Column("connected_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("ended_reason", sa.String(20)),
    )
    op.create_index("ix_matter_calls_matter", "matter_calls", ["matter_id", "opened_at"])


def downgrade() -> None:
    op.drop_index("ix_matter_calls_matter", table_name="matter_calls")
    op.drop_table("matter_calls")
