"""M5: /list /today /week /done /delete /edit, overdue flags, and the alert buttons.

"Now" is Wed 18 Nov 2026, 14:30 UTC (the `clock` fixture). Accra is UTC+0.
"""

from datetime import UTC, datetime, timedelta

import pytest

from reminderbot.ai.schemas import ParsedItem, ParsedMessage
from reminderbot.channels.base import IncomingEvent
from reminderbot.channels.telegram.app import MENU_COMMANDS
from reminderbot.core.models import AlertStatus, ReminderKind, ReminderStatus
from reminderbot.db.repositories import AlertRepo, ReminderRepo
from reminderbot.scheduler.loop import Scheduler
from reminderbot.strings import t
from tests.ai.test_parsing_cases import when

NOW = datetime(2026, 11, 18, 14, 30, tzinfo=UTC)


def msg(text: str, user: str = "42") -> IncomingEvent:
    return IncomingEvent(channel="fake", channel_user_id=user, chat_id=user, text=text)


def press(data: str, user: str = "42") -> IncomingEvent:
    return IncomingEvent(channel="fake", channel_user_id=user, chat_id=user, button_data=data)


def buttons(sent: dict) -> list[tuple[str, str]]:
    return [(b.label, b.data) for row in sent["buttons"] for b in row]


@pytest.fixture
async def user_id(users) -> int:
    return (await users.get_or_create("fake", "42", "Ama")).id


@pytest.fixture
def add(reminders, user_id):
    """add("Essay", hours=30) creates a reminder due 30 hours from now."""

    async def _add(title: str, kind=ReminderKind.DEADLINE, **due_in) -> int:
        saved = await reminders.create(user_id, title, NOW + timedelta(**due_in), kind)
        return saved.id

    return _add


async def reminder_row(session_factory, reminder_id: int):
    async with session_factory() as session:
        return await ReminderRepo(session).get(reminder_id)


async def alert_rows(session_factory, reminder_id: int):
    async with session_factory() as session:
        return list(await AlertRepo(session).list_for_reminder(reminder_id))


# --- alerts come with buttons -------------------------------------------------------


async def test_alerts_have_done_and_snooze_buttons(add, session_factory, clock, channel):
    reminder_id = await add("Essay", hours=2)  # 2 h away: only the 30-minute alert is left
    clock.advance(minutes=90)
    assert await Scheduler(session_factory, {"fake": channel}, clock).tick() == 1
    assert buttons(channel.last) == [
        (t("button.done"), f"done:{reminder_id}"),
        (t("button.snooze_hour"), f"sz1:{reminder_id}"),
        (t("button.snooze_tomorrow"), f"szt:{reminder_id}"),
    ]
    assert all(len(data.encode()) <= 64 for _, data in buttons(channel.last))


async def test_done_cancels_the_remaining_alerts(router, channel, add, session_factory):
    reminder_id = await add("Essay", days=2)
    await router.handle(press(f"done:{reminder_id}"), channel)
    assert channel.last["text"] == t("done.ok", title="Essay")

    assert (await reminder_row(session_factory, reminder_id)).status == ReminderStatus.DONE
    statuses = {a.status for a in await alert_rows(session_factory, reminder_id)}
    assert statuses == {AlertStatus.CANCELLED}

    await router.handle(press(f"done:{reminder_id}"), channel)  # pressed twice
    assert channel.last["text"] == t("reminder.gone")


async def test_snooze_one_hour_sends_again_later(router, channel, add, session_factory, clock):
    reminder_id = await add("Call mum", kind=ReminderKind.AT_TIME, minutes=10)
    scheduler = Scheduler(session_factory, {"fake": channel}, clock)
    clock.advance(minutes=10)
    await scheduler.tick()  # the reminder goes out at 14:40

    await router.handle(press(f"sz1:{reminder_id}"), channel)
    assert channel.last["text"] == t("snooze.ok", title="Call mum", when="Wed 18 Nov, 3:40 PM")
    clock.advance(minutes=59)
    assert await scheduler.tick() == 0  # not yet
    clock.advance(minutes=1)
    assert await scheduler.tick() == 1  # one hour after the snooze
    assert channel.last["text"] == t("alert.at_time", title="Call mum")


