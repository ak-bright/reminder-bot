"""Looking after existing reminders (M5): /list /today /week /done /delete /edit,
and the buttons under alerts and confirmations.

Users never type reminder ids. /done, /delete and /edit show one button per
reminder, and each button carries the id, e.g. "done:17". The store checks the
reminder belongs to the user who pressed it, so guessing ids gets you nothing.
"""

from reminderbot.channels.base import Button, Channel, IncomingEvent
from reminderbot.channels.natural import NaturalLanguage
from reminderbot.channels.replies import (
    DELETE_PREFIX,
    DONE_PREFIX,
    EDIT_PREFIX,
    SNOOZE_HOUR_PREFIX,
    SNOOZE_TOMORROW_PREFIX,
)
from reminderbot.clock import Clock
from reminderbot.core.formatting import format_datetime
from reminderbot.core.reminders import ReminderInfo, ReminderService
from reminderbot.core.users import UserProfile
from reminderbot.logging_setup import get_logger
from reminderbot.strings import t

log = get_logger(__name__)

MAX_SHOWN = 30  # longest list we print
MAX_PICKER_BUTTONS = 10  # /done etc. show the 10 soonest
PICKER_TITLE_CHARS = 30

# Which button prefix each picker command uses.
PICKERS = {"done": DONE_PREFIX, "delete": DELETE_PREFIX, "edit": EDIT_PREFIX}


class ReminderCommands:
    def __init__(self, reminders: ReminderService, natural: NaturalLanguage, clock: Clock) -> None:
        self._reminders = reminders
        self._natural = natural  # /edit asks for the new time like any other question
        self._clock = clock

    # --- /list, /today, /week ---------------------------------------------------

    async def on_list(
        self, event: IncomingEvent, user: UserProfile, channel: Channel, which: str
    ) -> None:
        if which == "today":
            items = await self._reminders.list_due_today(user.id, user.timezone)
        elif which == "week":
            items = await self._reminders.list_next_days(user.id, days=7)
        else:
            items = await self._reminders.list_active(user.id)
        await channel.send_message(event.chat_id, self._list_text(items, user, which))

    def _list_text(self, items: list[ReminderInfo], user: UserProfile, which: str) -> str:
        lang = user.language
        if not items:
            return t(f"list.empty.{which}", lang)
        now = self._clock.now()
        lines = [t(f"list.header.{which}", lang)]
        for number, item in enumerate(items[:MAX_SHOWN], start=1):
            due = format_datetime(item.due_at_utc, user.timezone)
            line = t("list.item", lang, n=number, title=item.title, due=due)
            if item.is_overdue(now):
                line += " " + t("list.overdue", lang)
            lines.append(line)
        if len(items) > MAX_SHOWN:
            lines.append(t("list.more", lang, count=len(items) - MAX_SHOWN))
        return "\n".join(lines)

    # --- /done, /delete, /edit: "which one?" ----------------------------------------

    async def on_pick(
        self, event: IncomingEvent, user: UserProfile, channel: Channel, action: str
    ) -> None:
        items = await self._reminders.list_active(user.id)
        if not items:
            await channel.send_message(event.chat_id, t("list.empty.all", user.language))
            return
        prefix = PICKERS[action]
        rows = [
            [Button(self._picker_label(item, user), f"{prefix}{item.id}")]
            for item in items[:MAX_PICKER_BUTTONS]
        ]
        await channel.send_buttons(event.chat_id, t(f"pick.{action}", user.language), rows)

    def _picker_label(self, item: ReminderInfo, user: UserProfile) -> str:
        title = item.title
        if len(title) > PICKER_TITLE_CHARS:
            title = title[: PICKER_TITLE_CHARS - 1] + "…"
        label = f"{title} · {format_datetime(item.due_at_utc, user.timezone)}"
        return ("⚠️ " + label) if item.is_overdue(self._clock.now()) else label

    # --- buttons --------------------------------------------------------------------

    async def on_button(
        self, event: IncomingEvent, user: UserProfile, channel: Channel, data: str
    ) -> bool:
        """Handle a reminder button. Returns False if `data` isn't one of ours."""
        for prefix, handler in (
            (DONE_PREFIX, self._done),
            (DELETE_PREFIX, self._delete),
            (EDIT_PREFIX, self._edit),
            (SNOOZE_HOUR_PREFIX, self._snooze_hour),
            (SNOOZE_TOMORROW_PREFIX, self._snooze_tomorrow),
        ):
            if data.startswith(prefix):
                raw_id = data.removeprefix(prefix)
                # Button data comes from the user's device, so check it before trusting it.
                if not raw_id.isdigit():
                    log.warning("bad_reminder_button", data_len=len(data))
                    return True
                await handler(event, user, channel, int(raw_id))
                return True
        return False

    async def _done(
        self, event: IncomingEvent, user: UserProfile, channel: Channel, reminder_id: int
    ) -> None:
        info = await self._reminders.done(user.id, reminder_id)
        if info is None:
            await channel.send_message(event.chat_id, t("reminder.gone", user.language))
            return
        log.info("reminder_done", reminder_id=reminder_id)
        await channel.send_message(event.chat_id, t("done.ok", user.language, title=info.title))

    async def _delete(
        self, event: IncomingEvent, user: UserProfile, channel: Channel, reminder_id: int
    ) -> None:
        deleted = await self._reminders.delete(user.id, reminder_id)
        key = "remind.deleted" if deleted else "remind.already_gone"
        await channel.send_message(event.chat_id, t(key, user.language))

    async def _edit(
        self, event: IncomingEvent, user: UserProfile, channel: Channel, reminder_id: int
    ) -> None:
        info = await self._reminders.get(user.id, reminder_id)
        if info is None:
            await channel.send_message(event.chat_id, t("reminder.gone", user.language))
            return
        await self._natural.ask_new_time(event, user, channel, info)

    async def _snooze_hour(
        self, event: IncomingEvent, user: UserProfile, channel: Channel, reminder_id: int
    ) -> None:
        await self._snooze(event, user, channel, reminder_id, "1h")

    async def _snooze_tomorrow(
        self, event: IncomingEvent, user: UserProfile, channel: Channel, reminder_id: int
    ) -> None:
        await self._snooze(event, user, channel, reminder_id, "tomorrow")

    async def _snooze(
        self,
        event: IncomingEvent,
        user: UserProfile,
        channel: Channel,
        reminder_id: int,
        until: str,
    ) -> None:
        result = await self._reminders.snooze(user.id, reminder_id, user.timezone, until)
        if result is None:
            await channel.send_message(event.chat_id, t("reminder.gone", user.language))
            return
        info, send_at = result
        when = format_datetime(send_at, user.timezone)
        log.info("reminder_snoozed", reminder_id=reminder_id, until=until)
        await channel.send_message(
            event.chat_id, t("snooze.ok", user.language, title=info.title, when=when)
        )
