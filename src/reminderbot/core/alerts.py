"""When to send a reminder's alerts (CLAUDE.md rule 4). Pure functions, no I/O."""

from datetime import datetime, timedelta

from reminderbot.core.models import ReminderKind

# Minutes before the deadline: 1 day, 3 hours, 30 minutes.
DEFAULT_OFFSETS = [24 * 60, 3 * 60, 30]

# A deadline closer than this gets one "last call" alert instead of the offsets.
SHORT_NOTICE = timedelta(minutes=30)
LAST_CALL = timedelta(minutes=5)


def compute_alert_times(
    due_at_utc: datetime,
    kind: ReminderKind,
    now: datetime,
    offsets: list[int] | None = None,
) -> list[datetime]:
    """Return the alert times, soonest first. Empty if the moment has already passed.

    deadline: one alert per offset before the deadline, skipping offsets already in the
              past. If the deadline is under 30 min away, a single alert at
              max(now, deadline - 5 min) instead.
    at_time:  one alert at exactly that moment ("remind me in 2 hours to ...").
    """
    if due_at_utc <= now:
        return []
    if kind == ReminderKind.AT_TIME:
        return [due_at_utc]

    if due_at_utc - now < SHORT_NOTICE:
        return [max(now, due_at_utc - LAST_CALL)]

    offsets = DEFAULT_OFFSETS if offsets is None else offsets
    # ">= now": an alert due exactly now is still sent (the next scheduler tick picks
    # it up), so a deadline exactly 30 min away still gets its 30-minute alert.
    times = {due_at_utc - timedelta(minutes=m) for m in offsets}
    return sorted(when for when in times if when >= now)
