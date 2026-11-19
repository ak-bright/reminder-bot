"""Alembic environment: how Alembic connects to the database.

Used both by the `alembic` command line tool and by db/migrate.py, which the bot
calls at startup.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from reminderbot.config import DatabaseSettings
from reminderbot.db import models  # noqa: F401 - registers all tables on Base.metadata
from reminderbot.db.base import Base, UTCDateTime

config = context.config

# The command line tool sets up its own logging from alembic.ini. When the bot
# runs migrations, it passes configure_logger=False to keep its structlog setup.
if config.config_file_name and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)


def database_url() -> str:
    # A URL passed in by the caller (e.g. tests) wins; otherwise read DATABASE_URL.
    return config.get_main_option("sqlalchemy.url") or DatabaseSettings().database_url


def render_item(type_, obj, autogen_context):
    # Write our UTCDateTime as a plain sa.DateTime() in migration files, so
    # migrations don't depend on app code that may change later.
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime()"
    return False  # use Alembic's default for everything else


def run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        render_item=render_item,
        render_as_batch=True,  # lets future migrations ALTER tables on SQLite
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async() -> None:
    engine = create_async_engine(database_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(run_migrations)
    await engine.dispose()


def run_offline() -> None:
    """`alembic upgrade head --sql`: print the SQL instead of running it."""
    context.configure(
        url=database_url(),
        target_metadata=Base.metadata,
        render_item=render_item,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_offline()
else:
    asyncio.run(run_async())
