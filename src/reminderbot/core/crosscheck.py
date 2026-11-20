"""A second opinion on the AI's date, from the `dateparser` library.

dateparser looks for dates in the original message. If it finds some, but none of
them falls on the day we worked out, something may be off, so the bot asks the user
to confirm instead of silently saving. If dateparser finds nothing, it has no opinion.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from dateparser.search import search_dates

from reminderbot.core.when import WhenSpec


def worth_checking(spec: WhenSpec) -> bool:
    """Only weekdays and calendar dates get a second opinion. Day words ("tomorrow",
    "next week") and "in 2 hours" are easy for the AI, and dateparser gets some of
    them wrong (it reads "day after tomorrow" as tomorrow)."""
    if spec.day_word is not None or spec.relative_minutes is not None:
        return False
    return spec.weekday is not None or spec.month is not None or spec.day is not None


def dates_agree(text: str, due_at_utc: datetime, timezone: str, now_utc: datetime) -> bool:
    now_local = now_utc.astimezone(ZoneInfo(timezone))
    settings = {
        # dateparser works with "naive" local times, so we give it local now without tzinfo.
        "RELATIVE_BASE": now_local.replace(tzinfo=None),
        "PREFER_DATES_FROM": "future",
        "DATE_ORDER": "DMY",  # in Ghana (and the UK) 11/12 means 11 December
        "RETURN_AS_TIMEZONE_AWARE": False,
    }
    try:
        found = search_dates(text, languages=["en"], settings=settings) or []
    except Exception:  # dateparser is only a helper, never a reason to fail
        return True
    # A reminder is never for a past day, so dateparser's past answers are mistakes
    # (it reads "on the 2nd" as a date that has gone). Ignore them.
    today = now_local.date()
    days = [moment.date() for _match, moment in found if moment.date() >= today]
    if not days:
        return True
    our_day = due_at_utc.astimezone(ZoneInfo(timezone)).date()
    return our_day in days
