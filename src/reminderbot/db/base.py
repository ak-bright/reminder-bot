"""The ORM base class and a UTC-safe datetime column type."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, MetaData
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator

# Fixed names for indexes and constraints. Alembic needs predictable names to
# change or drop them later (especially on SQLite).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UTCDateTime(TypeDecorator):
    """A datetime column that only accepts and returns timezone-aware UTC values.

    SQLite has no timezone support: it would hand back "naive" datetimes, and
    comparing those with aware ones crashes. So we store naive UTC and re-attach
    UTC when reading. Passing a naive datetime in is a bug, so we refuse it.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime given; always use timezone-aware UTC")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC)


def utc_now() -> datetime:
    """Default for `created_at` columns. These are audit timestamps that no logic
    reads, so they don't need the injectable Clock."""
    return datetime.now(UTC)
