"""Timezone helpers built on the standard-library zoneinfo module."""

from functools import cache
from zoneinfo import available_timezones


@cache
def _all_timezones() -> dict[str, str]:
    """Map lower-case name -> official IANA name, e.g. 'africa/accra' -> 'Africa/Accra'."""
    return {name.lower(): name for name in available_timezones()}


@cache
def _by_city() -> dict[str, list[str]]:
    """Map lower-case city -> IANA names, e.g. 'nairobi' -> ['Africa/Nairobi']."""
    cities: dict[str, list[str]] = {}
    for name in available_timezones():
        city = name.rsplit("/", 1)[-1].lower().replace("_", " ")
        cities.setdefault(city, []).append(name)
    return cities


def normalize_timezone(text: str) -> str | None:
    """Turn what a student typed into an official timezone name, or None.

    Accepts 'Africa/Accra', 'africa/accra', or a city on its own like 'Nairobi'
    or 'new york' (only if that city matches exactly one timezone).
    """
    cleaned = text.strip()
    if not cleaned:
        return None
    exact = _all_timezones().get(cleaned.lower().replace(" ", "_"))
    if exact:
        return exact
    matches = _by_city().get(cleaned.lower().replace("_", " "), [])
    return matches[0] if len(matches) == 1 else None


def is_valid_timezone(name: str) -> bool:
    return name in available_timezones()
