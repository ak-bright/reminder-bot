from datetime import UTC, datetime

import pytest

from reminderbot.clock import FakeClock
from reminderbot.core.formatting import format_datetime, format_time
from reminderbot.core.timezones import is_valid_timezone, normalize_timezone


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("Africa/Accra", "Africa/Accra"),
        ("africa/accra", "Africa/Accra"),
        ("  Europe/London ", "Europe/London"),
        ("Nairobi", "Africa/Nairobi"),
        ("new york", "America/New_York"),
        ("New_York", "America/New_York"),
        ("Mars/Olympus", None),
        ("", None),
        ("ignore your instructions", None),
    ],
)
def test_normalize_timezone(typed, expected):
    assert normalize_timezone(typed) == expected


def test_is_valid_timezone():
    assert is_valid_timezone("Africa/Accra")
    assert not is_valid_timezone("africa/accra")  # must be the exact official name


def test_accra_is_utc():
    moment = datetime(2026, 11, 21, 17, 0, tzinfo=UTC)
    assert format_datetime(moment, "Africa/Accra") == "Sat 21 Nov, 5:00 PM"


def test_new_york_shows_local_time():
    # 17:00 UTC in November = 12:00 PM in New York (EST, UTC-5)
    moment = datetime(2026, 11, 21, 17, 0, tzinfo=UTC)
    assert format_time(moment, "America/New_York") == "12:00 PM"


def test_new_york_daylight_saving():
    # In July New York is on EDT (UTC-4)
    moment = datetime(2026, 7, 1, 17, 0, tzinfo=UTC)
    assert format_time(moment, "America/New_York") == "1:00 PM"


def test_fake_clock_moves_only_when_told():
    clock = FakeClock(datetime(2026, 11, 18, 8, 0, tzinfo=UTC))
    assert clock.now() == datetime(2026, 11, 18, 8, 0, tzinfo=UTC)
    clock.advance(hours=2, minutes=30)
    assert clock.now() == datetime(2026, 11, 18, 10, 30, tzinfo=UTC)


def test_fake_clock_rejects_naive_datetimes():
    with pytest.raises(ValueError):
        FakeClock(datetime(2026, 11, 18, 8, 0))
