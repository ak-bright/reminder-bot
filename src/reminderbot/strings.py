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
            "Here's what I can do right now:\n\n"
            "/remind <when> | <what> - add a reminder, for example\n"
            "   /remind 2026-11-21 17:00 | DS assignment\n"
            "   /remind tomorrow 9:00 | Quiz on chapter 4\n"
            "   /remind in 2h | Call my group leader\n"
            "/start - set up the bot\n"
            "/timezone - change your timezone\n"
            "/help - show this message\n\n"
            "Coming soon: just type things like\n"
            '• "Data structures assignment due Friday 5pm"\n'
            '• "quiz on chapter 4 next Tuesday morning"\n'
            "and I'll remind you before the deadline."
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
            "I can't understand plain messages yet. That's coming soon! "
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
