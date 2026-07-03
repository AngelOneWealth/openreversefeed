"""Deterministic composite key builders. See spec §5 step 5."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from openreversefeed.core.models import Registrar

_JS_DATE_RE = re.compile(r"[A-Z][a-z]{2}\s+([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d{4})")
_MONTH_ABBR = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}
_SLASH_AMPM_RE = re.compile(
    r"^(\d{1,2})/(\d{1,2})/(\d{4})\s+\d{1,2}:\d{2}:\d{2}\s+[AP]M$",
    re.IGNORECASE,
)
_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_SLASH_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_DASH_DMY_RE = re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})$")
_ALREADY_YYYYMMDD_RE = re.compile(r"^\d{8}$")


def _date_str(value: Any) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%Y%m%d")

    s = str(value).strip()

    if _ALREADY_YYYYMMDD_RE.match(s):
        return s

    # ISO: YYYY-MM-DD
    m = _ISO_RE.match(s)
    if m:
        return f"{m.group(1)}{m.group(2)}{m.group(3)}"

    # US-style with AM/PM timestamp: M/D/YYYY HH:MM:SS AM
    m = _SLASH_AMPM_RE.match(s)
    if m:
        month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{year:04d}{month:02d}{day:02d}"

    # Slash without timestamp: first > 12 means DD/MM, else DD/MM (Indian default)
    m = _SLASH_RE.match(s)
    if m:
        a, b, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if a > 12:
            day, month = a, b
        else:
            day, month = a, b
        return f"{year:04d}{month:02d}{day:02d}"

    # Dash DD-MM-YYYY
    m = _DASH_DMY_RE.match(s)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{year:04d}{month:02d}{day:02d}"

    # JavaScript Date.toString(): "Fri Aug 28 2026 ..."
    m = _JS_DATE_RE.match(s)
    if m:
        month_abbr, day_s, year_s = m.group(1), m.group(2), m.group(3)
        month = _MONTH_ABBR.get(month_abbr, 0)
        if month:
            return f"{int(year_s):04d}{month:02d}{int(day_s):02d}"

    return s


def build_cams_key(row: dict[str, Any]) -> str:
    return (
        f"{row['original_trans_number']}_{row['transaction_type']}_"
        f"{row['transaction_number']}_{_date_str(row['transaction_date'])}"
    )


def build_kfintech_key(row: dict[str, Any]) -> str:
    parent = row.get("parent_transaction_number") or "0"
    return (
        f"{row['transaction_number']}_{parent}_{row['folio_number']}_"
        f"{_date_str(row['transaction_date'])}"
    )


def assign_composite_keys(df: pd.DataFrame, registrar: Registrar) -> pd.DataFrame:
    out = df.copy()
    if registrar is Registrar.CAMS:
        out["composite_key"] = out.apply(lambda r: build_cams_key(r.to_dict()), axis=1)
    elif registrar is Registrar.KFINTECH:
        out["composite_key"] = out.apply(lambda r: build_kfintech_key(r.to_dict()), axis=1)
    else:
        raise ValueError(f"unknown registrar: {registrar}")
    return out
