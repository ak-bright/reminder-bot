"""Repositories: the only place that writes SQL queries.

Each repository works inside a session the caller opens. The caller decides when
to commit, so several repository calls can be saved together (all or nothing):

    async with session_factory() as session:
        reminder = await ReminderRepo(session).add(...)
        await AlertRepo(session).add_many(reminder.id, [...])
        await session.commit()
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from reminderbot.core.models import AlertStatus, ReminderKind, ReminderStatus
from reminderbot.db.models import (
    Alert,
    ConversationMessage,
    Course,
    PendingAction,
    Reminder,
    User,
)


class UserRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_identity(self, channel: str, channel_user_id: str) -> User | None:
        query = select(User).where(User.channel == channel, User.channel_user_id == channel_user_id)
        return await self._session.scalar(query)

    async def add(self, user: User) -> User:
        self._session.add(user)
        await self._session.flush()  # sends the INSERT now, so user.id is filled in
        return user


class CourseRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user_id: int, name: str, code: str | None = None) -> Course:
        course = Course(user_id=user_id, name=name, code=code)
        self._session.add(course)
        await self._session.flush()
        return course

    async def list_for_user(self, user_id: int) -> Sequence[Course]:
        query = select(Course).where(Course.user_id == user_id).order_by(Course.name)
        return (await self._session.scalars(query)).all()


class ReminderRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        user_id: int,
        title: str,
        due_at_utc: datetime,
        *,
        kind: ReminderKind = ReminderKind.DEADLINE,
        alert_offsets: list[int] | None = None,
        notes: str | None = None,
        course_id: int | None = None,
        source_text: str | None = None,
    ) -> Reminder:
        reminder = Reminder(
            user_id=user_id,
            title=title,
            due_at_utc=due_at_utc,
            kind=kind,
            alert_offsets=alert_offsets or [],
            notes=notes,
            course_id=course_id,
            source_text=source_text,
        )
        self._session.add(reminder)
        await self._session.flush()
        return reminder

    async def get(self, reminder_id: int) -> Reminder | None:
        return await self._session.get(Reminder, reminder_id)

    async def get_for_user(self, user_id: int, reminder_id: int) -> Reminder | None:
        """Like get(), but only if the reminder belongs to this user (stops users
        from touching each other's reminders by guessing ids)."""
        query = select(Reminder).where(Reminder.id == reminder_id, Reminder.user_id == user_id)
        return await self._session.scalar(query)

    async def list_active(
        self,
        user_id: int,
        *,
        due_from: datetime | None = None,
        due_before: datetime | None = None,
    ) -> Sequence[Reminder]:
        """Active reminders, soonest first, optionally within [due_from, due_before)."""
        query = select(Reminder).where(
            Reminder.user_id == user_id, Reminder.status == ReminderStatus.ACTIVE
        )
        if due_from is not None:
            query = query.where(Reminder.due_at_utc >= due_from)
        if due_before is not None:
            query = query.where(Reminder.due_at_utc < due_before)
        return (await self._session.scalars(query.order_by(Reminder.due_at_utc))).all()

    async def set_status(self, reminder: Reminder, status: ReminderStatus) -> None:
        reminder.status = status
        await self._session.flush()


class AlertRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_many(self, reminder_id: int, send_times: list[datetime]) -> list[Alert]:
        alerts = [Alert(reminder_id=reminder_id, send_at_utc=when) for when in send_times]
        self._session.add_all(alerts)
        await self._session.flush()
        return alerts

    async def list_for_reminder(self, reminder_id: int) -> Sequence[Alert]:
        query = select(Alert).where(Alert.reminder_id == reminder_id).order_by(Alert.send_at_utc)
        return (await self._session.scalars(query)).all()

    async def cancel_pending(self, reminder_id: int) -> int:
        """Cancel alerts that haven't gone out yet (e.g. the reminder is done).
        Returns how many were cancelled."""
        result = await self._session.execute(
            update(Alert)
            .where(Alert.reminder_id == reminder_id, Alert.status == AlertStatus.PENDING)
            .values(status=AlertStatus.CANCELLED)
        )
        return result.rowcount

    # --- used by the scheduler (scheduler/loop.py) ---

    async def due_ids(self, now: datetime, stale_before: datetime, limit: int = 100) -> list[int]:
        """Ids of alerts ready to send, oldest first. See _ready_to_send()."""
        query = (
            select(Alert.id)
            .where(_ready_to_send(now, stale_before))
            .order_by(Alert.send_at_utc)
            .limit(limit)
        )
        return list((await self._session.scalars(query)).all())

    async def claim(self, alert_id: int, now: datetime, stale_before: datetime) -> bool:
        """Mark the alert `sending` if it is still ready to send. True if we got it.

        This is one conditional UPDATE, so if two schedulers try at the same time
        only one changes the row; the other sees 0 rows changed and skips it.
        Each claim counts as an attempt, so a crash loop can't retry forever.
        """
        result = await self._session.execute(
            update(Alert)
            .where(Alert.id == alert_id, _ready_to_send(now, stale_before))
            .values(status=AlertStatus.SENDING, claimed_at=now, attempts=Alert.attempts + 1)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    async def get_for_sending(self, alert_id: int) -> Alert | None:
        """The alert with its reminder and the reminder's user loaded."""
        query = (
            select(Alert)
            .where(Alert.id == alert_id)
            .options(selectinload(Alert.reminder).selectinload(Reminder.user))
        )
        return await self._session.scalar(query)

    async def mark_sent(self, alert: Alert, now: datetime) -> None:
        alert.status = AlertStatus.SENT
        alert.sent_at = now
        alert.last_error = None
        await self._session.flush()

    async def mark_cancelled(self, alert: Alert) -> None:
        alert.status = AlertStatus.CANCELLED
        await self._session.flush()

    async def record_failure(self, alert: Alert, error: str, retry_at: datetime | None) -> None:
        """Back to `pending` to try again at `retry_at`, or `failed` if retry_at is None."""
        alert.last_error = error[:500]
        if retry_at is None:
            alert.status = AlertStatus.FAILED
        else:
            alert.status = AlertStatus.PENDING
            alert.next_attempt_at = retry_at
        await self._session.flush()


def _ready_to_send(now: datetime, stale_before: datetime):
    """SQL condition for "this alert should be sent now":
    - pending, its time has come, and any retry wait is over; or
    - stuck in `sending` since before `stale_before` (the sender probably crashed)."""
    pending_and_due = (
        (Alert.status == AlertStatus.PENDING)
        & (Alert.send_at_utc <= now)
        & (Alert.next_attempt_at.is_(None) | (Alert.next_attempt_at <= now))
    )
    stuck = (Alert.status == AlertStatus.SENDING) & (Alert.claimed_at <= stale_before)
    return pending_and_due | stuck


class ConversationRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user_id: int, role: str, content: str) -> None:
        self._session.add(ConversationMessage(user_id=user_id, role=role, content=content))
        await self._session.flush()

    async def recent(self, user_id: int, limit: int = 10) -> list[ConversationMessage]:
        """The last `limit` messages, oldest first (the order the AI expects)."""
        query = (
            select(ConversationMessage)
            .where(ConversationMessage.user_id == user_id)
            .order_by(ConversationMessage.id.desc())
            .limit(limit)
        )
        newest_first = (await self._session.scalars(query)).all()
        return list(reversed(newest_first))

    async def trim(self, user_id: int, keep: int = 10) -> None:
        """Delete everything except the newest `keep` messages."""
        keep_ids = (
            select(ConversationMessage.id)
            .where(ConversationMessage.user_id == user_id)
            .order_by(ConversationMessage.id.desc())
            .limit(keep)
        )
        await self._session.execute(
            delete(ConversationMessage).where(
                ConversationMessage.user_id == user_id,
                ConversationMessage.id.not_in(keep_ids),
            )
        )


class PendingActionRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        user_id: int,
        kind: str,
        payload: dict[str, Any] | None = None,
        expires_at: datetime | None = None,
    ) -> PendingAction:
        action = PendingAction(
            user_id=user_id, kind=kind, payload=payload or {}, expires_at=expires_at
        )
        self._session.add(action)
        await self._session.flush()
        return action

    async def get_for_user(
        self, user_id: int, action_id: int, now: datetime
    ) -> PendingAction | None:
        """The action, if it belongs to this user and hasn't expired."""
        query = select(PendingAction).where(
            PendingAction.id == action_id,
            PendingAction.user_id == user_id,
            _not_expired(now),
        )
        return await self._session.scalar(query)

    async def find(self, user_id: int, kind: str, now: datetime) -> PendingAction | None:
        """The newest unexpired action of this kind for the user, if any."""
        query = (
            select(PendingAction)
            .where(PendingAction.user_id == user_id, PendingAction.kind == kind, _not_expired(now))
            .order_by(PendingAction.id.desc())
            .limit(1)
        )
        return await self._session.scalar(query)

    async def delete_kind(self, user_id: int, kind: str) -> None:
        await self._session.execute(
            delete(PendingAction).where(
                PendingAction.user_id == user_id, PendingAction.kind == kind
            )
        )

    async def delete_expired(self, now: datetime) -> int:
        result = await self._session.execute(
            delete(PendingAction).where(PendingAction.expires_at <= now)
        )
        return result.rowcount


def _not_expired(now: datetime):
    return (PendingAction.expires_at.is_(None)) | (PendingAction.expires_at > now)
