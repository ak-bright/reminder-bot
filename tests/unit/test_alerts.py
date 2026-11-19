"""When alerts are scheduled (CLAUDE.md rule 4)."""

from datetime import UTC, datetime, timedelta

from reminderbot.core.alerts import compute_alert_times
from reminderbot.core.models import ReminderKind

NOW = datetime(2026, 11, 18, 14, 30, tzinfo=UTC)
DEADLINE = ReminderKind.DEADLINE


def alerts_before(due: datetime) -> list[timedelta]:
    """How long before the deadline each alert goes out (easier to read in tests)."""
    return [due - when for when in compute_alert_times(due, DEADLINE, NOW)]


def test_far_deadline_gets_all_three_alerts():
    due = NOW + timedelta(days=3)
    assert alerts_before(due) == [timedelta(days=1), timedelta(hours=3), timedelta(minutes=30)]


def test_alerts_are_soonest_first():
    times = compute_alert_times(NOW + timedelta(days=3), DEADLINE, NOW)
    assert times == sorted(times)


def test_offsets_in_the_past_are_skipped():
    # 10 hours away: "1 day before" has already passed.
    assert alerts_before(NOW + timedelta(hours=10)) == [timedelta(hours=3), timedelta(minutes=30)]
    # 2 hours away: only "30 minutes before" is left.
    assert alerts_before(NOW + timedelta(hours=2)) == [timedelta(minutes=30)]


def test_exactly_30_minutes_away_still_gets_the_30_minute_alert():
    due = NOW + timedelta(minutes=30)
    assert compute_alert_times(due, DEADLINE, NOW) == [NOW]


def test_under_30_minutes_gets_one_alert_5_minutes_before():
    due = NOW + timedelta(minutes=20)
    assert compute_alert_times(due, DEADLINE, NOW) == [due - timedelta(minutes=5)]


def test_under_5_minutes_gets_one_alert_right_now():
    due = NOW + timedelta(minutes=3)
    assert compute_alert_times(due, DEADLINE, NOW) == [NOW]


def test_past_deadline_gets_no_alerts():
    assert compute_alert_times(NOW - timedelta(minutes=1), DEADLINE, NOW) == []
    assert compute_alert_times(NOW, DEADLINE, NOW) == []


def test_at_time_reminder_gets_one_alert_at_that_moment():
    when = NOW + timedelta(hours=2)
    assert compute_alert_times(when, ReminderKind.AT_TIME, NOW) == [when]


def test_custom_offsets_and_duplicates():
    due = NOW + timedelta(days=2)
    times = compute_alert_times(due, DEADLINE, NOW, offsets=[60, 60, 10])
    assert [due - t for t in times] == [timedelta(hours=1), timedelta(minutes=10)]
