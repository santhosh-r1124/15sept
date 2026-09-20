"""chat_messages review columns (legal-ops high-risk query review) - Phase 12

Matches ``app/models/chat.py``. Only the user's own message carries a risk level, so review
state lives on that row. The partial index is the review queue: unreviewed HIGH/CRITICAL queries.

Revision ID: 0012_query_review
Revises: 0011_notifications
Create Date: 2026-01-12 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_query_review"
down_revision: str | None = "0011_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("reviewed_at", sa.DateTime(timezone=True)))
    op.add_column(
        "chat_messages",
        sa.Column(
            "reviewed_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "users.id", ondelete="SET NULL", name="fk_chat_messages_reviewed_by_id_users"
            ),
        ),
    )
    op.add_column("chat_messages", sa.Column("review_note", sa.Text()))
    op.create_index(
        "ix_chat_messages_review_queue",
        "chat_messages",
        ["created_at"],
        postgresql_where=sa.text("risk_level IN ('HIGH', 'CRITICAL') AND reviewed_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_chat_messages_review_queue", table_name="chat_messages")
    op.drop_column("chat_messages", "review_note")
    op.drop_column("chat_messages", "reviewed_by_id")
    op.drop_column("chat_messages", "reviewed_at")
