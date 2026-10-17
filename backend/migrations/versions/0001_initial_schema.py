"""Initial schema: users, sessions, attempts and attempt items.

This matches the schema from before migrations were introduced, so existing
databases are stamped at this revision instead of having it applied.

Revision ID: 0001
Revises:
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UTC_DATETIME = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", UTC_DATETIME, nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", UTC_DATETIME, nullable=False),
        sa.Column("expires_at", UTC_DATETIME, nullable=False),
    )
    op.create_index("ix_sessions_token_hash", "sessions", ["token_hash"], unique=True)
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    op.create_table(
        "attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("test_id", sa.String(100), nullable=False),
        sa.Column("test_title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", UTC_DATETIME, nullable=False),
        sa.Column("deadline", UTC_DATETIME, nullable=False),
        sa.Column("submitted_at", UTC_DATETIME, nullable=True),
        sa.Column("timed_out", sa.Boolean(), nullable=False),
        sa.Column("current_index", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("max_score", sa.Float(), nullable=True),
        sa.Column("feedback_status", sa.String(20), nullable=True),
        sa.Column("feedback_json", sa.Text(), nullable=True),
        sa.Column("feedback_provider", sa.String(100), nullable=True),
        sa.Column("feedback_error", sa.Text(), nullable=True),
    )
    op.create_index("ix_attempts_status", "attempts", ["status"])
    op.create_index("ix_attempts_test_id", "attempts", ["test_id"])
    op.create_index("ix_attempts_user_id", "attempts", ["user_id"])

    op.create_table(
        "attempt_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("attempt_id", sa.String(36), sa.ForeignKey("attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.String(100), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("question_json", sa.Text(), nullable=False),
        sa.Column("answer_json", sa.Text(), nullable=True),
        sa.Column("answered_at", UTC_DATETIME, nullable=True),
        sa.Column("points", sa.Float(), nullable=True),
        sa.Column("max_points", sa.Float(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("grading_json", sa.Text(), nullable=True),
    )
    op.create_index("ix_attempt_items_attempt_id", "attempt_items", ["attempt_id"])
    op.create_index("ix_attempt_items_category", "attempt_items", ["category"])
    op.create_index("ix_attempt_items_question_id", "attempt_items", ["question_id"])


def downgrade() -> None:
    op.drop_table("attempt_items")
    op.drop_table("attempts")
    op.drop_table("sessions")
    op.drop_table("users")
