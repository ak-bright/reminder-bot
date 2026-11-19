"""/remind and the Delete button, through the router and a fake channel."""

from sqlalchemy import select

from reminderbot.channels.base import IncomingEvent
from reminderbot.core.models import AlertStatus, ReminderStatus
from reminderbot.db.models import Alert, Reminder
from reminderbot.strings import t

# The shared FakeClock (tests/conftest.py) says it's Wed 18 Nov 2026, 14:30 UTC.


def msg(text: str, user: str = "42") -> IncomingEvent:
    return IncomingEvent(channel="fake", channel_user_id=user, chat_id=user, text=text)


def press(data: str, user: str = "42") -> IncomingEvent:
    return IncomingEvent(channel="fake", channel_user_id=user, chat_id=user, button_data=data)


async def all_reminders(session_factory) -> list[Reminder]:
    async with session_factory() as session:
        return list((await session.scalars(select(Reminder))).all())


async def all_alerts(session_factory) -> list[Alert]:
    async with session_factory() as session:
        return list((await session.scalars(select(Alert).order_by(Alert.send_at_utc))).all())


async def test_remind_saves_and_confirms(router, channel, session_factory):
    await router.handle(msg("/remind 2026-11-21 17:00 | Data Structures assignment"), channel)

    assert channel.last["text"] == (
        "Got it. Data Structures assignment, due Sat 21 Nov, 5:00 PM. "
        "I'll remind you 1 day before, 3 hours before and 30 minutes before."
    )
    [reminder] = await all_reminders(session_factory)
    assert reminder.title == "Data Structures assignment"
    assert reminder.alert_offsets == [1440, 180, 30]
    assert len(await all_alerts(session_factory)) == 3


async def test_confirmation_has_a_delete_button(router, channel, session_factory):
    await router.handle(msg("/remind tomorrow 17:00 | Quiz"), channel)
    [reminder] = await all_reminders(session_factory)
    [[button]] = channel.last["buttons"]
    assert button.label == t("button.delete")
    assert button.data == f"del:{reminder.id}"


async def test_no_time_given_says_8am(router, channel):
    await router.handle(msg("/remind 2026-11-21 | Lab report"), channel)
    assert "due Sat 21 Nov, 8:00 AM" in channel.last["text"]
    assert channel.last["text"].endswith(t("remind.default_time"))


async def test_soon_deadline_only_lists_remaining_alerts(router, channel):
    await router.handle(msg("/remind today 18:00 | Submit essay"), channel)  # 3.5 h away
    assert channel.last["text"].endswith("I'll remind you 3 hours before and 30 minutes before.")


async def test_very_soon_deadline_alerts_right_away(router, channel):
    await router.handle(msg("/remind today 14:33 | Submit now"), channel)  # 3 min away
    assert channel.last["text"].endswith("I'll remind you right away.")


async def test_relative_reminder(router, channel, session_factory):
    await router.handle(msg("/remind in 2h | Call my group leader"), channel)
    assert channel.last["text"] == (
        "Got it. I'll remind you on Wed 18 Nov, 4:30 PM: Call my group leader"
    )
    [alert] = await all_alerts(session_factory)
    [reminder] = await all_reminders(session_factory)
    assert alert.send_at_utc == reminder.due_at_utc


async def test_new_york_user_sees_new_york_times(router, channel, session_factory):
    await router.handle(press("tz:other"), channel)
    await router.handle(msg("new york"), channel)
    await router.handle(msg("/remind 2026-11-21 17:00 | Essay"), channel)

    assert "due Sat 21 Nov, 5:00 PM" in channel.last["text"]
    [reminder] = await all_reminders(session_factory)
    assert reminder.due_at_utc.hour == 22  # stored in UTC


async def test_remind_without_arguments_shows_usage(router, channel, session_factory):
    await router.handle(msg("/remind"), channel)
    assert channel.last["text"] == t("remind.usage")
    assert await all_reminders(session_factory) == []


async def test_unreadable_time(router, channel):
    await router.handle(msg("/remind friday 5pm | Essay"), channel)
    assert channel.last["text"] == t("remind.bad_when", when="friday 5pm")


async def test_time_in_the_past(router, channel, session_factory):
    await router.handle(msg("/remind today 9:00 | Essay"), channel)
    assert channel.last["text"] == t("remind.past", due="today 9:00")
    assert await all_reminders(session_factory) == []


async def test_description_too_long(router, channel, session_factory):
    await router.handle(msg("/remind tomorrow 9:00 | " + "x" * 201), channel)
    assert channel.last["text"] == t("remind.too_long", max=200)
    assert await all_reminders(session_factory) == []


async def test_delete_button_deletes_and_cancels_alerts(router, channel, session_factory):
    await router.handle(msg("/remind 2026-11-21 17:00 | Essay"), channel)
    [[button]] = channel.last["buttons"]

    await router.handle(press(button.data), channel)
    assert channel.last["text"] == t("remind.deleted")
    [reminder] = await all_reminders(session_factory)
    assert reminder.status == ReminderStatus.DELETED
    assert {a.status for a in await all_alerts(session_factory)} == {AlertStatus.CANCELLED}

    await router.handle(press(button.data), channel)  # pressed again
    assert channel.last["text"] == t("remind.already_gone")


async def test_cannot_delete_someone_elses_reminder(router, channel, session_factory):
    await router.handle(msg("/remind 2026-11-21 17:00 | Ama's essay", user="1"), channel)
    [[button]] = channel.last["buttons"]

    await router.handle(press(button.data, user="2"), channel)  # Kofi sends Ama's button data
    assert channel.last["text"] == t("remind.already_gone")
    [reminder] = await all_reminders(session_factory)
    assert reminder.status == ReminderStatus.ACTIVE


async def test_tampered_delete_button_is_ignored(router, channel):
    await router.handle(press("del:abc"), channel)
    assert channel.sent == []
