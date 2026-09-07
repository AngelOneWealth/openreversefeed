"""Tests for parse_utils — quote normalization, header peeking, numeric coercion."""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

from openreversefeed.adapters.parse_utils import (
    has_quoted_headers,
    normalize_quoted_csv,
    peek_feed_headers,
    to_number,
)


def _write_csv(content: str) -> Path:
    """Write CSV content to a temp file and return its path."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write(content)
    return Path(f.name)


# --- normalize_quoted_csv ---


class TestNormalizeQuotedCsv:
    def test_strips_quoted_headers(self):
        path = _write_csv("'USRTRXNO','FOLIO','AMOUNT'\n'12345','67890','100.000'\n")
        df = normalize_quoted_csv(path)
        assert list(df.columns) == ["USRTRXNO", "FOLIO", "AMOUNT"]

    def test_strips_quoted_values(self):
        path = _write_csv("'USRTRXNO','FOLIO','AMOUNT'\n'12345','67890','100.000'\n")
        df = normalize_quoted_csv(path)
        assert df.iloc[0]["USRTRXNO"] == "12345"
        assert df.iloc[0]["FOLIO"] == "67890"
        assert df.iloc[0]["AMOUNT"] == "100.000"

    def test_ordinary_csv_unchanged(self):
        path = _write_csv("USRTRXNO,FOLIO,AMOUNT\n12345,67890,100.000\n")
        df = normalize_quoted_csv(path)
        assert list(df.columns) == ["USRTRXNO", "FOLIO", "AMOUNT"]
        assert df.iloc[0]["USRTRXNO"] == "12345"

    def test_internal_apostrophe_preserved(self):
        path = _write_csv("NAME,VALUE\nInvestor's Fund,100\n")
        df = normalize_quoted_csv(path)
        assert df.iloc[0]["NAME"] == "Investor's Fund"

    def test_mixed_quoted_and_unquoted(self):
        path = _write_csv("'USRTRXNO',FOLIO,'AMOUNT'\n'12345',67890,'100.000'\n")
        df = normalize_quoted_csv(path)
        assert list(df.columns) == ["USRTRXNO", "FOLIO", "AMOUNT"]
        assert df.iloc[0]["USRTRXNO"] == "12345"
        assert df.iloc[0]["FOLIO"] == "67890"


# --- peek_feed_headers ---


class TestPeekFeedHeaders:
    def test_returns_normalized_headers(self):
        path = _write_csv("'USRTRXNO','FOLIO','AMOUNT'\n'12345','67890','100'\n")
        headers = peek_feed_headers(path)
        assert headers == {"USRTRXNO", "FOLIO", "AMOUNT"}

    def test_returns_unquoted_headers(self):
        path = _write_csv("USRTRXNO,FOLIO,AMOUNT\n12345,67890,100\n")
        headers = peek_feed_headers(path)
        assert headers == {"USRTRXNO", "FOLIO", "AMOUNT"}

    def test_empty_file_returns_empty_set(self):
        path = _write_csv("")
        headers = peek_feed_headers(path)
        assert headers == set()


# --- has_quoted_headers ---


class TestHasQuotedHeaders:
    def test_detects_quoted(self):
        path = _write_csv("'USRTRXNO','FOLIO','AMOUNT'\n")
        assert has_quoted_headers(path) is True

    def test_detects_unquoted(self):
        path = _write_csv("USRTRXNO,FOLIO,AMOUNT\n")
        assert has_quoted_headers(path) is False


# --- to_number ---


class TestToNumber:
    def test_indian_comma_format(self):
        assert to_number("1,00,000.50") == 100000.50

    def test_western_comma_format(self):
        assert to_number("100,000.50") == 100000.50

    def test_plain_decimal(self):
        assert to_number("100.50") == 100.50

    def test_integer_string(self):
        assert to_number("100000") == 100000.0

    def test_float_passthrough(self):
        assert to_number(100.50) == 100.50

    def test_int_passthrough(self):
        assert to_number(100) == 100.0

    def test_empty_string_returns_nan(self):
        assert math.isnan(to_number(""))

    def test_none_returns_nan(self):
        assert math.isnan(to_number(None))

    def test_whitespace_only_returns_nan(self):
        assert math.isnan(to_number("  "))

    def test_dataframe_map_with_indian_commas(self):
        """to_number works as a pandas .map() target for mixed-format columns."""
        import pandas as pd

        col = pd.Series(["1,00,000.50", "5000", "12,345.00", ""])
        result = col.map(to_number)
        assert result.iloc[0] == 100000.50
        assert result.iloc[1] == 5000.0
        assert result.iloc[2] == 12345.00
        assert math.isnan(result.iloc[3])
