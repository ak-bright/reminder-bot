"""Logging setup (structlog).

Two safety rules (CLAUDE.md rule 7):
- never log secrets: values under "secret-looking" keys are replaced with "***";
- never log full user messages at INFO: we log `text_len` instead of `text`.
"""

import logging
import sys

import structlog

_SECRET_KEYS = {"token", "api_key", "password", "secret", "authorization"}


def _redact_secrets(_logger, _method, event_dict: dict) -> dict:
    for key in list(event_dict):
        if any(word in key.lower() for word in _SECRET_KEYS):
            event_dict[key] = "***"
    return event_dict


def setup_logging(level: str = "INFO", json: bool = False) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())

    # httpx (used by python-telegram-bot) logs every request URL at INFO, and Telegram
    # URLs contain the bot token. Keep it quiet.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpx2").setLevel(logging.WARNING)  # used by the anthropic SDK

    renderer = structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redact_secrets,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        logger_factory=structlog.PrintLoggerFactory(),
    )


def get_logger(name: str | None = None):
    return structlog.get_logger(name)
