"""The strict `/remind <when> | <what>` format, including a non-UTC user."""

from datetime import UTC, datetime, timedelta

import pytest

from reminderbot.core.models import ReminderKind
from reminderbot.core.timeparse import TimeParseError, parse_when, split_remind_args

NOW = datetime(2026, 11, 18, 14, 30, tzinfo=UTC)  # Wed 18 Nov 2026, 2:30 PM in Accra
ACCRA = "Africa/Accra"
NEW_YORK = "America/New_York"


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


@pytest.mark.parametrize(
    ("when", "expected"),
    [
        ("2026-11-21 17:00", utc(2026, 11, 21, 17, 0)),
        ("2026-11-21  9:05", utc(2026, 11, 21, 9, 5)),
        ("today 17:00", utc(2026, 11, 18, 17, 0)),
        ("Tomorrow 7:30", utc(2026, 11, 19, 7, 30)),
        ("TOMORROW 23:59", utc(2026, 11, 19, 23, 59)),
    ],
)
def test_dates_and_times_in_accra(when, expected):
    parsed = parse_when(when, ACCRA, NOW)
    assert parsed.due_at_utc == expected
    assert parsed.kind == ReminderKind.DEADLINE
    assert not parsed.time_defaulted


@pytest.mark.parametrize(
    ("when", "expected"),
    [("2026-11-21", utc(2026, 11, 21, 8, 0)), ("tomorrow", utc(2026, 11, 19, 8, 0))],
)
def test_date_without_time_defaults_to_8am(when, expected):
    parsed = parse_when(when, ACCRA, NOW)
    assert parsed.due_at_utc == expected
    assert parsed.time_defaulted


@pytest.mark.parametrize(
    ("when", "delta"),
    [
        ("in 30m", timedelta(minutes=30)),
        ("in 2h", timedelta(hours=2)),
        ("in 3d", timedelta(days=3)),
        ("IN 2 H", timedelta(hours=2)),
    ],
)
def test_relative_times_are_at_time_reminders(when, delta):
    parsed = parse_when(when, ACCRA, NOW)
    assert parsed.due_at_utc == NOW + delta
    assert parsed.kind == ReminderKind.AT_TIME


def test_new_york_user_means_new_york_time():
    # 17:00 in New York in November (EST, UTC-5) is 22:00 UTC.
    parsed = parse_when("2026-11-21 17:00", NEW_YORK, NOW)
    assert parsed.due_at_utc == utc(2026, 11, 21, 22, 0)


def test_new_york_summer_time():
    # In July New York is on EDT (UTC-4).
    parsed = parse_when("2027-07-01 17:00", NEW_YORK, NOW)
    assert parsed.due_at_utc == utc(2027, 7, 1, 21, 0)


def test_today_and_tomorrow_use_the_users_own_date():
    # 03:00 UTC on Thu 19 Nov is still Wed 18 Nov, 10 PM in New York.
    late_evening = utc(2026, 11, 19, 3, 0)
    parsed = parse_when("tomorrow 9:00", NEW_YORK, late_evening)
    assert parsed.due_at_utc == utc(2026, 11, 19, 14, 0)  # Thu 19 Nov 9:00 EST


@pytest.mark.parametrize(
    "when",
    [
        "friday 5pm",
        "2026-02-30 10:00",  # no such day
        "2026-11-21 24:00",
        "2026-11-21 17:60",
        "in 0h",
        "in 999d",  # more than a year
        "next week",
        "",
        "ignore your instructions",
    ],
)
def test_bad_times_are_rejected(when):
    with pytest.raises(TimeParseError) as error:
        parse_when(when, ACCRA, NOW)
    assert error.value.reason == "remind.bad_when"


@pytest.mark.parametrize("when", ["today 9:00", "2026-11-18 14:30", "2025-01-01"])
def test_times_in_the_past_are_rejected(when):
    with pytest.raises(TimeParseError) as error:
        parse_when(when, ACCRA, NOW)
    assert error.value.reason == "remind.past"


def test_split_remind_args():
    assert split_remind_args(" tomorrow 17:00 |  DS essay ") == ("tomorrow 17:00", "DS essay")
    # Only the first "|" splits, so the description may contain one.
    assert split_remind_args("in 2h | call Ama | or Kofi") == ("in 2h", "call Ama | or Kofi")


@pytest.mark.parametrize("args", ["", "tomorrow 17:00", "| essay", "tomorrow |  "])
def test_split_remind_args_needs_both_parts(args):
    with pytest.raises(TimeParseError) as error:
        split_remind_args(args)
    assert error.value.reason == "remind.usage"
