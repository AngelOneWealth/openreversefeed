"""End-to-end demo: seed accounts/amcs/schemes, process CAMS + KFintech sample files
through the cleaner pipeline, insert cleaned transactions into Postgres, and print
a verification query.

This is a standalone script for local manual testing. It will be superseded by
ReverseFeedService.process_file() once chunk 5 of the plan lands.
"""
from __future__ import annotations

import os
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from openreversefeed.adapters.cams import CamsAdapter
from openreversefeed.adapters.kfintech import KFintechFormat1Adapter
from openreversefeed.core.cleaner import Cleaner
from openreversefeed.core.models import Registrar
from openreversefeed.db import models  # noqa: F401 - populates metadata
from openreversefeed.db.models import (
    Account,
    Amc,
    Folio,
    IngestionRun,
    OutboxEvent,
    Scheme,
    SourceFile,
    Transaction,
)
from openreversefeed.db.session import Base, make_engine

DATABASE_URL = os.environ.get(
    "OFR_DATABASE_URL", "postgresql+psycopg://ofr:ofr@localhost:5438/ofr"
)

_FAKE_SCHEMES = [
    ("SYNLRGCAP001", "ALPHA01",   "Alpha Largecap Growth Fund - Direct"),
    ("SYNTOP100002", "BETA02",    "Beta Top 100 Growth Fund - Direct"),
    ("SYNSMLCAP003", "GAMMA03",   "Gamma Smallcap Growth Fund - Direct"),
    ("SYNMIDCAP004", "DELTA04",   "Delta Midcap Growth Fund - Direct"),
    ("SYNFLEXI005",  "EPSILON5",  "Epsilon Flexicap Growth Fund - Direct"),
]

_FAKE_ACCOUNTS = [
    ("Synthetic Investor 0", "AAAPL0001A", "individual"),
    ("Synthetic Investor 1", "AAAPL0002B", "joint"),
    ("Synthetic Investor 2", "AAAPL0003C", "individual"),
    ("Synthetic Investor 3", "AAAPL0003D", "joint"),
    ("Synthetic Investor 4", "AAAPL0004E", "individual"),
]


def seed_reference_data(session) -> dict:
    """Create AMCs, schemes, accounts. Returns lookup dicts."""
    print("Seeding reference data...")

    # AMCs
    amc_map = {}
    for _sc, code, _name in _FAKE_SCHEMES:
        amc = Amc(code=code, name=f"{code} AMC")
        session.add(amc)
        session.flush()
        amc_map[code] = amc

    # Schemes
    scheme_map = {}
    for sc, code, name in _FAKE_SCHEMES:
        scheme = Scheme(
            scheme_code=sc,
            amc_id=amc_map[code].id,
            name=name,
            plan_type="growth",
            option="direct",
        )
        session.add(scheme)
        session.flush()
        scheme_map[sc] = scheme

    # Accounts
    account_map = {}
    for name, pan, ot in _FAKE_ACCOUNTS:
        acc = Account(id=uuid.uuid4(), name=name, pan=pan, ownership_type=ot)
        session.add(acc)
        session.flush()
        account_map[pan] = acc

    session.commit()
    print(f"  {len(amc_map)} AMCs, {len(scheme_map)} schemes, {len(account_map)} accounts")
    return {"amcs": amc_map, "schemes": scheme_map, "accounts": account_map}


