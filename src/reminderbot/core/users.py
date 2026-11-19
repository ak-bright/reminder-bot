"""Users and their settings.

In M1 users are kept in memory (InMemoryUserStore), so they are forgotten when
the bot restarts. M2 adds a database-backed store with the same methods, and
nothing else needs to change.
"""

from dataclasses import dataclass
from typing import Protocol

from reminderbot.core.timezones import normalize_timezone


@dataclass
class UserProfile:
    channel: str  # e.g. "telegram"
    channel_user_id: str  # the id the channel gives this person
    name: str | None
    timezone: str
    language: str = "en"
    # True while we're waiting for the user to type a timezone name.
    # (Temporary M1 state; from M2 this kind of state lives in `pending_actions`.)
    awaiting_timezone: bool = False
    is_new: bool = True  # False once onboarding (timezone choice) is finished


class UserStore(Protocol):
    async def get(self, channel: str, channel_user_id: str) -> UserProfile | None: ...
    async def save(self, user: UserProfile) -> None: ...


class InMemoryUserStore:
    def __init__(self) -> None:
        self._users: dict[tuple[str, str], UserProfile] = {}

    async def get(self, channel: str, channel_user_id: str) -> UserProfile | None:
        return self._users.get((channel, channel_user_id))

    async def save(self, user: UserProfile) -> None:
        self._users[(user.channel, user.channel_user_id)] = user


class UserService:
    def __init__(self, store: UserStore, default_timezone: str) -> None:
        self._store = store
        self._default_timezone = default_timezone

    async def get_or_create(
        self, channel: str, channel_user_id: str, name: str | None
    ) -> UserProfile:
        user = await self._store.get(channel, channel_user_id)
        if user is None:
            user = UserProfile(
                channel=channel,
                channel_user_id=channel_user_id,
                name=name,
                timezone=self._default_timezone,
            )
            await self._store.save(user)
        return user

    async def set_awaiting_timezone(self, user: UserProfile, waiting: bool) -> None:
        user.awaiting_timezone = waiting
        await self._store.save(user)

    async def set_timezone(self, user: UserProfile, typed: str) -> str | None:
        """Save the timezone if it's valid. Returns the official name, or None if invalid."""
        timezone = normalize_timezone(typed)
        if timezone is None:
            return None
        user.timezone = timezone
        user.awaiting_timezone = False
        user.is_new = False
        await self._store.save(user)
        return timezone
