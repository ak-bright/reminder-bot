"""Initial schema: users, courses, reminders, alerts, conversation_memory, pending_actions.

Revision ID: 0001
Revises:
Create Date: 2026-11-19 04:25:52.567131
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("channel_user_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("onboarded", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("daily_digest_time", sa.Time(), nullable=True),
        sa.Column("last_digest_date", sa.Date(), nullable=True),
        sa.Column("ai_calls_today", sa.Integer(), nullable=False),
        sa.Column("ai_calls_date", sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint(
            "channel", "channel_user_id", name=op.f("uq_users_channel_channel_user_id")
        ),
    )
    op.create_table(
        "conversation_memory",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "role IN ('user', 'assistant')", name=op.f("ck_conversation_memory_role")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_conversation_memory_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversation_memory")),
    )
    with op.batch_alter_table("conversation_memory", schema=None) as batch_op:
        batch_op.create_index(
            "ix_conversation_memory_user_created", ["user_id", "created_at"], unique=False
        )

    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_courses_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_courses")),
        sa.UniqueConstraint("user_id", "code", name=op.f("uq_courses_user_id_code")),
    )
    with op.batch_alter_table("courses", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_courses_user_id"), ["user_id"], unique=False)

    op.create_table(
        "pending_actions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_pending_actions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pending_actions")),
    )
    with op.batch_alter_table("pending_actions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_pending_actions_user_id"), ["user_id"], unique=False)

    op.create_table(
        "reminders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("due_at_utc", sa.DateTime(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("alert_offsets", sa.JSON(), nullable=False),
        sa.Column("recurrence_rule", sa.String(length=200), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("kind IN ('deadline', 'at_time')", name=op.f("ck_reminders_kind")),
        sa.CheckConstraint(
            "status IN ('active', 'done', 'deleted')", name=op.f("ck_reminders_status")
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_reminders_course_id_courses"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_reminders_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reminders")),
    )
    with op.batch_alter_table("reminders", schema=None) as batch_op:
        batch_op.create_index(
            "ix_reminders_user_status_due", ["user_id", "status", "due_at_utc"], unique=False
        )

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reminder_id", sa.Integer(), nullable=False),
        sa.Column("send_at_utc", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'sending', 'sent', 'failed', 'cancelled')",
            name=op.f("ck_alerts_status"),
        ),
        sa.ForeignKeyConstraint(
            ["reminder_id"],
            ["reminders.id"],
            name=op.f("fk_alerts_reminder_id_reminders"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alerts")),
        sa.UniqueConstraint(
            "reminder_id", "send_at_utc", name=op.f("uq_alerts_reminder_id_send_at_utc")
        ),
    )
    with op.batch_alter_table("alerts", schema=None) as batch_op:
        batch_op.create_index("ix_alerts_status_send_at", ["status", "send_at_utc"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("alerts", schema=None) as batch_op:
        batch_op.drop_index("ix_alerts_status_send_at")

    op.drop_table("alerts")
    with op.batch_alter_table("reminders", schema=None) as batch_op:
        batch_op.drop_index("ix_reminders_user_status_due")

    op.drop_table("reminders")
    with op.batch_alter_table("pending_actions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_pending_actions_user_id"))

    op.drop_table("pending_actions")
    with op.batch_alter_table("courses", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_courses_user_id"))

    op.drop_table("courses")
    with op.batch_alter_table("conversation_memory", schema=None) as batch_op:
        batch_op.drop_index("ix_conversation_memory_user_created")

    op.drop_table("conversation_memory")
    op.drop_table("users")
