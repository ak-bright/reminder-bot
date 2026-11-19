"""Entry point: this is the only place where all the pieces are wired together."""

import sys

from pydantic import ValidationError

from reminderbot.channels.router import Router
from reminderbot.channels.telegram.app import build_application, run_polling
from reminderbot.clock import SystemClock
from reminderbot.config import Settings
from reminderbot.core.users import InMemoryUserStore, UserService
from reminderbot.logging_setup import get_logger, setup_logging


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

    users = UserService(InMemoryUserStore(), settings.default_timezone)
    router = Router(users, SystemClock())
    app = build_application(settings.telegram_bot_token.get_secret_value(), router)

    log.info("bot_starting", mode="polling", default_timezone=settings.default_timezone)
    run_polling(app)


if __name__ == "__main__":
    main()
