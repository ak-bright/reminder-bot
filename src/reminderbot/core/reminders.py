"""Creating and deleting reminders. The database side lives in db/reminder_store.py."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from reminderbot.clock import Clock
from reminderbot.core.alerts import DEFAULT_OFFSETS, compute_alert_times
from reminderbot.core.models import ReminderKind

MAX_TITLE_LENGTH = 200


@dataclass(frozen=True)
class NewReminder:
    user_id: int
    title: str
    due_at_utc: datetime
    kind: ReminderKind
    alert_offsets: list[int]
    alert_times: list[datetime]
    source_text: str | None = None


@dataclass(frozen=True)
class SavedReminder:
    id: int
    title: str
    due_at_utc: datetime
    kind: ReminderKind
    alert_times: list[datetime]


class ReminderStore(Protocol):
    async def create(self, reminder: NewReminder) -> SavedReminder:
        """Save the reminder and its alerts together (all or nothing)."""
        ...

    async def delete(self, user_id: int, reminder_id: int) -> bool:
        """Mark the user's reminder deleted and cancel its pending alerts.
        False if it doesn't exist, isn't theirs, or is already deleted."""
        ...


class ReminderService:
    def __init__(self, store: ReminderStore, clock: Clock) -> None:
        self._store = store
        self._clock = clock

    async def create(
        self,
        user_id: int,
        title: str,
        due_at_utc: datetime,
        kind: ReminderKind,
        source_text: str | None = None,
    ) -> SavedReminder:
        if not title.strip() or len(title) > MAX_TITLE_LENGTH:
            raise ValueError("title must be 1-200 characters")
        offsets = DEFAULT_OFFSETS if kind == ReminderKind.DEADLINE else []
        alert_times = compute_alert_times(due_at_utc, kind, self._clock.now(), offsets)
        if not alert_times:
            raise ValueError("this moment has already passed")
        return await self._store.create(
            NewReminder(
                user_id=user_id,
                title=title.strip(),
                due_at_utc=due_at_utc,
                kind=kind,
                alert_offsets=offsets,
                alert_times=alert_times,
                source_text=source_text,
            )
        )

    async def delete(self, user_id: int, reminder_id: int) -> bool:
        return await self._store.delete(user_id, reminder_id)
