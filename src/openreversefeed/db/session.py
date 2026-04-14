"""SQLAlchemy engine, session factory, and declarative Base."""
from __future__ import annotations

from sqlalchemy import Engine, MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from openreversefeed.settings import Settings

DEFAULT_SCHEMA = "openreversefeed"


class Base(DeclarativeBase):
    metadata = MetaData(schema=DEFAULT_SCHEMA)


def make_engine(url: str, *, schema: str | None = DEFAULT_SCHEMA, echo: bool = False) -> Engine:
    """Create a SQLAlchemy engine pointed at the given URL.

    Passing schema=None (e.g. for SQLite tests) rebinds metadata to the
    default (public) schema so the models still work without Postgres schemas.
    """
    if schema != DEFAULT_SCHEMA:
        Base.metadata.schema = schema
    return create_engine(url, echo=echo, future=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def engine_from_settings(settings: Settings) -> Engine:
    return make_engine(settings.database_url, schema=settings.db_schema)
