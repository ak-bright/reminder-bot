# ReminderBot: rules for working on this repo

ReminderBot is a Telegram bot (WhatsApp later) that makes sure university students in Ghana
never miss assignments, quizzes or deadlines. The user is a student and wants code they can
read and understand. Keep things simple and use short comments for non-obvious logic. Clear beats clever.

## How we work
- Build one milestone at a time (M1–M8, see "Milestones" below). After each one, run
  `ruff check .`, `ruff format --check .` and `pytest -q`, summarise in 5 lines or fewer,
  suggest a commit message, then **stop and wait for "next"**.
- Never commit unless asked.
- If two requirements conflict, say so. Don't pick one quietly.

## Commands
```
python -m venv .venv && .venv\Scripts\activate    # Windows (source .venv/bin/activate on Linux/Mac)
pip install -e ".[dev]"
python -m reminderbot          # run the bot (polling mode, needs .env); runs migrations first
alembic upgrade head           # apply migrations by hand
alembic revision --autogenerate -m "..."   # new migration after changing db/models.py
pytest -q                      # tests
ruff check . && ruff format --check .
```

## Stack
Python 3.12+ (async everywhere) · python-telegram-bot v22 · SQLAlchemy 2.x + Alembic (SQLite in dev, Postgres in prod)
· Anthropic Python SDK · pydantic-settings · structlog · pytest + pytest-asyncio · ruff · Docker.
dateparser/dateutil are used only to validate or back up the AI parser.

## Architecture (strict)
```
src/reminderbot/
  core/       domain logic. NEVER imports channels/ or telegram
  ai/         parser (Haiku), assistant (Sonnet), vision. NEVER imports channels/
  channels/   base.py = Channel interface + IncomingEvent; router.py = channel-agnostic bot logic;
              telegram/ = thin adapter (Update -> IncomingEvent, Channel -> Bot API)
  db/         ORM models, session, repositories, Alembic migrations
  scheduler/  30 s polling loop that sends due alerts through a Channel
  config.py, logging_setup.py, strings.py, clock.py, main.py
```
1. Dependencies point inward: channels -> core. `core/` and `ai/` never import `channels/` (a test enforces this).
2. A user's identity is `(channel, channel_user_id)`, which is UNIQUE.
3. Scheduler: every 30 s it queries alerts with `send_at_utc <= now AND status = pending`. It must be idempotent,
   survive restarts and retry failed sends with backoff. **No in-memory timers.**
   Each alert is claimed with a conditional UPDATE (`pending -> sending`) before sending. On failure it goes back to
   `pending` with `next_attempt_at` (backoff 1m, 5m, 15m, 1h) and becomes `failed` after 5 attempts. Alerts stuck in
   `sending` for more than 5 min are retried. **Decision: a rare duplicate is acceptable, a missed reminder is not.**
4. Alerts: a `deadline` reminder gets offsets of 1 day, 3 h and 30 min before. Offsets already in the past are skipped. If the
   deadline is under 30 min away, send one alert at max(now, deadline − 5 min).
   An `at_time` reminder ("remind me in 2 hours to…") gets one alert at that exact time.
5. Never guess silently. An unclear date or low confidence → ask ONE short clarifying question with buttons.
   A clear date with no time → default to 8:00 AM local and say so in the confirmation.
6. Always confirm in friendly words ("Got it. … due Fri 21 Nov, 5:00 PM. I'll remind you …") with [Edit] [Delete].
7. Secrets come only from env vars (`.env.example` lists them). Never log tokens or full message text at INFO.
   The `httpx` logger is kept at WARNING because it would log the bot token inside Telegram URLs.
8. User text is untrusted. Prompts treat it as data (wrapped in `<user_message>`), and model output is validated
   against a pydantic schema before use.
9. Cost control: a per-user daily AI assistant limit (default 30), max input length, max output tokens, the cheap model
   for parsing, and token usage logged on every call.
10. Every user-facing string lives in `strings.py`, accessed through `t(key, lang, **kwargs)`.

## Time
- Store ALL datetimes in UTC (timezone-aware). Convert to the user's timezone only for display or parsing.
- Default timezone is `Africa/Accra` (UTC+0, no DST). Each user can change theirs with /timezone.
- Code that needs "now" takes a `Clock` (`clock.py`). Tests use `FakeClock` and never sleep for real.

## Claude API
- Model names come from env vars only: `MODEL_PARSER` (claude-haiku-5-5) and `MODEL_ASSISTANT` (claude-sonnet-5-5).
- Parsing and vision use **structured outputs** (`output_config.format` via `client.messages.parse()` with
  pydantic models). Do not use forced `tool_choice`, because Sonnet 5.5 rejects it. Never regex-parse model text.
- Parser runs at `effort: "low"`. Don't send `temperature` (it is rejected). Log `usage` on every call.

## Product decisions (from planning)
- Private chats only. Content from class groups arrives as forwarded messages.
- Always-on hosting is required, because the scheduler loop must keep running.
- Telegram `callback_data` has a 64-byte limit, so buttons carry short ids. Larger state goes in `pending_actions` (from M2).

## Testing
- Scheduler tests use an injectable clock, with no real sleeping.
- Timezone tests include a non-UTC user (e.g. America/New_York, which has DST).
- Parser tests mock the AI (deterministic). Live tests live in `tests/live/` and are skipped unless `RUN_LIVE_AI_TESTS=1`.
- There is a test that a restart mid-day neither loses nor double-sends alerts.

## Milestones
M1 skeleton · M2 database · M3 /remind + scheduler · M4 natural-language parser · M5 buttons & list commands ·
M6 AI assistant · M7 student features (vision, digest, recurrence, courses, forwards, .ics) · M8 hardening/deploy.
