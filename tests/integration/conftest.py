"""Integration-test fixtures — require Docker + testcontainers."""
from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker
from testcontainers.postgres import PostgresContainer

from openreversefeed.db.session import make_engine


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
def engine(postgres_container: PostgresContainer) -> Engine:
    url = postgres_container.get_connection_url().replace(
        "postgresql+psycopg2", "postgresql+psycopg"
    )
    eng = make_engine(url, schema="openreversefeed")
    with eng.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS openreversefeed"))
    os.environ["OFR_DATABASE_URL"] = url
    return eng


@pytest.fixture()
def session(engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory() as s:
        yield s
        s.rollback()
