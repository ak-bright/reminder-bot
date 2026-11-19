"""The bot's conversation logic, tested through a fake channel (no Telegram needed)."""

import pytest

from reminderbot.channels.base import IncomingEvent, parse_command
from reminderbot.strings import t


def msg(text: str, user: str = "42") -> IncomingEvent:
    return IncomingEvent(
        channel="fake", channel_user_id=user, chat_id=user, text=text, display_name="Ama"
    )


def press(data: str, user: str = "42") -> IncomingEvent:
    return IncomingEvent(
        channel="fake", channel_user_id=user, chat_id=user, button_data=data, display_name="Ama"
    )


def button_data(sent: dict) -> list[str]:
    return [b.data for row in sent["buttons"] for b in row]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/start", ("start", "")),
        ("/START@ReminderBot", ("start", "")),
        ("/remind tomorrow | essay", ("remind", "tomorrow | essay")),
        ("hello", (None, "hello")),
        ("/", (None, "")),
    ],
)
def test_parse_command(text, expected):
    assert parse_command(text) == expected


async def test_start_greets_and_offers_timezones(router, channel):
    await router.handle(msg("/start"), channel)
    sent = channel.last
    assert "Ama" in sent["text"]
    assert button_data(sent) == [
        "tz:Africa/Accra",
        "tz:Africa/Lagos",
        "tz:Europe/London",
        "tz:other",
    ]
    # Telegram's callback_data limit is 64 bytes
    assert all(len(d.encode()) <= 64 for d in button_data(sent))


async def test_new_user_defaults_to_accra(router, channel, users):
    await router.handle(msg("/start"), channel)
    user = await users.get_or_create("fake", "42", "Ama")
    assert user.timezone == "Africa/Accra"


async def test_pressing_a_timezone_button_saves_it(router, channel, users):
    await router.handle(msg("/start"), channel)
    await router.handle(press("tz:Europe/London"), channel)
    user = await users.get_or_create("fake", "42", "Ama")
    assert user.timezone == "Europe/London"
    assert not user.is_new
    # FakeClock is 14:30 UTC; London in November is UTC+0
    assert "Europe/London" in channel.last["text"]
    assert "2:30 PM" in channel.last["text"]


async def test_other_timezone_typed_by_user(router, channel, users):
    await router.handle(press("tz:other"), channel)
    assert channel.last["text"] == t("tz.ask_other")

    await router.handle(msg("new york"), channel)
    user = await users.get_or_create("fake", "42", "Ama")
    assert user.timezone == "America/New_York"
    assert "9:30 AM" in channel.last["text"]  # 14:30 UTC = 9:30 EST


async def test_invalid_typed_timezone_keeps_asking(router, channel, users):
    await router.handle(press("tz:other"), channel)
    await router.handle(msg("Mars/Olympus"), channel)
    assert channel.last["text"] == t("tz.invalid", value="Mars/Olympus")
    user = await users.get_or_create("fake", "42", "Ama")
    assert user.awaiting_timezone
    assert user.timezone == "Africa/Accra"

    await router.handle(msg("Lagos"), channel)
    user = await users.get_or_create("fake", "42", "Ama")
    assert user.timezone == "Africa/Lagos"
    assert not user.awaiting_timezone


async def test_returning_user_gets_welcome_back(router, channel):
    await router.handle(press("tz:Africa/Accra"), channel)
    await router.handle(msg("/start"), channel)
    assert channel.last["buttons"] is None
    assert "Welcome back" in channel.last["text"]


async def test_timezone_command_shows_buttons(router, channel):
    await router.handle(msg("/timezone"), channel)
    assert "tz:other" in button_data(channel.last)


async def test_help(router, channel):
    await router.handle(msg("/help"), channel)
    assert channel.last["text"] == t("help.text")


async def test_unknown_command(router, channel):
    await router.handle(msg("/dance"), channel)
    assert channel.last["text"] == t("command.unknown")


async def test_plain_text_is_not_supported_yet(router, channel):
    await router.handle(msg("Data structures assignment due Friday 5pm"), channel)
    assert channel.last["text"] == t("fallback.not_yet")


async def test_users_are_kept_separate(router, channel, users):
    await router.handle(press("tz:Europe/London", user="1"), channel)
    await router.handle(press("tz:Africa/Lagos", user="2"), channel)
    assert (await users.get_or_create("fake", "1", None)).timezone == "Europe/London"
    assert (await users.get_or_create("fake", "2", None)).timezone == "Africa/Lagos"


async def test_unknown_button_is_ignored(router, channel):
    await router.handle(press("something-else"), channel)
    assert channel.sent == []
