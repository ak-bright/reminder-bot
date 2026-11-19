"""All configuration comes from environment variables (or a local .env file).

pydantic-settings reads each field from the env var with the same name in UPPER_CASE,
e.g. `telegram_bot_token` <- TELEGRAM_BOT_TOKEN.
"""

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from reminderbot.core.timezones import is_valid_timezone

DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./reminderbot.db"


class DatabaseSettings(BaseSettings):
    """Only the database URL. Used by the `alembic` command, which shouldn't need
    a Telegram token just to update the database."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = DEFAULT_DATABASE_URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Required. SecretStr hides the value if the settings object is ever printed or logged.
    telegram_bot_token: SecretStr

    # AI (used from M4). Model names live here, never in the logic.
    anthropic_api_key: SecretStr | None = None
    model_parser: str = "claude-haiku-5-5"
    model_assistant: str = "claude-sonnet-5-5"
    ai_daily_limit: int = 30
    ai_max_input_chars: int = 2000
    ai_max_output_tokens: int = 1024

    # Database. SQLite file in development; Postgres URL in production (M8).
    database_url: str = DEFAULT_DATABASE_URL

    # Behaviour
    default_timezone: str = "Africa/Accra"
    scheduler_interval_seconds: int = 30

    # Logging
    log_level: str = "INFO"
    log_json: bool = False

    @field_validator("default_timezone")
    @classmethod
    def _check_timezone(cls, value: str) -> str:
        if not is_valid_timezone(value):
            raise ValueError(f"unknown timezone: {value!r}")
        return value

    @field_validator("telegram_bot_token")
    @classmethod
    def _check_token_not_empty(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("TELEGRAM_BOT_TOKEN is empty")
        return value