def process_file(session, file_path: Path, adapter, ref_data: dict, registrar: Registrar) -> dict:
    """Parse, clean, and insert transactions from one file. Returns stats."""
    print(f"\nProcessing {file_path.name} ({registrar.value})...")

    # 1. Create source_files + ingestion_runs rows.
    # If the checksum already exists in the table, short-circuit with a
    # `skipped_duplicate_file` stats result — this is the spec's file-level
    # idempotency guarantee (§4.5 partial unique index on checksum).
    import hashlib

    checksum = hashlib.sha256(file_path.read_bytes()).hexdigest()
    existing = session.execute(
        select(SourceFile).where(SourceFile.checksum == checksum)
    ).scalar_one_or_none()
    if existing is not None:
        print(
            f"  skipped — file already processed as source_file id={existing.id} "
            f"({existing.status}) on {existing.created_at:%Y-%m-%d %H:%M:%S}"
        )
        return {"new_txns": 0, "skipped": 0, "duplicate": 0, "skipped_duplicate_file": True}

    source_file = SourceFile(
        filename=file_path.name,
        storage_uri=f"file://{file_path.absolute()}",
        status="processing",
        registrar=registrar.value,
        checksum=checksum,
        uploaded_by="demo-script",
    )
    session.add(source_file)
    session.flush()

    run = IngestionRun(
        source_file_id=source_file.id,
        started_at=datetime.utcnow(),
        status="running",
        stats={},
    )
    session.add(run)
    session.flush()

    # 2. Parse + normalize
    raw = adapter.parse(file_path)
    normalized = adapter.normalize(raw)
    normalized["transaction_date"] = pd_to_date(normalized["transaction_date"])
    normalized["units"] = normalized["units"].astype(float)
    normalized["amount"] = normalized["amount"].astype(float)
    if "nav" in normalized.columns:
        normalized["nav"] = normalized["nav"].astype(float)

    print(f"  parsed {len(normalized)} rows")

    # 3. Run cleaner pipeline
    cleaned = Cleaner().run(normalized, adapter)
    print(f"  cleaned → {len(cleaned)} rows")

    # 4. Insert transactions
    stats = {"new_txns": 0, "skipped": 0, "duplicate": 0}
    for _, row in cleaned.iterrows():
        pan = str(row.get("pan") or "").strip().upper()
        account = ref_data["accounts"].get(pan)
        scheme = ref_data["schemes"].get(row["scheme_code"])
        if account is None or scheme is None:
            stats["skipped"] += 1
            continue

        folio_number = str(row["folio_number"])
        folio = session.execute(
            select(Folio).where(
                Folio.account_id == account.id,
                Folio.folio_number == folio_number,
                Folio.amc_id == scheme.amc_id,
            )
        ).scalar_one_or_none()
        if folio is None:
            folio = Folio(
                account_id=account.id,
                folio_number=folio_number,
                amc_id=scheme.amc_id,
                source="registrar",
            )
            session.add(folio)
            session.flush()

        # Savepoint per row so a duplicate insert does not poison the outer txn
        sp = session.begin_nested()
        try:
            txn = Transaction(
                account_id=account.id,
                folio_id=folio.id,
                scheme_id=scheme.id,
                amc_id=scheme.amc_id,
                source_file_id=source_file.id,
                ingestion_run_id=run.id,
                registrar=registrar.value,
                composite_key=row["composite_key"],
                registrar_transaction_id=str(row["transaction_id"]),
                registrar_transaction_number=str(row.get("transaction_number") or ""),
                parent_transaction_number=str(row.get("parent_transaction_number") or "") or None,
                transaction_date=row["transaction_date"],
                nav=Decimal(str(row.get("nav") or "0")),
                units=Decimal(str(row["units"])),
                amount=Decimal(str(row["amount"])),
                action=(
                    row["action"].value
                    if hasattr(row["action"], "value")
                    else str(row["action"])
                ),
                action_tag=str(row["action_tag"]),
                status="successful",
                broker_code=str(row.get("broker_code") or ""),
                meta={},
            )
            session.add(txn)
            session.flush()
            sp.commit()
        except IntegrityError:
            sp.rollback()
            stats["duplicate"] += 1
            continue

        stats["new_txns"] += 1

        # Emit outbox event in the same transaction
        session.add(
            OutboxEvent(
                event_type="transaction.created",
                aggregate_id=str(txn.id),
                payload={
                    "transaction_id": txn.id,
                    "composite_key": txn.composite_key,
                    "account_id": str(account.id),
                    "scheme_code": scheme.scheme_code,
                    "units": float(txn.units),
                    "amount": float(txn.amount),
                    "action": txn.action,
                },
                status="pending",
                retry_count=0,
            )
        )

    run.status = "succeeded"
    run.ended_at = datetime.utcnow()
    run.stats = stats
    source_file.status = "completed"
    session.commit()
    print(
        f"  inserted {stats['new_txns']} transactions, "
        f"duplicates rejected={stats['duplicate']}, skipped={stats['skipped']}"
    )
    return stats


