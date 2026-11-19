# ReminderBot

A Telegram bot that makes sure university students never miss assignments, quizzes and deadlines.

**Status:** M1 (skeleton). `/start` onboarding with timezone selection, `/timezone` and `/help`.

## Run locally (Windows / PowerShell)

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Set up the project:
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -e ".[dev]"
   copy .env.example .env      # then paste your token into TELEGRAM_BOT_TOKEN
   ```
3. Start the bot: `python -m reminderbot`
4. Open your bot in Telegram and send `/start`.

## Tests and lint
```powershell
pytest -q
ruff check .
ruff format --check .
```

See `CLAUDE.md` for the architecture and the project rules.
