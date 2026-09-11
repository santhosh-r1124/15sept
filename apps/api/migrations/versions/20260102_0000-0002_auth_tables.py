"""auth: users, advocate profiles, verification/reset/refresh tokens

Phase 1 — authentication & RBAC. Matches ``app/models/user.py``.

Revision ID: 0002_auth_tables
Revises: 0001_initial_extensions
Create Date: 2026-01-02 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_auth_tables"
down_revision: str | None = "0001_initial_extensions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Type lifecycle is managed explicitly below (create()/drop()); create_type=False
# stops SQLAlchemy from also trying to (re)create/drop it as a table DDL side effect.
_USER_ROLE = postgresql.ENUM(
    "CONSUMER",
    "ADVOCATE",
    "ADMIN",
    "LEGAL_ADMIN",
    "ENTERPRISE_USER",
    name="user_role",
    create_type=False,
)
_VERIFICATION_STATUS = postgresql.ENUM(
    "PENDING",
    "IN_REVIEW",
    "VERIFIED",
    "REJECTED",
    name="verification_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    _USER_ROLE.create(bind, checkfirst=False)
    _VERIFICATION_STATUS.create(bind, checkfirst=False)

    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column(
            "role",
            _USER_ROLE,
            nullable=False,
            server_default="CONSUMER",
        ),
        sa.Column("display_name", sa.String(150), nullable=True),
        sa.Column("state_code", sa.String(2), nullable=True),
        sa.Column("preferred_language", sa.String(50), nullable=True),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "advocate_profiles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_advocate_profiles_user_id_users"),
            nullable=False,
        ),
        sa.Column(
            "practice_areas",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'::character varying[]"),
        ),
        sa.Column("state_code", sa.String(2), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column(
            "languages",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'::character varying[]"),
        ),
        sa.Column("consultation_fee", sa.Numeric(10, 2), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("experience_years", sa.Integer(), nullable=True),
        sa.Column(
            "verification_status",
            _VERIFICATION_STATUS,
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("verification_note", sa.Text(), nullable=True),
        sa.Column("availability", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "uq_advocate_profiles_user_id", "advocate_profiles", ["user_id"], unique=True
    )

    op.create_table(
        "email_verification_tokens",
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
                "users.id", ondelete="CASCADE", name="fk_email_verification_tokens_user_id_users"
            ),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_email_verification_tokens_token_hash",
        "email_verification_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_email_verification_tokens_user_id", "email_verification_tokens", ["user_id"]
    )

    op.create_table(
        "password_reset_tokens",
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
                "users.id", ondelete="CASCADE", name="fk_password_reset_tokens_user_id_users"
            ),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_password_reset_tokens_token_hash", "password_reset_tokens", ["token_hash"], unique=True
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])

    op.create_table(
        "refresh_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_refresh_tokens_user_id_users"),
            nullable=False,
        ),
        sa.Column("jti_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_refresh_tokens_jti_hash", "refresh_tokens", ["jti_hash"], unique=True)
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_table("refresh_tokens")
    op.drop_table("password_reset_tokens")
    op.drop_table("email_verification_tokens")
    op.drop_table("advocate_profiles")
    op.drop_table("users")

    bind = op.get_bind()
    _VERIFICATION_STATUS.drop(bind, checkfirst=False)
    _USER_ROLE.drop(bind, checkfirst=False)
