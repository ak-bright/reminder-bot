"""The Alembic migrations build exactly the tables described in db/models.py."""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from reminderbot.db.base import Base
from reminderbot.db.migrate import alembic_config, upgrade_to_latest

TABLES = {"users", "courses", "reminders", "alerts", "conversation_memory", "pending_actions"}


def sync_url(database_url: str) -> str:
    # For inspecting the result we use the plain (non-async) sqlite driver.
    return database_url.replace("+aiosqlite", "")


def test_upgrade_creates_all_tables(database_url):
    upgrade_to_latest(database_url)
    engine = create_engine(sync_url(database_url))
    assert set(inspect(engine).get_table_names()) >= TABLES
    engine.dispose()


def test_migrations_match_the_models(database_url):
    # If someone changes models.py but forgets a migration, this test fails.
    upgrade_to_latest(database_url)
    engine = create_engine(sync_url(database_url))
    with engine.connect() as conn:
        differences = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()
    assert differences == []


def test_upgrade_twice_is_safe_and_downgrade_works(database_url):
    upgrade_to_latest(database_url)
    upgrade_to_latest(database_url)  # the bot runs this at every start

    command.downgrade(alembic_config(database_url), "base")
    engine = create_engine(sync_url(database_url))
    assert not (TABLES & set(inspect(engine).get_table_names()))
    engine.dispose()
