"""Dashboard — top-level stats."""
from __future__ import annotations

from django.shortcuts import render
from sqlalchemy import func, select

from openreversefeed.db.models import (
    Account,
    CorrectionQueue,
    IngestionRun,
    OutboxEvent,
    Scheme,
    SourceFile,
    Transaction,
)
from reference_app.ofr_bridge import get_session_factory


def home(request):
    Session = get_session_factory()
    with Session() as session:
        stats = {
            "accounts": session.execute(select(func.count()).select_from(Account)).scalar(),
            "schemes": session.execute(select(func.count()).select_from(Scheme)).scalar(),
            "source_files": session.execute(select(func.count()).select_from(SourceFile)).scalar(),
            "ingestion_runs": session.execute(
                select(func.count()).select_from(IngestionRun)
            ).scalar(),
            "transactions": session.execute(
                select(func.count()).select_from(Transaction)
            ).scalar(),
            "outbox_pending": session.execute(
                select(func.count()).select_from(OutboxEvent).where(OutboxEvent.status == "pending")
            ).scalar(),
            "outbox_published": session.execute(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.status == "published")
            ).scalar(),
            "corrections_pending": session.execute(
                select(func.count())
                .select_from(CorrectionQueue)
                .where(CorrectionQueue.status == "pending")
            ).scalar(),
        }

        per_registrar = session.execute(
            select(
                Transaction.registrar,
                Transaction.action,
                Transaction.action_tag,
                func.count().label("n"),
                func.sum(Transaction.units).label("total_units"),
            )
            .group_by(Transaction.registrar, Transaction.action, Transaction.action_tag)
            .order_by(Transaction.registrar, Transaction.action, Transaction.action_tag)
        ).all()

        recent_files = session.execute(
            select(SourceFile).order_by(SourceFile.id.desc()).limit(10)
        ).scalars().all()

    return render(
        request,
        "dashboard/home.html",
        {
            "stats": stats,
            "per_registrar": per_registrar,
            "recent_files": recent_files,
            "active": "overview",
        },
    )
