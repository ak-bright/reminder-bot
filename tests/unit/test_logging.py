import logging

from reminderbot.logging_setup import _redact_secrets, setup_logging


def test_secret_keys_are_redacted():
    event = {"event": "x", "telegram_bot_token": "123:abc", "api_key": "sk", "user": "42"}
    out = _redact_secrets(None, "info", event)
    assert out["telegram_bot_token"] == "***"
    assert out["api_key"] == "***"
    assert out["user"] == "42"


def test_httpx_is_quiet_so_token_urls_are_not_logged():
    setup_logging("INFO")
    assert logging.getLogger("httpx").level == logging.WARNING
