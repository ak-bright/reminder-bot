"""Every user-facing message lives here (CLAUDE.md rule 10).

To add a language later, add another dict to STRINGS with the same keys.
Use placeholders like {name} and fill them through t(..., name="Ama").
"""

DEFAULT_LANGUAGE = "en"

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        # /start onboarding
        "start.welcome": (
            "Hi {name}! 👋 I'm ReminderBot.\n"
            "I make sure you never miss an assignment, quiz or deadline.\n\n"
            "First, which timezone are you in? Most students in Ghana use Africa/Accra."
        ),
        "start.welcome_back": (
            "Welcome back, {name}! Your timezone is {timezone}.\n"
            "Type /help to see what I can do, or /timezone to change it."
        ),
        "start.friend": "friend",
        # timezone selection
        "tz.choose": "Which timezone are you in?",
        "tz.button.accra": "Accra (default)",
        "tz.button.lagos": "Lagos",
        "tz.button.london": "London",
        "tz.button.other": "Other…",
        "tz.ask_other": (
            "Type your timezone, for example Africa/Nairobi, Europe/Paris or just Nairobi."
        ),
        "tz.invalid": (
            'I don\'t recognise "{value}" as a timezone. '
            "Try something like Africa/Accra, Europe/London or Nairobi."
        ),
        "tz.saved": (
            "Done! Your timezone is {timezone}. Your local time now is {local_time}.\n\n"
            "Type /help to see what I can do."
        ),
        # /help
        "help.text": (
            "Just tell me what's due and when, in your own words:\n"
            '• "Data structures assignment due Friday 5pm"\n'
            '• "quiz on chapter 4 next Tuesday morning"\n'
            '• "remind me in 2 hours to call my group leader"\n'
            '• "two assignments: stats Friday, physics Monday"\n'
            "I'll remind you 1 day, 3 hours and 30 minutes before each deadline.\n\n"
            "Commands:\n"
            "/list - all your reminders (/today, /week for less)\n"
            "/done - mark one as done (no more alerts)\n"
            "/edit - change the time of one\n"
            "/delete - delete one\n"
            "/remind <when> | <what> - the strict format, for example\n"
            "   /remind 2026-11-21 17:00 | DS assignment\n"
            "   /remind tomorrow 9:00 | Quiz on chapter 4\n"
            "   /remind in 2h | Call my group leader\n"
            "/start - set up the bot\n"
            "/timezone - change your timezone\n"
            "/help - show this message"
        ),
        # /remind
        "remind.usage": (
            "To add a reminder, type /remind <when> | <what>\n\n"
            "<when> can be:\n"
            "• 2026-11-21 17:00 (date and 24-hour time)\n"
            "• 2026-11-21 (I'll use 8:00 AM)\n"
            "• today 17:00, tomorrow 9:00, or just tomorrow\n"
            "• in 30m, in 2h, in 3d\n\n"
            "Example: /remind tomorrow 17:00 | DS assignment"
        ),
        "remind.bad_when": (
            'I couldn\'t read "{when}" as a time. '
            "Try 2026-11-21 17:00, tomorrow 9:00 or in 2h. Type /remind for all options."
        ),
        "remind.past": "{due} has already passed. Please pick a time in the future.",
        "remind.too_long": "That description is too long. Please keep it under {max} characters.",
        "remind.saved_deadline": "Got it. {title}, due {due}. I'll remind you {alerts}.",
        "remind.saved_at_time": "Got it. I'll remind you on {due}: {title}",
        "remind.default_time": "(You didn't give a time, so I used 8:00 AM.)",
        "remind.alert_before": "{duration} before",
        "remind.alert_now": "right away",
        "remind.deleted": "Deleted. I won't remind you about that.",
        "remind.already_gone": "That reminder is already deleted.",
        "button.delete": "Delete",
        "button.cancel": "Cancel",
        "button.edit": "Edit",
        "button.done": "✅ Done",
        "button.snooze_hour": "Snooze 1h",
        "button.snooze_tomorrow": "Snooze tomorrow",
        # /list, /today, /week (M5)
        "list.header.all": "📋 Your reminders:",
        "list.header.today": "📅 Due today:",
        "list.header.week": "🗓 Due in the next 7 days:",
        "list.empty.all": (
            "You have no reminders. Tell me what's due, "
            'for example "DS assignment due Friday 5pm".'
        ),
        "list.empty.today": "Nothing due today. 🎉",
        "list.empty.week": "Nothing due in the next 7 days. 🎉",
        "list.item": "{n}. {title} - {due}",
        "list.overdue": "⚠️ overdue",
        "list.more": "…and {count} more.",
        # Telegram's "/" menu (short descriptions)
        "menu.list": "All your reminders",
        "menu.today": "What's due today",
        "menu.week": "What's due in the next 7 days",
        "menu.done": "Mark a reminder as done",
        "menu.edit": "Change the time of a reminder",
        "menu.delete": "Delete a reminder",
        "menu.remind": "Add a reminder in the strict format",
        "menu.timezone": "Change your timezone",
        "menu.help": "What I can do",
        # /done, /delete, /edit and the buttons under alerts
        "pick.done": "Which one is done?",
        "pick.delete": "Which one should I delete?",
        "pick.edit": "Which one do you want to change?",
        "done.ok": '✅ Well done! "{title}" is marked done. No more reminders for it.',
        "snooze.ok": 'OK, I\'ll remind you about "{title}" again on {when}.',
        "reminder.gone": "That reminder is already done or deleted.",
        "edit.ask": (
            'When is "{title}" due now? Reply with the new day and time, for example: Friday 5pm.'
        ),
        # plain-language messages (M4)
        "nl.too_long": "That message is too long for me. Please keep it under {max} characters.",
        "nl.not_understood": (
            "I couldn't find a task and a time in that. "
            'Try something like "DS assignment due Friday 5pm", or type /help.'
        ),
        "nl.question_not_yet": (
            "That sounds like a question. I can't answer questions yet (coming soon!).\n"
            "To add a reminder, tell me what's due and when, "
            'e.g. "DS assignment due Friday 5pm".'
        ),
        "nl.passed": '"{title}": that time has already passed, so I didn\'t save it.',
        "ai.unavailable": (
            "Sorry, I can't read plain messages right now. Please try again in a moment, "
            "or use /remind (type /help for examples)."
        ),
        # clarifying questions: one at a time, with buttons (CLAUDE.md rule 5)
        "clarify.weekday_today": '"{title}": do you mean today, or {weekday} next week?',
        "clarify.next_weekday": '"{title}": which {weekday} do you mean?',
        "clarify.which_day": '"{title}": which day next week?',
        "clarify.when": 'When is "{title}"? Reply with a day and time, for example: Friday 5pm.',
        "clarify.past": (
            '"{title}": that time has already passed. '
            "Reply with a new day and time, for example: tomorrow 9am."
        ),
        "clarify.confirm": (
            '"{title}": did you mean {due}? Tap to confirm, or reply with the right day and time.'
        ),
        "clarify.cancelled": 'OK, I won\'t save "{title}".',
        "clarify.didnt_get": "Sorry, I didn't catch a day or time in that.",
        "clarify.expired": "That question has expired. Please send the reminder again.",
        # alerts sent by the scheduler
        "alert.deadline": "⏰ Reminder: {title}\nDue {due} (in {left}).",
        "alert.deadline_passed": "⏰ Reminder: {title}\nIt was due {due}.",
        "alert.at_time": "⏰ Reminder: {title}",
        # small building blocks
        "duration.minute": "{n} minute",
        "duration.minutes": "{n} minutes",
        "duration.hour": "{n} hour",
        "duration.hours": "{n} hours",
        "duration.day": "{n} day",
        "duration.days": "{n} days",
        "list.and": "{first} and {last}",
        # fallbacks
        "fallback.not_yet": (
            "Plain-language messages aren't switched on for this bot. "
            "For now, use /remind (type /help for examples)."
        ),
        "command.unknown": "I don't know that command. Try /help.",
        "error.generic": "Sorry, something went wrong on my side. Please try again in a moment.",
    },
}


def t(key: str, lang: str = DEFAULT_LANGUAGE, **kwargs: object) -> str:
    """Translate `key` into `lang` and fill in placeholders.

    Falls back to English if the language or key is missing, so a half-finished
    translation never crashes the bot.
    """
    table = STRINGS.get(lang, STRINGS[DEFAULT_LANGUAGE])
    template = table.get(key) or STRINGS[DEFAULT_LANGUAGE][key]
    return template.format(**kwargs)
