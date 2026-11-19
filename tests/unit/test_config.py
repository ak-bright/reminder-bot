import pytest
from pydantic import ValidationError

from reminderbot.config import Settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    # Make sure a developer's real environment doesn't leak into these tests.
    for var in ("TELEGRAM_BOT_TOKEN", "DEFAULT_TIMEZONE", "MODEL_PARSER", "MODEL_ASSISTANT"):
        monkeypatch.delenv(var, raising=False)


def test_missing_token_is_an_error():
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "telegram_bot_token" in str(exc.value)


def test_empty_token_is_an_error(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "   ")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_defaults(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    settings = Settings(_env_file=None)
    assert settings.default_timezone == "Africa/Accra"
    assert settings.model_parser == "claude-haiku-5-5"
    assert settings.model_assistant == "claude-sonnet-5-5"
    assert settings.ai_daily_limit == 30
    assert settings.scheduler_interval_seconds == 30


def test_token_is_hidden_when_printed(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:super-secret")
    settings = Settings(_env_file=None)
    assert "super-secret" not in repr(settings)
    assert settings.telegram_bot_token.get_secret_value() == "123:super-secret"


def test_models_come_from_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("MODEL_PARSER", "some-other-model")
    assert Settings(_env_file=None).model_parser == "some-other-model"


def test_invalid_default_timezone(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("DEFAULT_TIMEZONE", "Mars/Olympus")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