def pd_to_date(col):
    """Coerce a pandas Series of date-like strings into real date objects."""
    import pandas as pd

    return pd.to_datetime(col).dt.date


def verify(session) -> None:
    print("\n==== Verification queries ====")

    count = session.execute(text("SELECT COUNT(*) FROM openreversefeed.transactions")).scalar()
    print(f"transactions: {count}")

    count = session.execute(text("SELECT COUNT(*) FROM openreversefeed.outbox_events")).scalar()
    print(f"outbox_events (pending): {count}")

    rows = session.execute(
        text(
            """
            SELECT registrar, action, action_tag, COUNT(*) AS n, SUM(units) AS total_units
            FROM openreversefeed.transactions
            GROUP BY 1, 2, 3
            ORDER BY 1, 2, 3
            """
        )
    ).fetchall()
    print("\nTransactions by registrar / action / tag:")
    for r in rows:
        print(f"  {r.registrar:10} {r.action:10} {r.action_tag:20} n={r.n}  units={float(r.total_units):+.2f}")

    rows = session.execute(
        text(
            """
            SELECT a.name, a.pan, COUNT(t.id) AS txn_count, SUM(t.amount) AS total_amount
            FROM openreversefeed.accounts a
            LEFT JOIN openreversefeed.transactions t ON t.account_id = a.id
            GROUP BY a.id, a.name, a.pan
            ORDER BY total_amount DESC NULLS LAST
            """
        )
    ).fetchall()
    print("\nPer-account summary:")
    for r in rows:
        amt = float(r.total_amount or 0)
        print(f"  {r.name:25} {r.pan:12} txns={r.txn_count:3d}  total=₹{amt:>14,.2f}")

    rows = session.execute(
        text(
            """
            SELECT s.name, s.scheme_code, COUNT(t.id) AS txn_count
            FROM openreversefeed.schemes s
            LEFT JOIN openreversefeed.transactions t ON t.scheme_id = s.id
            GROUP BY s.id, s.name, s.scheme_code
            HAVING COUNT(t.id) > 0
            ORDER BY txn_count DESC
            """
        )
    ).fetchall()
    print("\nTransactions per scheme:")
    for r in rows:
        print(f"  {r.name:45} {r.scheme_code:15} n={r.txn_count}")


def main() -> None:
    print(f"DATABASE_URL = {DATABASE_URL}")

    engine = make_engine(DATABASE_URL, schema="openreversefeed")
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    # Wipe and re-seed for clean demo runs
    print("Wiping existing data...")
    with engine.begin() as conn:
        for t in (
            "outbox_events",
            "processing_records",
            "correction_queue",
            "transactions",
            "positions",
            "ingestion_runs",
            "source_files",
            "folios",
            "schemes",
            "amcs",
            "accounts",
        ):
            conn.execute(text(f"TRUNCATE TABLE openreversefeed.{t} RESTART IDENTITY CASCADE"))

    with SessionLocal() as session:
        ref_data = seed_reference_data(session)

    with SessionLocal() as session:
        cams_path = Path("tests/fixtures/generated/cams_sample.csv")
        kf_csv_path = Path("tests/fixtures/generated/kfintech_sample.csv")
        kf_dbf_path = Path("tests/fixtures/generated/kfintech_sample.dbf")

        print("\n=== Pass 1: process 3 distinct files ===")
        process_file(session, cams_path, CamsAdapter(), ref_data, Registrar.CAMS)
        process_file(session, kf_csv_path, KFintechFormat1Adapter(), ref_data, Registrar.KFINTECH)
        process_file(session, kf_dbf_path, KFintechFormat1Adapter(), ref_data, Registrar.KFINTECH)

        print("\n=== Pass 2: re-upload CAMS file (should be fully de-duped) ===")
        process_file(session, cams_path, CamsAdapter(), ref_data, Registrar.CAMS)

        verify(session)


if __name__ == "__main__":
    main()
