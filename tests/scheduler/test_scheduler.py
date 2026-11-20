"""The scheduler, driven by FakeClock: we move time by hand and call tick(). No sleeping."""

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select

from reminderbot.core.models import AlertStatus, ReminderKind, ReminderStatus
from reminderbot.core.reminders import ReminderService
from reminderbot.db.models import Alert, Reminder, User
from reminderbot.db.reminder_store import SqlReminderStore
from reminderbot.db.repositories import AlertRepo, UserRepo
from reminderbot.scheduler import loop
from reminderbot.scheduler.loop import Scheduler
from tests.conftest import FakeChannel


class FlakyChannel(FakeChannel):
    """Fails the first `failures` sends, then works."""

    def __init__(self, failures: int) -> None:
        super().__init__()
        self.failures = failures

    async def send_buttons(self, chat_id: str, text: str, buttons) -> None:
        # Alerts are sent with buttons ([Done] [Snooze 1h] [Snooze tomorrow]).
        if self.failures > 0:
            self.failures -= 1
            raise ConnectionError("Telegram is down")
        await super().send_buttons(chat_id, text, buttons)


class Crash(BaseException):
    """Simulates the process dying. BaseException, so no `except Exception` catches it."""


def make_scheduler(session_factory, channel, clock) -> Scheduler:
    return Scheduler(session_factory, {"fake": channel}, clock)


async def add_reminder(session_factory, clock, due_in: timedelta, **kwargs) -> int:
    """Create a user (if needed) and a reminder due `due_in` from now. Returns its id."""
    timezone = kwargs.pop("timezone", "Africa/Accra")
    kind = kwargs.pop("kind", ReminderKind.DEADLINE)
    async with session_factory() as session:
        users = UserRepo(session)
        user = await users.get_by_identity("fake", "42") or await users.add(
            User(channel="fake", channel_user_id="42", timezone=timezone)
        )
        await session.commit()
    service = ReminderService(SqlReminderStore(session_factory), clock)
    saved = await service.create(user.id, "DS assignment", clock.now() + due_in, kind)
    return saved.id


async def alerts(session_factory) -> list[Alert]:
    async with session_factory() as session:
        query = select(Alert).order_by(Alert.send_at_utc)
        return list((await session.scalars(query)).all())


# --- timing ---------------------------------------------------------------------


async def test_each_alert_is_sent_at_its_tick_and_only_once(session_factory, clock, channel):
    start = clock.now()
    await add_reminder(session_factory, clock, timedelta(days=3))
    scheduler = make_scheduler(session_factory, channel, clock)

    assert await scheduler.tick() == 0  # nothing due yet

    clock.set(start + timedelta(days=2) - timedelta(seconds=1))
    assert await scheduler.tick() == 0  # one second early: still nothing

    clock.set(start + timedelta(days=2))  # 1 day before the deadline
    assert await scheduler.tick() == 1
    assert channel.last["chat_id"] == "42"
    assert channel.last["text"] == (
        "⏰ Reminder: DS assignment\nDue Sat 21 Nov, 2:30 PM (in 1 day)."
    )
    assert await scheduler.tick() == 0  # the same alert is not sent again

    clock.set(start + timedelta(days=3, hours=-3))
    assert await scheduler.tick() == 1
    assert channel.last["text"].endswith("(in 3 hours).")

    clock.set(start + timedelta(days=3, minutes=-30))
    assert await scheduler.tick() == 1
    assert channel.last["text"].endswith("(in 30 minutes).")

    clock.advance(days=1)
    assert await scheduler.tick() == 0
    assert len(channel.sent) == 3
    assert {a.status for a in await alerts(session_factory)} == {AlertStatus.SENT}


async def test_at_time_reminder_message(session_factory, clock, channel):
    await add_reminder(session_factory, clock, timedelta(hours=2), kind=ReminderKind.AT_TIME)
    scheduler = make_scheduler(session_factory, channel, clock)
    clock.advance(hours=2)
    assert await scheduler.tick() == 1
    assert channel.last["text"] == "⏰ Reminder: DS assignment"


async def test_non_utc_user_gets_local_times(session_factory, clock, channel):
    await add_reminder(session_factory, clock, timedelta(days=3), timezone="America/New_York")
    scheduler = make_scheduler(session_factory, channel, clock)
    clock.advance(days=2)
    await scheduler.tick()
    # Deadline is 14:30 UTC on Sat 21 Nov = 9:30 AM in New York (EST).
    assert "Due Sat 21 Nov, 9:30 AM" in channel.last["text"]


