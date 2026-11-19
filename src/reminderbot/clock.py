"""Where "now" comes from.

Code that needs the current time takes a Clock instead of calling datetime.now()
directly. In production we pass SystemClock; in tests we pass FakeClock and move
time forward by hand, so tests never sleep and are fully deterministic.
"""

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Current time, always timezone-aware UTC."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FakeClock:
    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None:
            raise ValueError("FakeClock needs a timezone-aware datetime")
        self._now = start.astimezone(UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, **kwargs: float) -> None:
        """Move time forward, e.g. clock.advance(minutes=30)."""
        self._now += timedelta(**kwargs)

    def set(self, moment: datetime) -> None:
        self._now = moment.astimezone(UTC)
