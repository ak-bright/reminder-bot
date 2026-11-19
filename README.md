# ReminderBot

A Telegram bot that makes sure university students never miss assignments, quizzes and deadlines.

**Status:** M3 (reminders without AI). `/start`, `/timezone`, `/help`, and
`/remind <when> | <what>`. A scheduler checks the database every 30 seconds and sends alerts
1 day, 3 hours and 30 minutes before each deadline, retrying if Telegram is unreachable.

Examples:
```
/remind 2026-11-21 17:00 | Data Structures assignment
/remind tomorrow 9:00 | Quiz on chapter 4
/remind 2026-11-25 | Lab report          (no time -> 8:00 AM)
/remind in 2h | Call my group leader     (one alert, exactly in 2 hours)
```

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
   It creates or updates the database by itself (`reminderbot.db` in this folder).
4. Open your bot in Telegram and send `/start`.

## Database
- Development uses SQLite (`DATABASE_URL=sqlite+aiosqlite:///./reminderbot.db`); production will use Postgres.
- Tables are defined in `src/reminderbot/db/models.py`; migrations live in `src/reminderbot/db/migrations/`.
- After changing `models.py`, create a migration and check it:
  ```powershell
  alembic revision --autogenerate -m "what changed"
  alembic upgrade head
  ```
  A test fails if the models and migrations don't match.
- To start over with an empty database, stop the bot and delete `reminderbot.db`.

## Tests and lint
```powershell
pytest -q
ruff check .
ruff format --check .
```

See `CLAUDE.md` for the architecture and the project rules.
