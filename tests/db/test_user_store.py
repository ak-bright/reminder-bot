"""The database-backed UserStore, including the bot surviving a restart."""

from reminderbot.channels.base import IncomingEvent
from reminderbot.channels.router import Router
from reminderbot.core.reminders import ReminderService
from reminderbot.core.users import UserProfile, UserService
from reminderbot.db.reminder_store import SqlReminderStore
from reminderbot.db.user_store import SqlUserStore
from reminderbot.strings import t


def msg(text: str = "", button: str | None = None) -> IncomingEvent:
    return IncomingEvent(
        channel="fake",
        channel_user_id="42",
        chat_id="42",
        text=text,
        button_data=button,
        display_name="Ama",
    )


def new_bot(session_factory, clock) -> tuple[Router, UserService]:
    """Everything a fresh bot process would build. Calling it again = a restart."""
    users = UserService(SqlUserStore(session_factory, clock), default_timezone="Africa/Accra")
    reminders = ReminderService(SqlReminderStore(session_factory), clock)
    return Router(users, reminders, clock), users


async def test_save_and_load_roundtrip(session_factory, clock):
    store = SqlUserStore(session_factory, clock)
    profile = UserProfile(
        channel="fake", channel_user_id="42", name="Ama", timezone="America/New_York"
    )
    await store.save(profile)
    assert profile.id is not None

    loaded = await store.get("fake", "42")
    assert loaded == profile
    assert await store.get("fake", "nobody") is None


async def test_saving_twice_updates_the_same_row(session_factory, clock):
    store = SqlUserStore(session_factory, clock)
    profile = UserProfile(channel="fake", channel_user_id="42", name="Ama", timezone="UTC")
    await store.save(profile)
    first_id = profile.id

    profile.timezone = "Africa/Lagos"
    profile.is_new = False
    await store.save(profile)
    loaded = await store.get("fake", "42")
    assert loaded.id == first_id
    assert loaded.timezone == "Africa/Lagos" and loaded.is_new is False


async def test_start_saves_the_user(session_factory, clock, channel):
    router, _ = new_bot(session_factory, clock)
    await router.handle(msg("/start"), channel)

    stored = await SqlUserStore(session_factory, clock).get("fake", "42")
    assert stored is not None
    assert stored.name == "Ama" and stored.timezone == "Africa/Accra" and stored.is_new


async def test_timezone_survives_a_restart(session_factory, clock, channel):
    router, _ = new_bot(session_factory, clock)
    await router.handle(msg(button="tz:Africa/Lagos"), channel)

    router, users = new_bot(session_factory, clock)  # restart
    await router.handle(msg("/start"), channel)
    assert "Welcome back" in channel.last["text"]
    assert (await users.get_or_create("fake", "42", "Ama")).timezone == "Africa/Lagos"


async def test_waiting_for_a_typed_timezone_survives_a_restart(session_factory, clock, channel):
    router, _ = new_bot(session_factory, clock)
    await router.handle(msg(button="tz:other"), channel)
    assert channel.last["text"] == t("tz.ask_other")

    router, users = new_bot(session_factory, clock)  # restart before the user answers
    await router.handle(msg("new york"), channel)
    user = await users.get_or_create("fake", "42", "Ama")
    assert user.timezone == "America/New_York"
    assert not user.awaiting_timezone  # the pending action was cleared
