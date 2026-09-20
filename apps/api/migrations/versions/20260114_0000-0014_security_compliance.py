"""audit_logs (append-only), organizations + tenant columns, users.deleted_at - Phase 13

Matches ``app/models/audit.py``, ``organization.py`` and the new columns on ``users`` and
``legal_documents``. The audit table is made append-only with a trigger: UPDATE, DELETE and TRUNCATE
all raise, so history can't be rewritten by the application (or a bug in it).

Revision ID: 0014_security_compliance
Revises: 0013_matter_calls
Create Date: 2026-01-14 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_security_compliance"
down_revision: str | None = "0013_matter_calls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- organisations (the tenant boundary) --------------------------------------------------
    op.create_table(
        "organizations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(200), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "organizations.id", ondelete="SET NULL", name="fk_users_organization_id_organizations"
            ),
        ),
    )
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.create_index("ix_users_organization_id", "users", ["organization_id"])
    # NULL = a public document, visible to everyone; set = private to that organisation.
    op.add_column(
        "legal_documents",
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "organizations.id",
                ondelete="CASCADE",
                name="fk_legal_documents_organization_id_organizations",
            ),
        ),
    )
    op.create_index("ix_legal_documents_organization_id", "legal_documents", ["organization_id"])

    # ---- audit log ----------------------------------------------------------------------------
    op.create_table(
        "audit_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True)),
        sa.Column("actor_role", sa.String(20)),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("target_type", sa.String(30)),
        sa.Column("target_id", sa.String(64)),
        sa.Column("detail", postgresql.JSONB()),
        sa.Column("ip", sa.String(45)),
        sa.Column("request_id", sa.String(64)),
    )
    op.create_index("ix_audit_logs_occurred_at", "audit_logs", ["occurred_at"])
    op.create_index("ix_audit_logs_actor", "audit_logs", ["actor_id", "occurred_at"])
    op.create_index("ix_audit_logs_target", "audit_logs", ["target_type", "target_id"])

    op.execute(
        """
        CREATE FUNCTION audit_logs_block_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs is append-only' USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_logs_no_update_delete
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION audit_logs_block_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_logs_no_truncate
        BEFORE TRUNCATE ON audit_logs
        FOR EACH STATEMENT EXECUTE FUNCTION audit_logs_block_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_logs_no_truncate ON audit_logs")
    op.execute("DROP TRIGGER IF EXISTS audit_logs_no_update_delete ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS audit_logs_block_mutation()")
    op.drop_index("ix_audit_logs_target", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor", table_name="audit_logs")
    op.drop_index("ix_audit_logs_occurred_at", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_legal_documents_organization_id", table_name="legal_documents")
    op.drop_column("legal_documents", "organization_id")
    op.drop_index("ix_users_organization_id", table_name="users")
    op.drop_column("users", "deleted_at")
    op.drop_column("users", "organization_id")
    op.drop_table("organizations")
