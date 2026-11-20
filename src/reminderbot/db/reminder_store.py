"""SqlReminderStore: the database version of core's ReminderStore."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reminderbot.core.models import ReminderKind, ReminderStatus
from reminderbot.core.reminders import NewReminder, ReminderInfo, SavedReminder
from reminderbot.db.models import Reminder
from reminderbot.db.repositories import AlertRepo, ReminderRepo


class SqlReminderStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create(self, reminder: NewReminder) -> SavedReminder:
        async with self._session_factory() as session:
            row = await ReminderRepo(session).add(
                reminder.user_id,
                reminder.title,
                reminder.due_at_utc,
                kind=reminder.kind,
                alert_offsets=reminder.alert_offsets,
                source_text=reminder.source_text,
            )
            await AlertRepo(session).add_many(row.id, reminder.alert_times)
            await session.commit()  # reminder and alerts are saved together
            return _saved(row, reminder.alert_times)

    async def delete(self, user_id: int, reminder_id: int) -> bool:
        async with self._session_factory() as session:
            reminders = ReminderRepo(session)
            row = await reminders.get_for_user(user_id, reminder_id)
            if row is None or row.status == ReminderStatus.DELETED:
                return False
            await reminders.set_status(row, ReminderStatus.DELETED)
            await AlertRepo(session).cancel_pending(row.id)
            await session.commit()
            return True

    async def mark_done(self, user_id: int, reminder_id: int) -> ReminderInfo | None:
        async with self._session_factory() as session:
            row = await _active(session, user_id, reminder_id)
            if row is None:
                return None
            await ReminderRepo(session).set_status(row, ReminderStatus.DONE)
            await AlertRepo(session).cancel_pending(row.id)  # no more alerts for it
            await session.commit()
            return _info(row)

    async def get_active(self, user_id: int, reminder_id: int) -> ReminderInfo | None:
        async with self._session_factory() as session:
            row = await _active(session, user_id, reminder_id)
            return None if row is None else _info(row)

    async def list_active(
        self, user_id: int, due_before: datetime | None = None
    ) -> list[ReminderInfo]:
        async with self._session_factory() as session:
            rows = await ReminderRepo(session).list_active(user_id, due_before=due_before)
            return [_info(row) for row in rows]

    async def add_alert(
        self, user_id: int, reminder_id: int, send_at_utc: datetime
    ) -> ReminderInfo | None:
        async with self._session_factory() as session:
            row = await _active(session, user_id, reminder_id)
            if row is None:
                return None
            await AlertRepo(session).schedule(row.id, send_at_utc)
            await session.commit()
            return _info(row)

    async def reschedule(
        self, user_id: int, reminder_id: int, due_at_utc: datetime, alert_times: list[datetime]
    ) -> SavedReminder | None:
        async with self._session_factory() as session:
            row = await _active(session, user_id, reminder_id)
            if row is None:
                return None
            row.due_at_utc = due_at_utc
            alerts = AlertRepo(session)
            await alerts.cancel_pending(row.id)  # the old alerts are for the old deadline
            for when in alert_times:
                await alerts.schedule(row.id, when)
            await session.commit()
            return _saved(row, alert_times)


async def _active(session: AsyncSession, user_id: int, reminder_id: int) -> Reminder | None:
    """The user's reminder, only if it is still active (not done or deleted)."""
    row = await ReminderRepo(session).get_for_user(user_id, reminder_id)
    return row if row is not None and row.status == ReminderStatus.ACTIVE else None


def _info(row: Reminder) -> ReminderInfo:
    return ReminderInfo(row.id, row.title, row.due_at_utc, ReminderKind(row.kind))


def _saved(row: Reminder, alert_times: list[datetime]) -> SavedReminder:
    return SavedReminder(
        id=row.id,
        title=row.title,
        due_at_utc=row.due_at_utc,
        kind=ReminderKind(row.kind),
        alert_times=list(alert_times),
    )
