"""notifications (in-app + email outbox) and users.email_notifications - Phase 11

Matches ``app/models/notification.py``. ``kind`` / ``email_status`` are plain strings so new
event types never need a migration.

Revision ID: 0011_notifications
Revises: 0010_payments
Create Date: 2026-01-11 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_notifications"
down_revision: str | None = "0010_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_notifications", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "notifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "users.id", ondelete="CASCADE", name="fk_notifications_user_id_users"
            ),
            nullable=False,
        ),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("link", sa.String(300)),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.Column("email_status", sa.String(10), nullable=False),
        sa.Column("email_subject", sa.String(200)),
        sa.Column("email_body", sa.Text()),
        sa.Column("email_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("emailed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_notifications_user_created", "notifications", ["user_id", "created_at"])
    op.create_index(
        "ix_notifications_unread",
        "notifications",
        ["user_id"],
        postgresql_where=sa.text("read_at IS NULL"),
    )
    op.create_index(
        "ix_notifications_email_pending",
        "notifications",
        ["created_at"],
        postgresql_where=sa.text("email_status = 'PENDING'"),
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_email_pending", table_name="notifications")
    op.drop_index("ix_notifications_unread", table_name="notifications")
    op.drop_index("ix_notifications_user_created", table_name="notifications")
    op.drop_table("notifications")
    op.drop_column("users", "email_notifications")
