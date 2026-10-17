"""Roles, attempt modes, integrity events, certificates and company invites.

Revision ID: 0003
Revises: 0002
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UTC_DATETIME = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "invites",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("candidate_name", sa.String(100), nullable=False),
        sa.Column("company", sa.String(120), nullable=False),
        sa.Column("test_id", sa.String(100), nullable=False),
        sa.Column("test_title", sa.String(200), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", UTC_DATETIME, nullable=False),
        sa.Column("expires_at", UTC_DATETIME, nullable=False),
        sa.Column("opened_at", UTC_DATETIME, nullable=True),
        sa.Column("cancelled_at", UTC_DATETIME, nullable=True),
    )
    op.create_index("ix_invites_email", "invites", ["email"])
    op.create_index("ix_invites_token_hash", "invites", ["token_hash"], unique=True)

    op.create_table(
        "certificates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_id", sa.String(36), sa.ForeignKey("attempts.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("test_id", sa.String(100), nullable=False),
        sa.Column("test_title", sa.String(200), nullable=False),
        sa.Column("percent", sa.Float(), nullable=False),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", UTC_DATETIME, nullable=False),
        sa.Column("issued_at", UTC_DATETIME, nullable=True),
        sa.Column("reviewed_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
    )
    op.create_index("ix_certificates_code", "certificates", ["code"], unique=True)
    op.create_index("ix_certificates_status", "certificates", ["status"])
    op.create_index("ix_certificates_test_id", "certificates", ["test_id"])
    op.create_index("ix_certificates_user_id", "certificates", ["user_id"])

    op.create_table(
        "integrity_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("attempt_id", sa.String(36), sa.ForeignKey("attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("occurred_at", UTC_DATETIME, nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("detail", sa.String(200), nullable=True),
    )
    op.create_index("ix_integrity_events_attempt_id", "integrity_events", ["attempt_id"])

    # Batch mode so SQLite can add the foreign key (it rebuilds the table).
    with op.batch_alter_table("attempts") as batch:
        batch.add_column(sa.Column("mode", sa.String(20), server_default="practice", nullable=False))
        batch.add_column(sa.Column("invite_id", sa.String(36), nullable=True))
        batch.create_index("ix_attempts_mode", ["mode"])
        batch.create_index("ix_attempts_invite_id", ["invite_id"])
        batch.create_foreign_key("fk_attempts_invite_id", "invites", ["invite_id"], ["id"], ondelete="SET NULL")

    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("role", sa.String(20), server_default="user", nullable=False))
        batch.add_column(sa.Column("disabled_at", UTC_DATETIME, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("disabled_at")
        batch.drop_column("role")
    with op.batch_alter_table("attempts") as batch:
        batch.drop_constraint("fk_attempts_invite_id", type_="foreignkey")
        batch.drop_index("ix_attempts_invite_id")
        batch.drop_index("ix_attempts_mode")
        batch.drop_column("invite_id")
        batch.drop_column("mode")
    op.drop_table("integrity_events")
    op.drop_table("certificates")
    op.drop_table("invites")
