"""The strict `/remind <when> | <what>` format (M3, before the AI parser exists).

Accepted <when> forms (times are 24-hour, in the user's own timezone):
    2026-11-21 17:00      a date and a time
    2026-11-21            a date only -> 8:00 AM, and we say so (CLAUDE.md rule 5)
    today 17:00
    tomorrow 17:00
    tomorrow              -> 8:00 AM
    in 30m / in 2h / in 3d   relative; this is an `at_time` reminder (one alert then)
Dates and times give a `deadline` reminder (alerts before it).
"""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from reminderbot.core.models import ReminderKind

DEFAULT_TIME = time(8, 0)
MAX_RELATIVE = timedelta(days=366)

_DATE = r"(?P<date>\d{4}-\d{2}-\d{2})"
_DAY_WORD = r"(?P<day>today|tomorrow)"
_TIME = r"(?:\s+(?P<time>\d{1,2}:\d{2}))?"
_ABSOLUTE = re.compile(rf"(?:{_DATE}|{_DAY_WORD}){_TIME}", re.IGNORECASE)
_RELATIVE = re.compile(r"in\s+(?P<amount>\d{1,4})\s*(?P<unit>m|h|d)", re.IGNORECASE)
_UNITS = {"m": "minutes", "h": "hours", "d": "days"}


@dataclass(frozen=True)
class ParsedWhen:
    due_at_utc: datetime
    kind: ReminderKind
    time_defaulted: bool  # True if no time was given and we used 8:00 AM


class TimeParseError(ValueError):
    """`reason` is a strings.py key explaining what was wrong."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def split_remind_args(args: str) -> tuple[str, str]:
    """'tomorrow 17:00 | DS essay' -> ('tomorrow 17:00', 'DS essay')."""
    when, bar, what = args.partition("|")
    if not bar or not when.strip() or not what.strip():
        raise TimeParseError("remind.usage")
    return when.strip(), what.strip()


def parse_when(text: str, timezone: str, now: datetime) -> ParsedWhen:
    """Turn the <when> part into a UTC moment. `now` is UTC (from the Clock)."""
    cleaned = " ".join(text.split())  # collapse extra spaces

    relative = _RELATIVE.fullmatch(cleaned)
    if relative:
        amount = int(relative["amount"])
        delta = timedelta(**{_UNITS[relative["unit"].lower()]: amount})
        if amount == 0 or delta > MAX_RELATIVE:
            raise TimeParseError("remind.bad_when")
        return ParsedWhen(now + delta, ReminderKind.AT_TIME, time_defaulted=False)

    absolute = _ABSOLUTE.fullmatch(cleaned)
    if not absolute:
        raise TimeParseError("remind.bad_when")

    zone = ZoneInfo(timezone)
    today_local = now.astimezone(zone).date()
    if absolute["date"]:
        try:
            day = date.fromisoformat(absolute["date"])
        except ValueError:  # e.g. 2026-02-30
            raise TimeParseError("remind.bad_when") from None
    else:
        extra_days = 1 if absolute["day"].lower() == "tomorrow" else 0
        day = today_local + timedelta(days=extra_days)

    if absolute["time"]:
        hour, minute = (int(part) for part in absolute["time"].split(":"))
        if hour > 23 or minute > 59:
            raise TimeParseError("remind.bad_when")
        at, defaulted = time(hour, minute), False
    else:
        at, defaulted = DEFAULT_TIME, True

    # Build the local time, then convert to UTC for storage.
    due = datetime.combine(day, at, tzinfo=zone).astimezone(UTC)
    if due <= now:
        raise TimeParseError("remind.past")
    return ParsedWhen(due, ReminderKind.DEADLINE, time_defaulted=defaulted)
