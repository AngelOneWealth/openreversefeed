"""Correction queue (Exceptions) list view."""
from __future__ import annotations

from django.shortcuts import render
from sqlalchemy import func, select

from openreversefeed.db.models import CorrectionQueue
from reference_app.ofr_bridge import get_session_factory


def queue_list(request):
    status_filter = request.GET.get("status", "all")
    valid = ("all", "pending", "resolved", "skipped")
    if status_filter not in valid:
        status_filter = "all"

    Session = get_session_factory()
    with Session() as session:
        query = select(CorrectionQueue).order_by(CorrectionQueue.id.desc())
        if status_filter != "all":
            query = query.where(CorrectionQueue.status == status_filter)
        items = session.execute(query).scalars().all()
        total = session.execute(select(func.count()).select_from(CorrectionQueue)).scalar()

    return render(
        request,
        "corrections/list.html",
        {
            "items": items,
            "status_filter": status_filter,
            "choices": valid,
            "total": total,
            "active": "exceptions",
        },
    )
