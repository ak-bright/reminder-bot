"""core/when.py on its own: edge cases the message table doesn't reach."""

from datetime import UTC, date, datetime

from reminderbot.core.crosscheck import dates_agree, worth_checking
from reminderbot.core.when import Ask, Resolved, resolve
from tests.ai.test_parsing_cases import when

ACCRA = "Africa/Accra"


def at(year, month, day, hour=8, minute=0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def test_end_of_month_in_december():
    now = at(2026, 12, 10, 12)
    assert resolve(when(day_word="end_of_month"), ACCRA, now) == Resolved(
        at(2026, 12, 31), time_defaulted=True
    )


def test_day_only_rolls_into_next_year_in_december():
    now = at(2026, 12, 20, 12)
    assert resolve(when(day=5), ACCRA, now) == Resolved(at(2027, 1, 5), time_defaulted=True)


def test_day_only_that_this_month_lacks_asks():
    # "The 31st", said in February: there is no 31 February, so we ask.
    now = at(2027, 2, 1, 12)
    assert resolve(when(day=31, time="09:00"), ACCRA, now) == Ask("clarify.when")


def test_month_without_a_day_asks():
    assert resolve(when(month=12), ACCRA, at(2026, 11, 18, 14)) == Ask("clarify.when")


def test_next_week_on_a_sunday_means_the_coming_week():
    now = at(2026, 11, 22, 12)  # Sunday
    result = resolve(when(day_word="next_week"), ACCRA, now)
    assert isinstance(result, Ask)
    assert result.choices[0].due_at_utc.date() == date(2026, 11, 23)  # tomorrow, Monday


def test_local_date_is_used_not_the_utc_date():
    # 02:00 UTC on Thu 19 Nov is still Wed 18 Nov, 9 PM in New York.
    now = at(2026, 11, 19, 2)
    result = resolve(when(day_word="tomorrow", part_of_day="morning"), "America/New_York", now)
    # Tomorrow for them is Thu 19 Nov, 8 AM New York = 13:00 UTC.
    assert result == Resolved(at(2026, 11, 19, 13))


def test_relative_limit():
    now = at(2026, 11, 18, 14)
    assert resolve(when(relative_minutes=-5), ACCRA, now) == Ask("clarify.when")
    assert resolve(when(relative_minutes=10**9), ACCRA, now) == Ask("clarify.when")


# --- dateparser cross-check -----------------------------------------------------


def test_crosscheck_only_for_weekdays_and_dates():
    assert worth_checking(when(weekday="friday"))
    assert worth_checking(when(month=12, day=11))
    assert not worth_checking(when(day_word="tomorrow"))
    assert not worth_checking(when(relative_minutes=60))
    assert not worth_checking(when(weekday="friday", day_word="next_week"))


def test_crosscheck_agrees_and_disagrees():
    now = at(2026, 11, 18, 14, 30)
    friday_5pm = at(2026, 11, 20, 17)
    assert dates_agree("essay due Friday 5pm", friday_5pm, ACCRA, now)
    assert not dates_agree("essay due Monday 5pm", friday_5pm, ACCRA, now)


def test_crosscheck_has_no_opinion_without_dates():
    now = at(2026, 11, 18, 14, 30)
    assert dates_agree("essay", at(2026, 11, 20, 17), ACCRA, now)
