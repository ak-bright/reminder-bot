"""Creating, listing and changing reminders. The database side lives in db/reminder_store.py."""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from reminderbot.clock import Clock
from reminderbot.core.alerts import DEFAULT_OFFSETS, compute_alert_times
from reminderbot.core.models import ReminderKind

MAX_TITLE_LENGTH = 200
SNOOZE_SHORT = timedelta(hours=1)
SNOOZE_TOMORROW_AT = time(8, 0)  # "Snooze tomorrow" = 8:00 AM local, like a date with no time


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


@dataclass(frozen=True)
class ReminderInfo:
    """An active reminder, as shown in /list, /today and /week."""

    id: int
    title: str
    due_at_utc: datetime
    kind: ReminderKind

    def is_overdue(self, now: datetime) -> bool:
        return self.due_at_utc <= now


class ReminderStore(Protocol):
    """Every method takes the user_id, so a user can only ever touch their own reminders."""

    async def create(self, reminder: NewReminder) -> SavedReminder:
        """Save the reminder and its alerts together (all or nothing)."""
        ...

    async def delete(self, user_id: int, reminder_id: int) -> bool:
        """Mark the user's reminder deleted and cancel its pending alerts.
        False if it doesn't exist, isn't theirs, or is already deleted."""
        ...

    async def mark_done(self, user_id: int, reminder_id: int) -> ReminderInfo | None:
        """Mark it done and cancel its pending alerts. None if it isn't active."""
        ...

    async def get_active(self, user_id: int, reminder_id: int) -> ReminderInfo | None: ...

    async def list_active(
        self, user_id: int, due_before: datetime | None = None
    ) -> list[ReminderInfo]:
        """Active reminders, soonest first (so overdue ones come first)."""
        ...

    async def add_alert(
        self, user_id: int, reminder_id: int, send_at_utc: datetime
    ) -> ReminderInfo | None:
        """One extra alert (snooze). None if the reminder isn't active."""
        ...

    async def reschedule(
        self, user_id: int, reminder_id: int, due_at_utc: datetime, alert_times: list[datetime]
    ) -> SavedReminder | None:
        """New deadline: cancel the pending alerts and add these. None if not active."""
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
        offsets = _offsets_for(kind)
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

    async def done(self, user_id: int, reminder_id: int) -> ReminderInfo | None:
        return await self._store.mark_done(user_id, reminder_id)

    async def get(self, user_id: int, reminder_id: int) -> ReminderInfo | None:
        return await self._store.get_active(user_id, reminder_id)

    async def list_active(self, user_id: int) -> list[ReminderInfo]:
        return await self._store.list_active(user_id)

    async def list_due_today(self, user_id: int, timezone: str) -> list[ReminderInfo]:
        """Overdue ones, plus everything due before midnight in the user's timezone."""
        local_today = self._clock.now().astimezone(ZoneInfo(timezone)).date()
        midnight = datetime.combine(local_today + timedelta(days=1), time(0), ZoneInfo(timezone))
        return await self._store.list_active(user_id, due_before=midnight)

    async def list_next_days(self, user_id: int, days: int = 7) -> list[ReminderInfo]:
        """Overdue ones, plus everything due in the next `days` days."""
        return await self._store.list_active(
            user_id, due_before=self._clock.now() + timedelta(days=days)
        )

    async def snooze(
        self, user_id: int, reminder_id: int, timezone: str, until: str
    ) -> tuple[ReminderInfo, datetime] | None:
        """until="1h" or "tomorrow". Returns the reminder and the new alert time."""
        send_at = snooze_time(self._clock.now(), timezone, until)
        info = await self._store.add_alert(user_id, reminder_id, send_at)
        return None if info is None else (info, send_at)

    async def edit_due(
        self, user_id: int, reminder_id: int, due_at_utc: datetime
    ) -> SavedReminder | None:
        """Move the deadline. Alerts are worked out again, exactly as for a new reminder."""
        info = await self._store.get_active(user_id, reminder_id)
        if info is None:
            return None
        alert_times = compute_alert_times(
            due_at_utc, info.kind, self._clock.now(), _offsets_for(info.kind)
        )
        if not alert_times:
            raise ValueError("this moment has already passed")
        return await self._store.reschedule(user_id, reminder_id, due_at_utc, alert_times)


def snooze_time(now: datetime, timezone: str, until: str) -> datetime:
    if until == "1h":
        moment = now + SNOOZE_SHORT
    elif until == "tomorrow":
        tomorrow = now.astimezone(ZoneInfo(timezone)).date() + timedelta(days=1)
        moment = datetime.combine(tomorrow, SNOOZE_TOMORROW_AT, ZoneInfo(timezone))
    else:
        raise ValueError(f"unknown snooze {until!r}")
    # Whole minutes keep alert times tidy (and equal when compared later).
    return moment.replace(second=0, microsecond=0).astimezone(now.tzinfo)


def _offsets_for(kind: ReminderKind) -> list[int]:
    return DEFAULT_OFFSETS if kind == ReminderKind.DEADLINE else []
