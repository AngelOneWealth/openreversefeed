"""Verify alembic creates and drops all tables cleanly against a real Postgres."""
from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text


@pytest.mark.integration
def test_upgrade_head_creates_all_tables(engine: Engine) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "src/openreversefeed/db/alembic")
    cfg.set_main_option(
        "sqlalchemy.url", engine.url.render_as_string(hide_password=False)
    )

    command.upgrade(cfg, "head")

    insp = inspect(engine)
    tables = set(insp.get_table_names(schema="openreversefeed"))
    expected = {
        "accounts",
        "amcs",
        "schemes",
        "folios",
        "source_files",
        "ingestion_runs",
        "transactions",
        "positions",
        "processing_records",
        "correction_queue",
        "outbox_events",
    }
    assert expected.issubset(tables), f"missing: {expected - tables}"

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = 'openreversefeed' "
                "AND indexname = 'uq_source_files_checksum_partial'"
            )
        ).fetchall()
    assert len(rows) == 1
    assert "WHERE" in rows[0][0] and "checksum IS NOT NULL" in rows[0][0]

    command.downgrade(cfg, "base")
    insp = inspect(engine)
    tables = set(insp.get_table_names(schema="openreversefeed"))
    assert expected.isdisjoint(tables)
