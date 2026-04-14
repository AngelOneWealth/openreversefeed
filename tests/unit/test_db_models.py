"""Structural tests for db.models. Behavioral tests live in the integration suite."""
from sqlalchemy.schema import CheckConstraint, UniqueConstraint

from openreversefeed.db import models  # noqa: F401 — ensures metadata is populated
from openreversefeed.db.session import Base


def _table(name: str):
    return Base.metadata.tables[f"openreversefeed.{name}"]


def test_all_expected_tables_registered():
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
    actual = {t.name for t in Base.metadata.tables.values()}
    assert expected.issubset(actual), f"missing tables: {expected - actual}"


def test_transactions_unique_constraint_registrar_amc_composite_key():
    tbl = _table("transactions")
    uniques = [c for c in tbl.constraints if isinstance(c, UniqueConstraint)]
    cols_sets = [{c.name for c in u.columns} for u in uniques]
    assert {"registrar", "amc_id", "composite_key"} in cols_sets


def test_transactions_has_required_columns():
    tbl = _table("transactions")
    required = {
        "id",
        "account_id",
        "folio_id",
        "scheme_id",
        "amc_id",
        "source_file_id",
        "ingestion_run_id",
        "registrar",
        "composite_key",
        "registrar_transaction_id",
        "registrar_transaction_number",
        "parent_transaction_number",
        "parent_transaction_id",
        "transaction_date",
        "nav",
        "units",
        "amount",
        "action",
        "action_tag",
        "status",
        "broker_code",
        "meta",
        "created_at",
        "updated_at",
    }
    actual = {c.name for c in tbl.columns}
    assert required.issubset(actual), f"missing columns: {required - actual}"


def test_transactions_indexes_declared():
    tbl = _table("transactions")
    index_col_sets = [tuple(c.name for c in idx.columns) for idx in tbl.indexes]
    assert ("registrar", "amc_id", "registrar_transaction_id") in index_col_sets
    assert ("registrar", "amc_id", "registrar_transaction_number") in index_col_sets
    assert ("account_id", "scheme_id") in index_col_sets
    assert ("parent_transaction_id",) in index_col_sets


def test_source_files_checksum_partial_unique_index_exists():
    tbl = _table("source_files")
    partial = [
        idx
        for idx in tbl.indexes
        if idx.unique and "checksum" in {c.name for c in idx.columns}
    ]
    assert len(partial) == 1
    assert partial[0].dialect_options["postgresql"]["where"] is not None


def test_positions_unique_constraint_account_folio_scheme():
    tbl = _table("positions")
    uniques = [c for c in tbl.constraints if isinstance(c, UniqueConstraint)]
    cols_sets = [{c.name for c in u.columns} for u in uniques]
    assert {"account_id", "folio_id", "scheme_id"} in cols_sets


def test_folios_unique_constraint_account_folio_amc():
    tbl = _table("folios")
    uniques = [c for c in tbl.constraints if isinstance(c, UniqueConstraint)]
    cols_sets = [{c.name for c in u.columns} for u in uniques]
    assert {"account_id", "folio_number", "amc_id"} in cols_sets


def test_outbox_events_status_check_constraint():
    tbl = _table("outbox_events")
    checks = [c for c in tbl.constraints if isinstance(c, CheckConstraint)]
    status_check = next(
        (c for c in checks if c.name == "ck_outbox_events_status"), None
    )
    assert status_check is not None
    text = str(status_check.sqltext).lower()
    assert "pending" in text and "published" in text and "dead" in text


def test_accounts_ownership_check_constraint():
    tbl = _table("accounts")
    checks = [c for c in tbl.constraints if isinstance(c, CheckConstraint)]
    assert any(c.name == "ck_accounts_ownership_type" for c in checks)


def test_processing_records_status_check():
    tbl = _table("processing_records")
    checks = [c for c in tbl.constraints if isinstance(c, CheckConstraint)]
    assert any(c.name == "ck_processing_records_status" for c in checks)
