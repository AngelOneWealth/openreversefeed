"""Feed parsing helpers — quote normalization, header peeking, numeric coercion."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pandas as pd


def _strip_outer_quotes(value: str) -> str:
    """Strip matched leading/trailing single quotes from a string value."""
    if len(value) >= 2 and value[0] == "'" and value[-1] == "'":
        return value[1:-1]
    return value


def normalize_quoted_csv(file_path: str | Path) -> pd.DataFrame:
    """Read a CSV that may have single-quoted headers and cell values.

    Strips matched leading/trailing single quotes from column names and
    from all string cell values. Leaves unquoted values and internal
    apostrophes untouched.
    """
    df = pd.read_csv(Path(file_path), dtype=str)
    df.columns = pd.Index([_strip_outer_quotes(c) for c in df.columns])
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].map(lambda v: _strip_outer_quotes(v) if isinstance(v, str) else v)
    return df


def peek_feed_headers(file_path: str | Path) -> set[str]:
    """Read only the first line of a CSV and return normalized header names.

    Applies the same single-quote stripping as normalize_quoted_csv so
    detection works on quoted CAMS lot-level files.
    """
    path = Path(file_path)
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        try:
            raw_headers = next(reader)
        except StopIteration:
            return set()
    return {_strip_outer_quotes(h.strip()) for h in raw_headers if h.strip()}


def has_quoted_headers(file_path: str | Path) -> bool:
    """Return True if the CSV header row contains single-quoted column names."""
    path = Path(file_path)
    with path.open(newline="", encoding="utf-8-sig") as f:
        first_line = f.readline()
    return first_line.startswith("'") and "'," in first_line


def to_number(value: Any) -> float:
    """Convert a value to float, stripping commas from Indian-formatted numbers.

    Returns float('nan') for empty strings and None.
    """
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return float("nan")
    s = str(value).strip()
    if not s:
        return float("nan")
    s = s.replace(",", "")
    return float(s)
