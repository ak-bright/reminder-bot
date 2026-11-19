"""Human-friendly date/time formatting in the user's timezone."""

from datetime import datetime
from zoneinfo import ZoneInfo


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
