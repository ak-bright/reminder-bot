"""Replies shared by /remind and plain-language messages: the "Got it. ..." confirmation."""

from datetime import datetime

from reminderbot.channels.base import Button, Channel
from reminderbot.core.formatting import format_datetime, format_duration, join_list
from reminderbot.core.models import ReminderKind
from reminderbot.core.reminders import SavedReminder
from reminderbot.core.users import UserProfile
from reminderbot.strings import t

# Button data is "<prefix><reminder id>", e.g. "del:123" (short, well under Telegram's 64 bytes).
DELETE_PREFIX = "del:"
DONE_PREFIX = "done:"
EDIT_PREFIX = "edit:"
SNOOZE_HOUR_PREFIX = "sz1:"  # snooze 1 hour
SNOOZE_TOMORROW_PREFIX = "szt:"  # snooze until tomorrow morning


def confirmation_text(saved: SavedReminder, user: UserProfile, now: datetime) -> str:
    """'Got it. DS assignment, due Fri 21 Nov, 5:00 PM. I'll remind you 1 day before, ...'"""
    lang = user.language
    due = format_datetime(saved.due_at_utc, user.timezone)
    if saved.kind == ReminderKind.AT_TIME:
        return t("remind.saved_at_time", lang, title=saved.title, due=due)

    parts = []
    for when in saved.alert_times:
        if when <= now:
            parts.append(t("remind.alert_now", lang))
        else:
            before = format_duration(saved.due_at_utc - when, lang)
            parts.append(t("remind.alert_before", lang, duration=before))
    alerts = join_list(parts, lang)
    return t("remind.saved_deadline", lang, title=saved.title, due=due, alerts=alerts)


async def send_confirmation(
    channel: Channel,
    chat_id: str,
    saved: SavedReminder,
    user: UserProfile,
    now: datetime,
    time_defaulted: bool,
) -> None:
    text = confirmation_text(saved, user, now)
    if time_defaulted:
        text += "\n" + t("remind.default_time", user.language)
    lang = user.language
    buttons = [
        [
            Button(t("button.edit", lang), f"{EDIT_PREFIX}{saved.id}"),
            Button(t("button.delete", lang), f"{DELETE_PREFIX}{saved.id}"),
        ]
    ]
    await channel.send_buttons(chat_id, text, buttons)


def alert_buttons(reminder_id: int, lang: str) -> list[list[Button]]:
    """[Done] [Snooze 1h] [Snooze tomorrow] under every alert."""
    return [
        [
            Button(t("button.done", lang), f"{DONE_PREFIX}{reminder_id}"),
            Button(t("button.snooze_hour", lang), f"{SNOOZE_HOUR_PREFIX}{reminder_id}"),
            Button(t("button.snooze_tomorrow", lang), f"{SNOOZE_TOMORROW_PREFIX}{reminder_id}"),
        ]
    ]
