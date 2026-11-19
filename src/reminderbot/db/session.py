"""Create the async database engine and the session factory."""

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine


def create_engine(database_url: str) -> AsyncEngine:
    engine = create_async_engine(database_url)
    if engine.dialect.name == "sqlite":
        _enable_sqlite_foreign_keys(engine)
    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker:
    # expire_on_commit=False: objects stay readable after commit, so we can still
    # use a row we just saved without another query.
    return async_sessionmaker(engine, expire_on_commit=False)


def _enable_sqlite_foreign_keys(engine: AsyncEngine) -> None:
    # SQLite ignores foreign keys (and ON DELETE CASCADE) unless each connection
    # switches them on. Postgres always enforces them.
    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_connection, _record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
