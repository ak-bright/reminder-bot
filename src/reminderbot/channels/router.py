"""Channel-agnostic bot logic: decides how to answer each IncomingEvent.

Telegram (and later WhatsApp) adapters call Router.handle(); the router replies
through the Channel interface, so the same logic works on every channel and is
easy to test with a fake channel.
"""

from reminderbot.channels.base import Button, Channel, IncomingEvent, parse_command
from reminderbot.clock import Clock
from reminderbot.core.formatting import format_time
from reminderbot.core.users import UserProfile, UserService
from reminderbot.logging_setup import get_logger
from reminderbot.strings import t

log = get_logger(__name__)

# Button data prefix for timezone choices, e.g. "tz:Africa/Accra" or "tz:other".
TZ_PREFIX = "tz:"
TZ_OTHER = "other"
QUICK_TIMEZONES = [
    ("tz.button.accra", "Africa/Accra"),
    ("tz.button.lagos", "Africa/Lagos"),
    ("tz.button.london", "Europe/London"),
]


def timezone_buttons(lang: str) -> list[list[Button]]:
    row = [Button(t(key, lang), TZ_PREFIX + tz) for key, tz in QUICK_TIMEZONES]
    return [row, [Button(t("tz.button.other", lang), TZ_PREFIX + TZ_OTHER)]]


class Router:
    def __init__(self, users: UserService, clock: Clock) -> None:
        self._users = users
        self._clock = clock

    async def handle(self, event: IncomingEvent, channel: Channel) -> None:
        user = await self._users.get_or_create(
            event.channel, event.channel_user_id, event.display_name
        )
        # Log ids and sizes only, never the message text (CLAUDE.md rule 7).
        log.info(
            "event_received",
            channel=event.channel,
            user=event.channel_user_id,
            text_len=len(event.text),
            is_button=event.button_data is not None,
        )

        if event.button_data is not None:
            await self._on_button(event, user, channel)
            return

        command, _args = parse_command(event.text)
        if command == "start":
            await self._on_start(event, user, channel)
        elif command == "timezone":
            await self._ask_timezone(event, user, channel, t("tz.choose", user.language))
        elif command == "help":
            await channel.send_message(event.chat_id, t("help.text", user.language))
        elif command is not None:
            await channel.send_message(event.chat_id, t("command.unknown", user.language))
        elif user.awaiting_timezone:
            await self._save_timezone(event, user, channel, event.text)
        else:
            await channel.send_message(event.chat_id, t("fallback.not_yet", user.language))

    async def _on_start(self, event: IncomingEvent, user: UserProfile, channel: Channel) -> None:
        name = user.name or t("start.friend", user.language)
        if user.is_new:
            text = t("start.welcome", user.language, name=name)
            await self._ask_timezone(event, user, channel, text)
        else:
            text = t("start.welcome_back", user.language, name=name, timezone=user.timezone)
            await channel.send_message(event.chat_id, text)

    async def _ask_timezone(
        self, event: IncomingEvent, user: UserProfile, channel: Channel, text: str
    ) -> None:
        await channel.send_buttons(event.chat_id, text, timezone_buttons(user.language))

    async def _on_button(self, event: IncomingEvent, user: UserProfile, channel: Channel) -> None:
        data = event.button_data or ""
        if not data.startswith(TZ_PREFIX):
            log.warning("unknown_button", data_len=len(data))
            return
        choice = data.removeprefix(TZ_PREFIX)
        if choice == TZ_OTHER:
            await self._users.set_awaiting_timezone(user, True)
            await channel.send_message(event.chat_id, t("tz.ask_other", user.language))
        else:
            await self._save_timezone(event, user, channel, choice)

    async def _save_timezone(
        self, event: IncomingEvent, user: UserProfile, channel: Channel, typed: str
    ) -> None:
        timezone = await self._users.set_timezone(user, typed)
        if timezone is None:
            # Keep waiting; the user can simply type another name.
            await channel.send_message(event.chat_id, t("tz.invalid", user.language, value=typed))
            return
        local_time = format_time(self._clock.now(), timezone)
        await channel.send_message(
            event.chat_id,
            t("tz.saved", user.language, timezone=timezone, local_time=local_time),
        )
