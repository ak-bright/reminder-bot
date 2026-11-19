"""Find due alerts in the database and send them (CLAUDE.md rule 3).

There are no in-memory timers: every tick asks the database what is due, so a
restart loses nothing. Each alert goes through these steps:

    pending --claim--> sending --sent ok--> sent
                          |
                          +--send failed--> pending again, retry after 1m, 5m, 15m, 1h
                                            (failed after 5 attempts)

If the bot crashes while an alert is `sending`, the alert is retried once it has
been stuck for 5 minutes. If the crash happened just after Telegram accepted the
message, the user gets it twice. That is our decision: a rare duplicate is
acceptable, a missed reminder is not.
"""

from asyncio import sleep
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reminderbot.channels.base import Channel
from reminderbot.clock import Clock
from reminderbot.core.formatting import format_datetime, format_duration
from reminderbot.core.models import ReminderKind, ReminderStatus
from reminderbot.db.models import Alert
from reminderbot.db.repositories import AlertRepo
from reminderbot.logging_setup import get_logger
from reminderbot.strings import t

log = get_logger(__name__)

# Wait before retry number 1, 2, 3, 4. The 5th failure is final.
BACKOFF = [
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(hours=1),
]
MAX_ATTEMPTS = 5
STALE_CLAIM = timedelta(minutes=5)


class Scheduler:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        channels: dict[str, Channel],
        clock: Clock,
        interval_seconds: float = 30,
    ) -> None:
        self._session_factory = session_factory
        self._channels = channels  # e.g. {"telegram": TelegramChannel(...)}
        self._clock = clock
        self._interval = interval_seconds

    async def run_forever(self) -> None:
        """Tick every `interval_seconds` until the task is cancelled (bot shutdown)."""
        log.info("scheduler_started", interval_seconds=self._interval)
        while True:
            try:
                await self.tick()
            except Exception:  # noqa: BLE001 - one bad tick must not stop all reminders
                log.exception("scheduler_tick_failed")
            await sleep(self._interval)

    async def tick(self) -> int:
        """Send everything that is due right now. Returns how many alerts were sent."""
        now = self._clock.now()
        stale_before = now - STALE_CLAIM
        async with self._session_factory() as session:
            alert_ids = await AlertRepo(session).due_ids(now, stale_before)

        sent = 0
        for alert_id in alert_ids:
            if await self._process(alert_id, now, stale_before):
                sent += 1
        return sent

    async def _process(self, alert_id: int, now: datetime, stale_before: datetime) -> bool:
        # Step 1: claim it and COMMIT before sending, so any other scheduler
        # (e.g. a second copy of the bot) can see it is taken.
        async with self._session_factory() as session:
            if not await AlertRepo(session).claim(alert_id, now, stale_before):
                return False  # someone else got it first
            await session.commit()

        # Step 2: send it and record the result.
        async with self._session_factory() as session:
            alerts = AlertRepo(session)
            alert = await alerts.get_for_sending(alert_id)
            if alert is None:  # deleted in the meantime (e.g. its user was removed)
                return False
            if alert.reminder.status != ReminderStatus.ACTIVE:
                await alerts.mark_cancelled(alert)
                await session.commit()
                return False

            try:
                await self._send(alert, now)
            except Exception as exc:  # noqa: BLE001 - any send error means "try again later"
                retry_at = self._retry_time(alert.attempts, now)
                await alerts.record_failure(alert, type(exc).__name__, retry_at)
                await session.commit()
                log.warning(
                    "alert_send_failed",
                    alert_id=alert.id,
                    attempt=alert.attempts,
                    error=type(exc).__name__,
                    gave_up=retry_at is None,
                )
                return False

            await alerts.mark_sent(alert, now)
            await session.commit()
            log.info("alert_sent", alert_id=alert.id, attempt=alert.attempts)
            return True

    async def _send(self, alert: Alert, now: datetime) -> None:
        user = alert.reminder.user
        channel = self._channels.get(user.channel)
        if channel is None:
            raise LookupError(f"no channel called {user.channel!r}")
        # Private chats only, so the chat to write to has the same id as the user.
        await channel.send_message(user.channel_user_id, alert_text(alert, now))

    @staticmethod
    def _retry_time(attempts: int, now: datetime) -> datetime | None:
        """When to try again after `attempts` failed tries, or None to give up."""
        if attempts >= MAX_ATTEMPTS:
            return None
        return now + BACKOFF[attempts - 1]


def alert_text(alert: Alert, now: datetime) -> str:
    reminder = alert.reminder
    user = reminder.user
    if reminder.kind == ReminderKind.AT_TIME:
        return t("alert.at_time", user.language, title=reminder.title)

    due = format_datetime(reminder.due_at_utc, user.timezone)
    if reminder.due_at_utc <= now:  # a late retry can arrive after the deadline
        return t("alert.deadline_passed", user.language, title=reminder.title, due=due)
    left = format_duration(reminder.due_at_utc - now, user.language)
    return t("alert.deadline", user.language, title=reminder.title, due=due, left=left)
