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
            "/start - set up the bot\n"
            "/timezone - change your timezone\n"
            "/help - show this message\n\n"
            "Coming soon: just type things like\n"
            '• "Data structures assignment due Friday 5pm"\n'
            '• "quiz on chapter 4 next Tuesday morning"\n'
            "and I'll remind you before the deadline."
        ),
        # fallbacks
        "fallback.not_yet": (
            "I can't understand plain messages yet. That's coming soon! For now, try /help."
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
