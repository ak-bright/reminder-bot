from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from reminderbot.ai.parser import ParserError
from reminderbot.ai.schemas import ParsedMessage
from reminderbot.channels.base import Button, Channel
from reminderbot.channels.natural import NaturalLanguage
from reminderbot.channels.router import Router
from reminderbot.clock import FakeClock
from reminderbot.core.reminders import ReminderService
from reminderbot.core.users import UserService
from reminderbot.db.base import Base
from reminderbot.db.clarification_store import SqlClarificationStore
from reminderbot.db.reminder_store import SqlReminderStore
from reminderbot.db.session import create_engine, create_session_factory
from reminderbot.db.user_store import SqlUserStore


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
def users(session_factory, clock) -> UserService:
    return UserService(SqlUserStore(session_factory, clock), default_timezone="Africa/Accra")


@pytest.fixture
def reminders(session_factory, clock) -> ReminderService:
    return ReminderService(SqlReminderStore(session_factory), clock)


class FakeParser:
    """Stands in for the AI: returns the answers a test queued up, in order.

    It records what it was asked, so tests can check the input too.
    """

    def __init__(self) -> None:
        self.answers: list[ParsedMessage | ParserError] = []
        self.calls: list[str] = []

    async def parse(self, text: str, now_local: datetime, timezone: str) -> ParsedMessage:
        self.calls.append(text)
        answer = self.answers.pop(0)
        if isinstance(answer, ParserError):
            raise answer
        return answer


@pytest.fixture
def parser() -> FakeParser:
    return FakeParser()


@pytest.fixture
def natural(parser, reminders, session_factory, clock) -> NaturalLanguage:
    store = SqlClarificationStore(session_factory)
    return NaturalLanguage(parser, reminders, store, clock, max_input_chars=2000)


@pytest.fixture
def router(
    users: UserService, reminders: ReminderService, natural: NaturalLanguage, clock: FakeClock
) -> Router:
    return Router(users, reminders, natural, clock)


# --- Database -------------------------------------------------------------------
# Each test gets its own fresh SQLite file in a temporary folder. (A file rather
# than ":memory:", because every new connection to ":memory:" is an empty database.)


@pytest.fixture
def database_url(tmp_path) -> str:
    return f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}"


@pytest.fixture
async def engine(database_url):
    engine = create_engine(database_url)
    async with engine.begin() as conn:
        # create_all is quicker than running migrations; test_migrations.py checks
        # that the migrations build exactly the same tables.
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(engine):
    return create_session_factory(engine)


@pytest.fixture
async def session(session_factory) -> AsyncSession:
    async with session_factory() as session:
        yield session
