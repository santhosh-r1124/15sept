"""chat: conversations, chat_messages

Phase 2 — public legal AI chat. Matches ``app/models/chat.py``.

Revision ID: 0003_chat_tables
Revises: 0002_auth_tables
Create Date: 2026-01-03 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_chat_tables"
down_revision: str | None = "0002_auth_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Type lifecycle is managed explicitly below (create()/drop()); create_type=False
# stops SQLAlchemy from also trying to (re)create/drop it as a table DDL side effect.
_MESSAGE_ROLE = postgresql.ENUM("user", "assistant", name="message_role", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    _MESSAGE_ROLE.create(bind, checkfirst=False)

    op.create_table(
        "conversations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_conversations_user_id_users"),
            nullable=True,
        ),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])

    op.create_table(
        "chat_messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "conversations.id", ondelete="CASCADE", name="fk_chat_messages_conversation_id_conversations"
            ),
            nullable=False,
        ),
        sa.Column("role", _MESSAGE_ROLE, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("legal_category", sa.String(30), nullable=True),
        sa.Column("jurisdiction_scope", sa.String(30), nullable=True),
        sa.Column("is_out_of_scope", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_chat_messages_conversation_id", "chat_messages", ["conversation_id"])


def downgrade() -> None:
    op.drop_table("chat_messages")
    op.drop_table("conversations")

    bind = op.get_bind()
    _MESSAGE_ROLE.drop(bind, checkfirst=False)
