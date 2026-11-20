"""Turn a structured "when" (from the AI parser) into an exact UTC moment.

The AI only *describes* the time ("weekday=friday, time=17:00"). All date maths
happens here, in plain Python anchored to the user's local "now", so it is
deterministic and fully tested. When the description is ambiguous we don't guess:
we return an `Ask` with the possible answers, and the bot asks the user (CLAUDE.md rule 5).
"""

import calendar
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from reminderbot.core.formatting import format_datetime

DEFAULT_TIME = time(8, 0)  # a date with no time -> 8:00 AM, and we say so
# "tomorrow morning" etc. CLAUDE.md: morning = 8:00.
PART_OF_DAY_TIMES = {
    "morning": time(8, 0),
    "afternoon": time(14, 0),
    "evening": time(18, 0),
    "night": time(20, 0),
}
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MAX_RELATIVE_MINUTES = 366 * 24 * 60  # "in 2 years" is almost certainly a mistake

Weekday = Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DayWord = Literal["today", "tomorrow", "day_after_tomorrow", "end_of_month", "next_week"]


class WhenSpec(BaseModel):
    """A description of a moment, exactly as the AI parser fills it in.

    The AI fills in only what the user actually said and leaves the rest null.
    (This text and the field descriptions are sent to the model in the JSON schema.)
    """

    relative_minutes: int | None = Field(
        description='For "in 2 hours" / "in 30 min" / "in 3 days": the total minutes from now.'
    )
    day_word: DayWord | None = Field(
        description='"end_of_month" for "end of the month" / "month end". '
        '"day_after_tomorrow" for "day after tomorrow". '
        '"next_week" only when no weekday is given ("due next week").'
    )
    weekday: Weekday | None = Field(description='A named day, e.g. "friday" for "Friday".')
    weekday_modifier: Literal["none", "this", "next"] = Field(
        description='"next" for "next Friday", "this" for "this Friday", otherwise "none".'
    )
    month: int | None = Field(description="1-12, only if the user named a month.")
    day: int | None = Field(description="1-31, only if the user named a calendar date.")
    year: int | None = Field(description="Only if the user wrote the year.")
    time: str | None = Field(
        description='24-hour "HH:MM" if a clock time was given. 5pm -> "17:00".'
    )
    part_of_day: Literal["morning", "afternoon", "evening", "night"] | None = Field(
        description='"tonight" -> "night". Leave empty if an exact time was given.'
    )


@dataclass(frozen=True)
class Resolved:
    due_at_utc: datetime
    time_defaulted: bool = False  # True when we used 8:00 AM because no time was given


@dataclass(frozen=True)
class Ask:
    """We need the user to choose. `question_key` is a strings.py key."""

    question_key: str
    args: dict[str, str] = field(default_factory=dict)
    choices: list[Resolved] = field(default_factory=list)  # empty = they must type an answer


def resolve(spec: WhenSpec, timezone: str, now_utc: datetime) -> Resolved | Ask:
    zone = ZoneInfo(timezone)
    now_local = now_utc.astimezone(zone)

    if spec.relative_minutes is not None:
        if not 0 < spec.relative_minutes <= MAX_RELATIVE_MINUTES:
            return Ask("clarify.when")
        return Resolved(now_utc + timedelta(minutes=spec.relative_minutes))

    try:
        at = _time_of_day(spec)
        days = _candidate_days(spec, now_local.date())
    except _Unclear:
        return Ask("clarify.when")
    defaulted = at is None
    clock_time = at or DEFAULT_TIME

    def make(day: date) -> Resolved:
        # Build the local wall-clock time, then convert to UTC for storage.
        local = datetime.combine(day, clock_time, tzinfo=zone)
        return Resolved(local.astimezone(UTC), time_defaulted=defaulted)

    today = now_local.date()
    if days is None:
        # No day at all. A bare time ("at 6pm") means the next time it's that o'clock.
        if at is None:
            return Ask("clarify.when")
        first = make(today)
        return first if first.due_at_utc > now_utc else make(today + timedelta(days=1))
    if isinstance(days, _Pick):
        return _with_choices(days, make, now_utc)

    result = make(days)
    if result.due_at_utc <= now_utc:
        return Ask("clarify.past")
    return result


# --- helpers ------------------------------------------------------------------


