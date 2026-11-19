"""Entry point: this is the only place where all the pieces are wired together."""

import asyncio
import contextlib
import sys

from pydantic import ValidationError
from telegram.ext import Application

from reminderbot.channels.router import Router
from reminderbot.channels.telegram.adapter import TelegramChannel
from reminderbot.channels.telegram.app import build_application, run_polling
from reminderbot.clock import SystemClock
from reminderbot.config import Settings
from reminderbot.core.reminders import ReminderService
from reminderbot.core.users import UserService
from reminderbot.db.migrate import upgrade_to_latest
from reminderbot.db.reminder_store import SqlReminderStore
from reminderbot.db.session import create_engine, create_session_factory
from reminderbot.db.user_store import SqlUserStore
from reminderbot.logging_setup import get_logger, setup_logging
from reminderbot.scheduler.loop import Scheduler


def load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        # Show which env vars are missing or invalid, without printing their values.
        problems = "\n".join(
            f"  - {'.'.join(str(p) for p in err['loc']).upper()}: {err['msg']}"
            for err in exc.errors()
        )
        print(f"Configuration error. Check your .env file:\n{problems}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_level, settings.log_json)
    log = get_logger(__name__)

    # Create or update the database tables before anything uses them.
    upgrade_to_latest(settings.database_url)
    log.info("database_ready", dialect=settings.database_url.split(":", 1)[0])

    clock = SystemClock()
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    users = UserService(SqlUserStore(session_factory, clock), settings.default_timezone)
    reminders = ReminderService(SqlReminderStore(session_factory), clock)
    router = Router(users, reminders, clock)

    background: list[asyncio.Task] = []

    async def start_scheduler(app: Application) -> None:
        # Runs once the bot is connected, so app.bot is ready to send messages.
        channels = {TelegramChannel.name: TelegramChannel(app.bot)}
        scheduler = Scheduler(session_factory, channels, clock, settings.scheduler_interval_seconds)
        background.append(asyncio.create_task(scheduler.run_forever()))

    async def stop_everything(_app: Application) -> None:
        for task in background:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await engine.dispose()

    app = build_application(
        settings.telegram_bot_token.get_secret_value(),
        router,
        on_startup=start_scheduler,
        on_shutdown=stop_everything,
    )

    log.info("bot_starting", mode="polling", default_timezone=settings.default_timezone)
    run_polling(app)


if __name__ == "__main__":
    main()
