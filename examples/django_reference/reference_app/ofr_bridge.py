"""Bridges Django views to the openreversefeed library.

Holds a module-level SQLAlchemy engine + session factory pointed at the same
Postgres as the library. Django never uses its own ORM for feed data — all
reads and writes go through the library's SQLAlchemy models.
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.conf import settings
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from openreversefeed.adapters.cams import CamsAdapter
from openreversefeed.adapters.kfintech import KFintechFormat1Adapter
from openreversefeed.core.cleaner import Cleaner
from openreversefeed.core.models import Registrar
from openreversefeed.db import models as ofr_models
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
from openreversefeed.db.session import make_engine

_engine = None
_session_factory = None


def get_session_factory() -> sessionmaker[Session]:
    global _engine, _session_factory
    if _session_factory is None:
        _engine = make_engine(settings.OFR_DATABASE_URL, schema="openreversefeed")
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _session_factory


def _adapter_for(registrar: str):
    if registrar == "cams":
        return CamsAdapter(), Registrar.CAMS
    if registrar == "kfintech":
        return KFintechFormat1Adapter(), Registrar.KFINTECH
    raise ValueError(f"unknown registrar: {registrar}")


def save_uploaded_file(uploaded_file, registrar: str, uploaded_by: str) -> dict[str, Any]:
    """Persist an uploaded Django file to disk and create a source_files row.

    Returns a dict with source_file_id and whether it was a duplicate.
    Does NOT process the file — that happens later in the worker (or on
    demand via process_source_file()).
    """
    target_dir = Path(settings.UPLOAD_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)

    raw_bytes = b""
    for chunk in uploaded_file.chunks():
        raw_bytes += chunk
    checksum = hashlib.sha256(raw_bytes).hexdigest()

    target_path = target_dir / f"{checksum[:12]}_{uploaded_file.name}"
    target_path.write_bytes(raw_bytes)

    Session = get_session_factory()
    with Session() as session:
        existing = session.execute(
            select(SourceFile).where(SourceFile.checksum == checksum)
        ).scalar_one_or_none()
        if existing is not None:
            return {
                "source_file_id": existing.id,
                "status": existing.status,
                "duplicate": True,
                "message": f"already exists (id={existing.id}, {existing.status})",
            }

        sf = SourceFile(
            filename=uploaded_file.name,
            storage_uri=f"file://{target_path.absolute()}",
            status="pending",
            registrar=registrar,
            checksum=checksum,
            uploaded_by=uploaded_by,
            meta={},
        )
        session.add(sf)
        session.commit()
        return {
            "source_file_id": sf.id,
            "status": "pending",
            "duplicate": False,
            "message": f"uploaded (id={sf.id})",
        }


def process_source_file(source_file_id: int) -> dict[str, Any]:
    """Run the full cleaner pipeline on one source_files row + persist transactions.

    This is intentionally synchronous so the Django demo can show immediate
    results without a separate worker. In production this runs in
    examples/django_reference/workers/file_worker.py.
    """
    Session = get_session_factory()
    with Session() as session:
        sf = session.get(SourceFile, source_file_id)
        if sf is None:
            return {"error": f"source_file {source_file_id} not found"}

        if sf.status == "completed":
            return {"source_file_id": sf.id, "status": "already_completed"}

        sf.status = "processing"
        session.commit()

        adapter, registrar = _adapter_for(sf.registrar)
        local_path = Path(sf.storage_uri.removeprefix("file://"))

        run = IngestionRun(
            source_file_id=sf.id,
            started_at=datetime.utcnow(),
            status="running",
            stats={},
        )
        session.add(run)
        session.commit()

        try:
            raw = adapter.parse(local_path)
            normalized = adapter.normalize(raw)

            # Coerce types (same coercions as tools/end_to_end_demo.py)
            import pandas as pd

            normalized["transaction_date"] = pd.to_datetime(
                normalized["transaction_date"]
            ).dt.date
            normalized["units"] = normalized["units"].astype(float)
            normalized["amount"] = normalized["amount"].astype(float)
            if "nav" in normalized.columns:
                normalized["nav"] = normalized["nav"].astype(float)

            cleaned = Cleaner().run(normalized, adapter)

            stats = {
                "rows_in": int(len(raw)),
                "rows_cleaned": int(len(cleaned)),
                "new_txns": 0,
                "skipped": 0,
                "duplicate": 0,
            }

            for _, row in cleaned.iterrows():
                pan = str(row.get("pan") or "").strip().upper()
                scheme_code = row.get("scheme_code")
                account = session.execute(
                    select(Account).where(Account.pan == pan)
                ).scalar_one_or_none()
                scheme = session.execute(
                    select(Scheme).where(Scheme.scheme_code == scheme_code)
                ).scalar_one_or_none()
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

                sp = session.begin_nested()
                try:
                    txn = Transaction(
                        account_id=account.id,
                        folio_id=folio.id,
                        scheme_id=scheme.id,
                        amc_id=scheme.amc_id,
                        source_file_id=sf.id,
                        ingestion_run_id=run.id,
                        registrar=registrar.value,
                        composite_key=row["composite_key"],
                        registrar_transaction_id=str(row["transaction_id"]),
                        registrar_transaction_number=str(
                            row.get("transaction_number") or ""
                        ),
                        parent_transaction_number=str(
                            row.get("parent_transaction_number") or ""
                        )
                        or None,
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
            sf.status = "completed"
            sf.row_count = stats["rows_in"]
            session.commit()
            return {"source_file_id": sf.id, "stats": stats, "ingestion_run_id": run.id}
        except Exception as e:  # noqa: BLE001 — catch-all only for demo path
            session.rollback()
            sf.status = "failed"
            sf.error = str(e)[:2000]
            run.status = "failed"
            run.ended_at = datetime.utcnow()
            run.error = str(e)[:2000]
            session.commit()
            return {"source_file_id": sf.id, "error": str(e)}