async def test_alerts_missed_while_the_bot_was_off_are_sent_late(session_factory, clock, channel):
    await add_reminder(session_factory, clock, timedelta(hours=10))  # alerts at -3h and -30m
    clock.advance(hours=11)  # the bot was off until after the deadline
    scheduler = make_scheduler(session_factory, channel, clock)
    assert await scheduler.tick() == 2
    assert "It was due" in channel.last["text"]  # a late message says the deadline passed


async def test_deleted_reminder_sends_nothing(session_factory, clock, channel):
    reminder_id = await add_reminder(session_factory, clock, timedelta(days=3))
    await ReminderService(SqlReminderStore(session_factory), clock).delete(1, reminder_id)
    clock.advance(days=3)
    assert await make_scheduler(session_factory, channel, clock).tick() == 0
    assert channel.sent == []


async def test_alert_of_an_inactive_reminder_is_cancelled_not_sent(session_factory, clock, channel):
    # E.g. the reminder was marked done in the same moment the alert became due.
    reminder_id = await add_reminder(session_factory, clock, timedelta(hours=1))
    async with session_factory() as session:
        reminder = await session.get(Reminder, reminder_id)
        reminder.status = ReminderStatus.DONE  # alerts still say "pending"
        await session.commit()

    clock.advance(minutes=30)
    assert await make_scheduler(session_factory, channel, clock).tick() == 0
    assert channel.sent == []
    [alert] = await alerts(session_factory)
    assert alert.status == AlertStatus.CANCELLED


# --- retries --------------------------------------------------------------------


async def test_failed_send_is_retried_with_backoff(session_factory, clock):
    await add_reminder(session_factory, clock, timedelta(hours=1))  # one alert, in 30 min
    channel = FlakyChannel(failures=2)
    scheduler = make_scheduler(session_factory, channel, clock)

    clock.advance(minutes=30)
    assert await scheduler.tick() == 0  # attempt 1 fails -> retry in 1 minute
    [alert] = await alerts(session_factory)
    assert alert.status == AlertStatus.PENDING and alert.attempts == 1
    assert alert.next_attempt_at == clock.now() + timedelta(minutes=1)
    assert alert.last_error == "ConnectionError"

    clock.advance(seconds=30)
    assert await scheduler.tick() == 0  # too early for the retry: nothing happens
    assert (await alerts(session_factory))[0].attempts == 1

    clock.advance(seconds=30)
    assert await scheduler.tick() == 0  # attempt 2 fails -> retry in 5 minutes
    [alert] = await alerts(session_factory)
    assert alert.next_attempt_at == clock.now() + timedelta(minutes=5)

    clock.advance(minutes=5)
    assert await scheduler.tick() == 1  # attempt 3 works
    [alert] = await alerts(session_factory)
    assert alert.status == AlertStatus.SENT and alert.attempts == 3
    assert alert.sent_at == clock.now() and alert.last_error is None
    assert len(channel.sent) == 1


async def test_gives_up_after_5_attempts(session_factory, clock):
    await add_reminder(session_factory, clock, timedelta(hours=1))
    channel = FlakyChannel(failures=100)
    scheduler = make_scheduler(session_factory, channel, clock)

    clock.advance(minutes=30)
    for wait in [None, 1, 5, 15, 60]:  # minutes between attempts: 1m, 5m, 15m, 1h
        if wait:
            clock.advance(minutes=wait)
        await scheduler.tick()

    [alert] = await alerts(session_factory)
    assert alert.status == AlertStatus.FAILED and alert.attempts == 5

    clock.advance(days=1)
    await scheduler.tick()
    assert (await alerts(session_factory))[0].attempts == 5  # no 6th attempt
    assert channel.sent == []


async def test_unknown_channel_counts_as_a_failure(session_factory, clock):
    await add_reminder(session_factory, clock, timedelta(hours=1))
    scheduler = Scheduler(session_factory, {}, clock)  # no channels at all
    clock.advance(minutes=30)
    assert await scheduler.tick() == 0
    [alert] = await alerts(session_factory)
    assert alert.status == AlertStatus.PENDING and alert.last_error == "LookupError"


# --- restarts and crashes -------------------------------------------------------


