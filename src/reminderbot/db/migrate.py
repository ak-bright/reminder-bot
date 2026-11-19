"""Run Alembic migrations from Python (the bot does this at startup).

Same effect as typing `alembic upgrade head`, but works from any folder because
it finds the migrations next to this file.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def alembic_config(database_url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    # Config values treat "%" as special, so a password like "p%ss" must be escaped.
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    config.attributes["configure_logger"] = False
    return config


def upgrade_to_latest(database_url: str) -> None:
    """Bring the database schema up to date. Safe to run every time.

    Must be called when no asyncio event loop is running (env.py uses asyncio.run).
    """
    command.upgrade(alembic_config(database_url), "head")