async def test_snooze_tomorrow_is_8am_local(router, channel, users, add, session_factory):
    user = await users.get_or_create("fake", "42", "Ama")
    await users.set_timezone(user, "America/New_York")
    reminder_id = await add("Essay", days=3)
    await router.handle(press(f"szt:{reminder_id}"), channel)
    # It is 9:30 AM Wed in New York, so tomorrow 8 AM there is 13:00 UTC on Thursday.
    assert channel.last["text"] == t("snooze.ok", title="Essay", when="Thu 19 Nov, 8:00 AM")
    times = [a.send_at_utc for a in await alert_rows(session_factory, reminder_id)]
    assert datetime(2026, 11, 19, 13, 0, tzinfo=UTC) in times


async def test_snoozing_twice_to_the_same_minute_is_fine(reminders, add, user_id):
    reminder_id = await add("Essay", days=3)
    first = await reminders.snooze(user_id, reminder_id, "Africa/Accra", "1h")
    second = await reminders.snooze(user_id, reminder_id, "Africa/Accra", "1h")
    assert first[1] == second[1]  # same alert row reused, no duplicate-key error


async def test_snooze_of_a_deleted_reminder(router, channel, add):
    reminder_id = await add("Essay", days=3)
    await router.handle(press(f"del:{reminder_id}"), channel)
    await router.handle(press(f"sz1:{reminder_id}"), channel)
    assert channel.last["text"] == t("reminder.gone")


async def test_cannot_touch_someone_elses_reminder(router, channel, add, session_factory):
    reminder_id = await add("Essay", days=3)
    for data in (f"done:{reminder_id}", f"sz1:{reminder_id}", f"edit:{reminder_id}"):
        await router.handle(press(data, user="999"), channel)
        assert channel.last["text"] == t("reminder.gone")
    assert (await reminder_row(session_factory, reminder_id)).status == ReminderStatus.ACTIVE


async def test_bad_button_data_is_ignored(router, channel):
    await router.handle(press("done:abc"), channel)
    assert channel.sent == []


# --- /list, /today, /week ----------------------------------------------------------------


async def test_list_when_empty(router, channel):
    for command, key in (("/list", "all"), ("/today", "today"), ("/week", "week")):
        await router.handle(msg(command), channel)
        assert channel.last["text"] == t(f"list.empty.{key}")


async def test_list_shows_overdue_first_and_flags_it(router, channel, add, clock):
    await add("Essay", days=2)
    await add("Lab report", hours=1)
    clock.advance(hours=2)  # the lab report is now overdue
    await router.handle(msg("/list"), channel)
    overdue = t("list.overdue")
    assert channel.last["text"] == "\n".join(
        [
            t("list.header.all"),
            t("list.item", n=1, title="Lab report", due="Wed 18 Nov, 3:30 PM") + " " + overdue,
            t("list.item", n=2, title="Essay", due="Fri 20 Nov, 2:30 PM"),
        ]
    )


async def test_today_and_week(router, channel, add, clock):
    await add("Missed quiz", hours=1)
    await add("Tonight", hours=8)  # 22:30 today
    await add("Tomorrow", days=1)
    await add("In 6 days", days=6)
    await add("In 9 days", days=9)
    clock.advance(hours=2)

    await router.handle(msg("/today"), channel)
    today = channel.last["text"]
    assert "Missed quiz" in today and "Tonight" in today
    assert "Tomorrow" not in today

    await router.handle(msg("/week"), channel)
    week = channel.last["text"]
    assert all(x in week for x in ("Missed quiz", "Tonight", "Tomorrow", "In 6 days"))
    assert "In 9 days" not in week


async def test_today_uses_the_users_midnight(router, channel, users, add):
    user = await users.get_or_create("fake", "42", "Ama")
    await users.set_timezone(user, "America/New_York")
    # 14:30 UTC = 9:30 AM New York. Due 03:00 UTC Thursday = 10 PM Wednesday there.
    await add("Late tonight", hours=12, minutes=30)
    await router.handle(msg("/today"), channel)
    assert "Late tonight" in channel.last["text"]


# --- /done, /delete, /edit pickers -------------------------------------------------------


