"""Feed Files (uploads) views — list, new, detail, process."""
from __future__ import annotations

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from sqlalchemy import func, or_, select

from openreversefeed.db.models import (
    Account,
    Folio,
    IngestionRun,
    Scheme,
    SourceFile,
    Transaction,
)
from reference_app.ofr_bridge import (
    get_session_factory,
    process_source_file,
    save_uploaded_file,
)

from .forms import UploadForm


_STATUS_CHOICES = ("all", "pending", "processing", "completed", "failed")
_PROVIDER_CHOICES = ("all", "cams", "kfintech")


def file_list(request):
    q = (request.GET.get("q") or "").strip()
    status = request.GET.get("status") or "all"
    provider = request.GET.get("provider") or "all"
    if status not in _STATUS_CHOICES:
        status = "all"
    if provider not in _PROVIDER_CHOICES:
        provider = "all"

    Session = get_session_factory()
    with Session() as session:
        query = select(SourceFile).order_by(SourceFile.id.desc())
        if status != "all":
            query = query.where(SourceFile.status == status)
        if provider != "all":
            query = query.where(SourceFile.registrar == provider)
        if q:
            query = query.where(
                or_(
                    SourceFile.filename.ilike(f"%{q}%"),
                    SourceFile.uploaded_by.ilike(f"%{q}%"),
                )
            )
        files = session.execute(query).scalars().all()
        counts = dict(
            session.execute(
                select(Transaction.source_file_id, func.count())
                .group_by(Transaction.source_file_id)
            ).all()
        )
        total_files = session.execute(select(func.count()).select_from(SourceFile)).scalar()

    rows = []
    for f in files:
        rows.append(
            {
                "id": f.id,
                "filename": f.filename,
                "registrar": f.registrar,
                "status": f.status,
                "created_at": f.created_at,
                "row_count": f.row_count,
                "txn_count": counts.get(f.id, 0),
                "uploaded_by": f.uploaded_by,
            }
        )

    return render(
        request,
        "uploads/list.html",
        {
            "rows": rows,
            "q": q,
            "status": status,
            "provider": provider,
            "status_choices": _STATUS_CHOICES,
            "provider_choices": _PROVIDER_CHOICES,
            "total_files": total_files,
            "shown_count": len(rows),
            "active": "files",
        },
    )


def upload_view(request):
    if request.method == "POST":
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            result = save_uploaded_file(
                uploaded_file=form.cleaned_data["file"],
                registrar=form.cleaned_data["registrar"],
                uploaded_by=form.cleaned_data["uploaded_by"],
            )
            if result["duplicate"]:
                messages.warning(request, f"Duplicate file — {result['message']}")
            else:
                messages.success(request, result["message"])
            return redirect(reverse("uploads:detail", args=[result["source_file_id"]]))
    else:
        form = UploadForm()
    return render(request, "uploads/upload.html", {"form": form, "active": "ingest"})


def file_detail(request, source_file_id: int):
    Session = get_session_factory()
    with Session() as session:
        sf = session.get(SourceFile, source_file_id)
        if sf is None:
            raise Http404
        runs = (
            session.execute(
                select(IngestionRun)
                .where(IngestionRun.source_file_id == source_file_id)
                .order_by(IngestionRun.id.desc())
            )
            .scalars()
            .all()
        )
        txn_rows = (
            session.execute(
                select(
                    Transaction,
                    Account.name.label("account_name"),
                    Account.pan.label("account_pan"),
                    Scheme.name.label("scheme_name"),
                    Scheme.scheme_code.label("scheme_code"),
                    Folio.folio_number.label("folio_number"),
                )
                .join(Account, Account.id == Transaction.account_id)
                .join(Scheme, Scheme.id == Transaction.scheme_id)
                .join(Folio, Folio.id == Transaction.folio_id)
                .where(Transaction.source_file_id == source_file_id)
                .order_by(Transaction.transaction_date, Transaction.id)
                .limit(200)
            )
            .all()
        )

    # Enrich each row with avatar color class + initials from PAN
    txns = []
    for r in txn_rows:
        pan = r.account_pan or "XXXXX"
        bucket = (sum(ord(c) for c in pan[-4:]) % 6) + 1
        initials = pan[:2].upper() if pan else "??"
        txns.append(
            {
                "t": r.Transaction,
                "account_name": r.account_name,
                "account_pan": r.account_pan,
                "scheme_code": r.scheme_code,
                "scheme_name": r.scheme_name,
                "folio_number": r.folio_number,
                "avatar_class": f"av-{bucket}",
                "initials": initials,
            }
        )

    return render(
        request,
        "uploads/detail.html",
        {"sf": sf, "runs": runs, "txns": txns, "active": "files"},
    )


def process_view(request, source_file_id: int):
    if request.method != "POST":
        return redirect(reverse("uploads:detail", args=[source_file_id]))
    result = process_source_file(source_file_id)
    if "error" in result:
        messages.error(request, f"Processing failed: {result['error']}")
    else:
        stats = result.get("stats", {})
        messages.success(
            request,
            f"Processed — new={stats.get('new_txns', 0)} "
            f"duplicates={stats.get('duplicate', 0)} skipped={stats.get('skipped', 0)}",
        )
    return redirect(reverse("uploads:detail", args=[source_file_id]))
