"""Channel-agnostic bot logic: decides how to answer each IncomingEvent.

Telegram (and later WhatsApp) adapters call Router.handle(); the router replies
through the Channel interface, so the same logic works on every channel and is
easy to test with a fake channel.
"""

from reminderbot.channels.base import Button, Channel, IncomingEvent, parse_command
from reminderbot.channels.manage import PICKERS, ReminderCommands
from reminderbot.channels.natural import CLARIFY_PREFIX, NaturalLanguage
from reminderbot.channels.replies import send_confirmation
from reminderbot.clock import Clock
from reminderbot.core.formatting import format_time
from reminderbot.core.reminders import MAX_TITLE_LENGTH, ReminderService
from reminderbot.core.timeparse import TimeParseError, parse_when, split_remind_args
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
    def __init__(
        self,
        users: UserService,
        reminders: ReminderService,
        natural: NaturalLanguage,
        clock: Clock,
    ) -> None:
        self._users = users
        self._reminders = reminders
        self._natural = natural  # plain-language messages (M4)
        self._manage = ReminderCommands(reminders, natural, clock)  # /list, /done, ... (M5)
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

        command, args = parse_command(event.text)
        if command == "start":
            await self._on_start(event, user, channel)
        elif command == "remind":
            await self._on_remind(event, user, channel, args)
        elif command == "timezone":
            await self._ask_timezone(event, user, channel, t("tz.choose", user.language))
        elif command == "help":
            await channel.send_message(event.chat_id, t("help.text", user.language))
        elif command in ("list", "today", "week"):
            await self._manage.on_list(
                event, user, channel, which="all" if command == "list" else command
            )
        elif command in PICKERS:  # done, delete, edit
            await self._manage.on_pick(event, user, channel, action=command)
        elif command is not None:
            await channel.send_message(event.chat_id, t("command.unknown", user.language))
        elif user.awaiting_timezone:
            await self._save_timezone(event, user, channel, event.text)
        else:
            await self._natural.on_text(event, user, channel)

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
        if await self._manage.on_button(event, user, channel, data):
            return  # done / delete / edit / snooze
        if data.startswith(CLARIFY_PREFIX):
            await self._natural.on_button(event, user, channel, data.removeprefix(CLARIFY_PREFIX))
            return
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

    async def _on_remind(
        self, event: IncomingEvent, user: UserProfile, channel: Channel, args: str
    ) -> None:
        lang = user.language
        now = self._clock.now()
        try:
            when_text, title = split_remind_args(args)
            when = parse_when(when_text, user.timezone, now)
        except TimeParseError as error:
            if error.reason == "remind.usage":
                text = t("remind.usage", lang)
            elif error.reason == "remind.past":
                # Show the time they asked for, so they can see what went wrong.
                text = t("remind.past", lang, due=when_text)
            else:
                text = t("remind.bad_when", lang, when=when_text)
            await channel.send_message(event.chat_id, text)
            return
        if len(title) > MAX_TITLE_LENGTH:
            await channel.send_message(
                event.chat_id, t("remind.too_long", lang, max=MAX_TITLE_LENGTH)
            )
            return

        saved = await self._reminders.create(
            user.id, title, when.due_at_utc, when.kind, source_text=event.text
        )
        log.info(
            "reminder_created",
            reminder_id=saved.id,
            kind=str(saved.kind),
            alerts=len(saved.alert_times),
        )

        await send_confirmation(channel, event.chat_id, saved, user, now, when.time_defaulted)
