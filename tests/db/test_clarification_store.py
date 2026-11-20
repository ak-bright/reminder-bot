"""The clarification queue is stored in `pending_actions` and comes back unchanged."""

from datetime import UTC, datetime, timedelta

from reminderbot.core.clarify import PendingReminder
from reminderbot.core.models import ReminderKind
from reminderbot.core.when import Resolved
from reminderbot.db.clarification_store import SqlClarificationStore
from reminderbot.db.models import User

NOW = datetime(2026, 11, 18, 14, 30, tzinfo=UTC)


async def make_user(session_factory) -> int:
    async with session_factory() as session:
        user = User(channel="fake", channel_user_id="42", timezone="Africa/Accra")
        session.add(user)
        await session.commit()
        return user.id


async def test_roundtrip_and_clear(session_factory):
    user_id = await make_user(session_factory)
    store = SqlClarificationStore(session_factory)
    item = PendingReminder(
        title="Essay",
        kind=ReminderKind.DEADLINE,
        question_key="clarify.next_weekday",
        question_args={"weekday": "Friday"},
        choices=[Resolved(NOW + timedelta(days=2), time_defaulted=True)],
        source_text="next friday essay",
    )
    saved = await store.replace(user_id, [item], expires_at=NOW + timedelta(hours=1))

    loaded = await store.get(user_id, NOW)
    assert loaded == saved
    assert loaded.queue[0].choices[0].due_at_utc.tzinfo is not None  # still UTC-aware

    assert await store.replace(user_id, [], expires_at=NOW) is None
    assert await store.get(user_id, NOW) is None


async def test_expired_question_is_not_returned(session_factory):
    user_id = await make_user(session_factory)
    store = SqlClarificationStore(session_factory)
    item = PendingReminder("Essay", ReminderKind.DEADLINE, "clarify.when")
    await store.replace(user_id, [item], expires_at=NOW + timedelta(hours=1))
    assert await store.get(user_id, NOW + timedelta(hours=2)) is None
