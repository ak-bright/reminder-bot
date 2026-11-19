"""SQLAlchemy ORM tables. All datetimes are timezone-aware UTC (see UTCDateTime).

Status and kind columns hold the string values of the enums in core/models.py,
and a CHECK constraint stops anything else from being stored.
"""

from datetime import date, datetime, time
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from reminderbot.core.models import AlertStatus, ReminderKind, ReminderStatus
from reminderbot.db.base import Base, UTCDateTime, utc_now


def _one_of(column: str, enum: type) -> str:
    """SQL for a CHECK constraint, e.g. "status IN ('active', 'done')"."""
    values = ", ".join(f"'{member.value}'" for member in enum)
    return f"{column} IN ({values})"


class User(Base):
    __tablename__ = "users"
    # One row per person per chat app (CLAUDE.md rule 2).
    __table_args__ = (UniqueConstraint("channel", "channel_user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(20))
    channel_user_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str | None] = mapped_column(String(100))
    timezone: Mapped[str] = mapped_column(String(64))
    language: Mapped[str] = mapped_column(String(8), default="en")
    onboarded: Mapped[bool] = mapped_column(default=False)  # timezone chosen at least once
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    # Daily digest (M7): local time of day to send it, and the last local date it was sent.
    daily_digest_time: Mapped[time | None] = mapped_column(Time())
    last_digest_date: Mapped[date | None] = mapped_column(Date())
    # AI limit (M6): the counter resets when ai_calls_date is not today.
    ai_calls_today: Mapped[int] = mapped_column(Integer, default=0)
    ai_calls_date: Mapped[date | None] = mapped_column(Date())

    reminders: Mapped[list["Reminder"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (UniqueConstraint("user_id", "code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    code: Mapped[str | None] = mapped_column(String(20))  # e.g. "DCIT 201"


class Reminder(Base):
    __tablename__ = "reminders"
    __table_args__ = (
        CheckConstraint(_one_of("kind", ReminderKind), name="kind"),
        CheckConstraint(_one_of("status", ReminderStatus), name="status"),
        Index("ix_reminders_user_status_due", "user_id", "status", "due_at_utc"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    due_at_utc: Mapped[datetime] = mapped_column(UTCDateTime())
    kind: Mapped[str] = mapped_column(String(16), default=ReminderKind.DEADLINE)
    # Minutes before the deadline, e.g. [1440, 180, 30]. Kept so /edit can recompute alerts.
    alert_offsets: Mapped[list[int]] = mapped_column(JSON, default=list)
    recurrence_rule: Mapped[str | None] = mapped_column(String(200))  # RFC 5545 RRULE (M7)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default=ReminderStatus.ACTIVE)
    source_text: Mapped[str | None] = mapped_column(Text)  # what the user typed (private!)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    user: Mapped[User] = relationship(back_populates="reminders")
    alerts: Mapped[list["Alert"]] = relationship(
        back_populates="reminder", cascade="all, delete-orphan", passive_deletes=True
    )


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        # The same reminder never gets two alerts at the same moment.
        UniqueConstraint("reminder_id", "send_at_utc"),
        CheckConstraint(_one_of("status", AlertStatus), name="status"),
        # The scheduler's query: "status = pending AND send_at_utc <= now".
        Index("ix_alerts_status_send_at", "status", "send_at_utc"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    reminder_id: Mapped[int] = mapped_column(ForeignKey("reminders.id", ondelete="CASCADE"))
    send_at_utc: Mapped[datetime] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(16), default=AlertStatus.PENDING)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # Retry bookkeeping for the scheduler (M3).
    next_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    claimed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_error: Mapped[str | None] = mapped_column(String(500))

    reminder: Mapped[Reminder] = relationship(back_populates="alerts")


class ConversationMessage(Base):
    """Short rolling chat history for the AI assistant (M6)."""

    __tablename__ = "conversation_memory"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="role"),
        Index("ix_conversation_memory_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class PendingAction(Base):
    """Something the bot is waiting for the user to answer.

    Telegram buttons can only carry 64 bytes, so a button holds just this row's id
    and the real state lives in `payload`. Because it's in the database, an
    unanswered question survives a restart.
    """

    __tablename__ = "pending_actions"
    # No CHECK on `kind`: new kinds arrive in later milestones (PendingKind in core/models.py),
    # and we don't want a migration for each one.

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())  # None = never
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
