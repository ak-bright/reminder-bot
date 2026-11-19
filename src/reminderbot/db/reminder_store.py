"""SqlReminderStore: the database version of core's ReminderStore."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reminderbot.core.models import ReminderKind, ReminderStatus
from reminderbot.core.reminders import NewReminder, SavedReminder
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
            return SavedReminder(
                id=row.id,
                title=row.title,
                due_at_utc=row.due_at_utc,
                kind=ReminderKind(row.kind),
                alert_times=list(reminder.alert_times),
            )

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