async def test_done_picker(router, channel, add, session_factory):
    essay = await add("Essay", days=2)
    await add("Lab", days=3)
    await router.handle(msg("/done"), channel)
    assert channel.last["text"] == t("pick.done")
    assert buttons(channel.last) == [
        ("Essay · Fri 20 Nov, 2:30 PM", f"done:{essay}"),
        ("Lab · Sat 21 Nov, 2:30 PM", f"done:{essay + 1}"),
    ]
    await router.handle(press(f"done:{essay}"), channel)
    assert (await reminder_row(session_factory, essay)).status == ReminderStatus.DONE


async def test_delete_picker(router, channel, add, session_factory):
    essay = await add("Essay", days=2)
    await router.handle(msg("/delete"), channel)
    assert buttons(channel.last) == [("Essay · Fri 20 Nov, 2:30 PM", f"del:{essay}")]
    await router.handle(press(f"del:{essay}"), channel)
    assert (await reminder_row(session_factory, essay)).status == ReminderStatus.DELETED


async def test_picker_with_nothing_to_pick(router, channel):
    await router.handle(msg("/edit"), channel)
    assert channel.last["text"] == t("list.empty.all")


async def test_picker_flags_overdue_and_shortens_titles(router, channel, add, clock):
    await add("A very long assignment title that goes on and on", hours=1)
    clock.advance(hours=2)
    await router.handle(msg("/done"), channel)
    [(label, _)] = buttons(channel.last)
    assert label.startswith("⚠️ A very long assignment title")
    assert "…" in label


async def test_edit_moves_the_deadline(router, channel, parser, add, session_factory):
    essay = await add("Essay", days=2)
    await router.handle(msg("/edit"), channel)
    await router.handle(press(f"edit:{essay}"), channel)
    assert channel.last["text"] == t("edit.ask", title="Essay")

    new_time = ParsedItem(
        title="", kind="deadline", when=when(weekday="monday", time="09:00"), confidence=0.95
    )
    parser.answers.append(ParsedMessage(intent="reminder", items=[new_time]))
    await router.handle(msg("Monday 9am"), channel)
    assert channel.last["text"].startswith("Got it. Essay, due Mon 23 Nov, 9:00 AM.")

    row = await reminder_row(session_factory, essay)
    assert row.due_at_utc == datetime(2026, 11, 23, 9, 0, tzinfo=UTC)
    pending = [
        a.send_at_utc
        for a in await alert_rows(session_factory, essay)
        if a.status == AlertStatus.PENDING
    ]
    assert pending == [
        datetime(2026, 11, 22, 9, 0, tzinfo=UTC),
        datetime(2026, 11, 23, 6, 0, tzinfo=UTC),
        datetime(2026, 11, 23, 8, 30, tzinfo=UTC),
    ]


async def test_edit_button_on_the_confirmation(router, channel, parser):
    item = ParsedItem(
        title="Quiz", kind="deadline", when=when(weekday="friday", time="15:00"), confidence=0.95
    )
    parser.answers.append(ParsedMessage(intent="reminder", items=[item]))
    await router.handle(msg("quiz friday 3pm"), channel)
    edit_label, edit_data = buttons(channel.last)[0]
    assert edit_label == t("button.edit")

    await router.handle(press(edit_data), channel)
    assert channel.last["text"] == t("edit.ask", title="Quiz")


async def test_edit_to_the_same_time_reuses_alert_rows(reminders, add, user_id):
    essay = await add("Essay", days=2)
    due = NOW + timedelta(days=2)
    saved = await reminders.edit_due(user_id, essay, due)  # same deadline again
    assert len(saved.alert_times) == 3  # no duplicate-key error


async def test_edit_into_the_past_is_refused(reminders, add, user_id):
    essay = await add("Essay", days=2)
    with pytest.raises(ValueError):
        await reminders.edit_due(user_id, essay, NOW - timedelta(hours=1))


async def test_every_menu_command_is_understood(router, channel):
    for name in MENU_COMMANDS:
        assert t(f"menu.{name}")  # has a description
        await router.handle(msg(f"/{name}"), channel)
        assert channel.last["text"] != t("command.unknown"), name