async def test_restart_mid_day_neither_loses_nor_double_sends(session_factory, clock, channel):
    start = clock.now()
    await add_reminder(session_factory, clock, timedelta(hours=20))  # alerts at 17h and 19h30
    await add_reminder(session_factory, clock, timedelta(hours=6))  # alerts at 3h and 5h30

    first = make_scheduler(session_factory, channel, clock)
    clock.set(start + timedelta(hours=3))
    assert await first.tick() == 1  # second reminder's 3-hour alert

    # The bot restarts: a brand-new Scheduler, same database, nothing kept in memory.
    second = make_scheduler(session_factory, channel, clock)
    assert await second.tick() == 0  # does not resend what was already sent

    for _ in range(26 * 2):  # tick every 30 minutes for the rest of the day
        clock.advance(minutes=30)
        await second.tick()

    assert len(channel.sent) == 4  # every alert exactly once
    assert {a.status for a in await alerts(session_factory)} == {AlertStatus.SENT}


async def test_two_schedulers_at_once_send_each_alert_once(session_factory, clock, channel):
    await add_reminder(session_factory, clock, timedelta(hours=1))
    clock.advance(minutes=30)
    a = make_scheduler(session_factory, channel, clock)
    b = make_scheduler(session_factory, channel, clock)
    sent = await a.tick() + await b.tick()
    assert sent == 1 and len(channel.sent) == 1


async def test_two_schedulers_racing_on_the_same_alert(session_factory, clock):
    # Both found the alert due; only the first conditional UPDATE wins the claim.
    await add_reminder(session_factory, clock, timedelta(hours=1))
    clock.advance(minutes=30)
    now = clock.now()
    [alert] = await alerts(session_factory)
    results = []
    for _ in range(2):
        async with session_factory() as session:
            results.append(await AlertRepo(session).claim(alert.id, now, now - loop.STALE_CLAIM))
            await session.commit()
    assert results == [True, False]


async def test_crash_before_sending_is_retried_after_5_minutes(
    session_factory, clock, channel, monkeypatch
):
    await add_reminder(session_factory, clock, timedelta(hours=1))
    clock.advance(minutes=30)

    async def crash(*_args):
        raise Crash

    with monkeypatch.context() as patch:
        patch.setattr(channel, "send_buttons", crash)
        with pytest.raises(Crash):
            await make_scheduler(session_factory, channel, clock).tick()
    [alert] = await alerts(session_factory)
    assert alert.status == AlertStatus.SENDING  # claimed, then the process died

    restarted = make_scheduler(session_factory, channel, clock)
    clock.advance(minutes=4)
    assert await restarted.tick() == 0  # maybe the first process is just slow: wait

    clock.advance(minutes=1)
    assert await restarted.tick() == 1  # stuck for 5 minutes: send it
    assert len(channel.sent) == 1
    [alert] = await alerts(session_factory)
    assert alert.status == AlertStatus.SENT and alert.attempts == 2


async def test_crash_right_after_sending_gives_one_duplicate(
    session_factory, clock, channel, monkeypatch
):
    # Telegram got the message but we died before saving "sent". We can't know it
    # went out, so we send again: a rare duplicate is better than a missed reminder.
    await add_reminder(session_factory, clock, timedelta(hours=1))
    clock.advance(minutes=30)

    async def crash(*_args):
        raise Crash

    with monkeypatch.context() as patch:
        patch.setattr(AlertRepo, "mark_sent", crash)
        with pytest.raises(Crash):
            await make_scheduler(session_factory, channel, clock).tick()
    assert len(channel.sent) == 1

    restarted = make_scheduler(session_factory, channel, clock)
    clock.advance(minutes=5)
    assert await restarted.tick() == 1
    assert len(channel.sent) == 2  # the duplicate
    clock.advance(hours=1)
    assert await restarted.tick() == 0  # but never a third time


# --- the loop itself ------------------------------------------------------------


async def test_run_forever_keeps_going_after_a_failed_tick(session_factory, clock, monkeypatch):
    scheduler = make_scheduler(session_factory, FakeChannel(), clock)
    ticks = []

    async def bad_tick():
        ticks.append(1)
        raise RuntimeError("database hiccup")

    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 3:
            raise asyncio.CancelledError  # stop the loop, like a shutdown would

    monkeypatch.setattr(scheduler, "tick", bad_tick)
    monkeypatch.setattr(loop, "sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        await scheduler.run_forever()
    assert len(ticks) == 3 and sleeps == [30, 30, 30]
