"""Alembic environment — online mode only."""
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from openreversefeed.db import models  # noqa: F401 — populates metadata
from openreversefeed.db.session import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

env_url = os.environ.get("OFR_DATABASE_URL")
if env_url:
    config.set_main_option("sqlalchemy.url", env_url)

target_metadata = Base.metadata
target_schema = os.environ.get("OFR_DB_SCHEMA", "openreversefeed")
target_metadata.schema = target_schema


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{target_schema}"'))
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table_schema=target_schema,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise NotImplementedError("Offline migrations are not supported")
else:
    run_migrations_online()
