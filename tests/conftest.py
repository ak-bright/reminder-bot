from datetime import UTC, datetime

import pytest

from reminderbot.channels.base import Button, Channel
from reminderbot.channels.router import Router
from reminderbot.clock import FakeClock
from reminderbot.core.users import InMemoryUserStore, UserService


class FakeChannel(Channel):
    """Records everything the bot 'sends' so tests can inspect it."""

    name = "fake"

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_message(self, chat_id: str, text: str) -> None:
        self.sent.append({"chat_id": chat_id, "text": text, "buttons": None})

    async def send_buttons(self, chat_id: str, text: str, buttons: list[list[Button]]) -> None:
        self.sent.append({"chat_id": chat_id, "text": text, "buttons": buttons})

    @property
    def last(self) -> dict:
        return self.sent[-1]


@pytest.fixture
def clock() -> FakeClock:
    # Wed 18 Nov 2026, 14:30 UTC
    return FakeClock(datetime(2026, 11, 18, 14, 30, tzinfo=UTC))


@pytest.fixture
def channel() -> FakeChannel:
    return FakeChannel()


@pytest.fixture
def users() -> UserService:
    return UserService(InMemoryUserStore(), default_timezone="Africa/Accra")


@pytest.fixture
def router(users: UserService, clock: FakeClock) -> Router:
    return Router(users, clock)
