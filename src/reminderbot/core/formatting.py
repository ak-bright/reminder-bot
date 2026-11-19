"""Human-friendly date/time formatting in the user's timezone."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from reminderbot.strings import DEFAULT_LANGUAGE, t


def to_local(moment_utc: datetime, timezone: str) -> datetime:
    return moment_utc.astimezone(ZoneInfo(timezone))


def format_time(moment_utc: datetime, timezone: str) -> str:
    """'3:05 PM' style. (We strip the leading zero ourselves because '%-I' fails on Windows.)"""
    return to_local(moment_utc, timezone).strftime("%I:%M %p").lstrip("0")


def format_datetime(moment_utc: datetime, timezone: str) -> str:
    """'Fri 21 Nov, 5:00 PM' style."""
    local = to_local(moment_utc, timezone)
    day = f"{local.strftime('%a')} {local.day} {local.strftime('%b')}"
    return f"{day}, {format_time(local, timezone)}"


def format_duration(delta: timedelta, lang: str = DEFAULT_LANGUAGE) -> str:
    """'1 day', '3 hours', '30 minutes'. Rounded to the biggest unit that fits."""
    minutes = max(1, round(delta.total_seconds() / 60))
    if minutes >= 24 * 60:
        amount, unit = round(minutes / (24 * 60)), "day"
    elif minutes >= 60:
        amount, unit = round(minutes / 60), "hour"
    else:
        amount, unit = minutes, "minute"
    key = f"duration.{unit}" if amount == 1 else f"duration.{unit}s"
    return t(key, lang, n=amount)


def join_list(items: list[str], lang: str = DEFAULT_LANGUAGE) -> str:
    """['a', 'b', 'c'] -> 'a, b and c'."""
    if len(items) <= 1:
        return "".join(items)
    return t("list.and", lang, first=", ".join(items[:-1]), last=items[-1])