class _Unclear(Exception):
    """The AI gave something we can't use (e.g. time "25:99"), so we ask the user."""


def _time_of_day(spec: WhenSpec) -> time | None:
    """The clock time asked for, or None if none was given."""
    if spec.time:
        try:
            hour, minute = (int(part) for part in spec.time.strip().split(":"))
            return time(hour, minute)
        except ValueError:
            raise _Unclear from None
    if spec.part_of_day:
        return PART_OF_DAY_TIMES[spec.part_of_day]
    return None


@dataclass(frozen=True)
class _Pick:
    """Internal: several possible days. Turned into an Ask with real times later."""

    question_key: str
    args: dict[str, str]
    days: list[date]


def _candidate_days(spec: WhenSpec, today: date) -> date | _Pick | None:
    """Which day is meant. None means the user gave no day at all."""
    if spec.month is not None or spec.day is not None:
        return _calendar_date(spec, today)

    if spec.weekday is not None:
        return _weekday(spec, today)

    match spec.day_word:
        case "today":
            return today
        case "tomorrow":
            return today + timedelta(days=1)
        case "day_after_tomorrow":
            return today + timedelta(days=2)
        case "end_of_month":
            last = calendar.monthrange(today.year, today.month)[1]
            return today.replace(day=last)
        case "next_week":
            # "Due next week" doesn't say which day, so offer Monday to Friday.
            monday = _start_of_week(today) + timedelta(days=7)
            return _Pick("clarify.which_day", {}, [monday + timedelta(days=i) for i in range(5)])
    return None


def _calendar_date(spec: WhenSpec, today: date) -> date:
    if spec.day is None:
        raise _Unclear  # a month alone ("in December") is too vague
    try:
        if spec.month is None:
            # "On the 25th": this month, or next month if the 25th has gone.
            candidate = today.replace(day=spec.day)
            if candidate < today:
                year, month = (
                    (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
                )
                candidate = date(year, month, spec.day)
            return candidate
        if spec.year is not None:
            return date(spec.year, spec.month, spec.day)
        # No year: this year, unless that date has already gone, then next year.
        candidate = date(today.year, spec.month, spec.day)
        if candidate < today:
            candidate = date(today.year + 1, spec.month, spec.day)
        return candidate
    except ValueError:  # e.g. 30 February
        raise _Unclear from None


def _weekday(spec: WhenSpec, today: date) -> date | _Pick:
    target = WEEKDAYS.index(spec.weekday)
    ahead = (target - today.weekday()) % 7  # 0 = today
    name = spec.weekday.capitalize()

    if spec.day_word == "next_week" or (spec.weekday_modifier == "next" and ahead == 0):
        # "Friday next week", or "next Friday" said on a Friday: clearly a week away.
        return _start_of_week(today) + timedelta(days=7 + target)

    if spec.weekday_modifier == "next":
        upcoming = today + timedelta(days=ahead)
        following_week = _start_of_week(today) + timedelta(days=7 + target)
        if upcoming == following_week:
            return upcoming  # e.g. "next Tuesday" said on a Wednesday: only one Tuesday fits
        # Said on a Wednesday, "next Friday" could be in 2 days or in 9. Ask.
        return _Pick("clarify.next_weekday", {"weekday": name}, [upcoming, following_week])

    if ahead == 0 and spec.weekday_modifier == "none":
        # "Friday" said on a Friday: today, or a week from today?
        return _Pick("clarify.weekday_today", {"weekday": name}, [today, today + timedelta(days=7)])
    return today + timedelta(days=ahead)


def _with_choices(pick: _Pick, make, now_utc: datetime) -> Resolved | Ask:
    choices = [make(day) for day in pick.days]
    choices = [c for c in choices if c.due_at_utc > now_utc]  # drop options already past
    if not choices:
        return Ask("clarify.past")
    if len(choices) == 1:
        return choices[0]  # only one possible answer left, so nothing to ask
    return Ask(pick.question_key, pick.args, choices)


def _start_of_week(day: date) -> date:
    return day - timedelta(days=day.weekday())  # weeks start on Monday


def describe_choice(choice: Resolved, timezone: str) -> str:
    """Button label for a choice, e.g. 'Fri 27 Nov, 5:00 PM'."""
    return format_datetime(choice.due_at_utc, timezone)
