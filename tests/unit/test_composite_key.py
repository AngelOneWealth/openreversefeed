from datetime import date, datetime

import pandas as pd

from openreversefeed.core.composite_key import (
    _date_str,
    assign_composite_keys,
    build_cams_key,
    build_kfintech_key,
)
from openreversefeed.core.models import Registrar


def test_cams_key_deterministic():
    row = {
        "original_trans_number": "1997865738",
        "transaction_type": "SI",
        "transaction_number": "1311531177",
        "transaction_date": date(2025, 7, 29),
    }
    assert build_cams_key(row) == "1997865738_SI_1311531177_20250729"


def test_kfintech_key_deterministic():
    row = {
        "transaction_number": "1227",
        "parent_transaction_number": "0",
        "folio_number": "91046479506",
        "transaction_date": date(2020, 7, 8),
    }
    assert build_kfintech_key(row) == "1227_0_91046479506_20200708"


def test_kfintech_key_none_parent_becomes_zero():
    row = {
        "transaction_number": "1227",
        "parent_transaction_number": None,
        "folio_number": "91046479506",
        "transaction_date": date(2020, 7, 8),
    }
    assert build_kfintech_key(row) == "1227_0_91046479506_20200708"


def test_assign_keys_writes_column_for_cams():
    df = pd.DataFrame(
        {
            "original_trans_number": ["1997865738"],
            "transaction_type": ["SI"],
            "transaction_number": ["1311531177"],
            "transaction_date": [date(2025, 7, 29)],
        }
    )
    out = assign_composite_keys(df, Registrar.CAMS)
    assert "composite_key" in out.columns
    assert out["composite_key"].iloc[0] == "1997865738_SI_1311531177_20250729"
    assert "composite_key" not in df.columns  # pure function


def test_assign_keys_writes_column_for_kfintech():
    df = pd.DataFrame(
        {
            "transaction_number": ["1227"],
            "parent_transaction_number": ["0"],
            "folio_number": ["91046479506"],
            "transaction_date": [date(2020, 7, 8)],
        }
    )
    out = assign_composite_keys(df, Registrar.KFINTECH)
    assert out["composite_key"].iloc[0] == "1227_0_91046479506_20200708"


# --- _date_str regression tests for real registrar date formats ---


class TestDateStrFormats:
    """All registrar date representations must normalize to YYYYMMDD."""

    def test_python_date_object(self):
        assert _date_str(date(2026, 8, 28)) == "20260828"

    def test_python_datetime_object(self):
        assert _date_str(datetime(2026, 8, 28, 14, 30)) == "20260828"

    def test_iso_date_string(self):
        assert _date_str("2026-08-28") == "20260828"

    def test_dd_mm_yyyy_slash(self):
        assert _date_str("28/08/2026") == "20260828"

    def test_dd_mm_yyyy_dash(self):
        assert _date_str("28-08-2026") == "20260828"

    def test_us_date_with_ampm(self):
        assert _date_str("8/28/2026  12:00:00 AM") == "20260828"

    def test_us_date_with_ampm_single_digit(self):
        assert _date_str("1/5/2026  12:00:00 AM") == "20260105"

    def test_js_date_tostring(self):
        assert _date_str("Fri Aug 28 2026 00:00:00 GMT+0530 (India Standard Time)") == "20260828"

    def test_day_gt_12_unambiguous_slash(self):
        """Day > 12 forces DD/MM interpretation."""
        assert _date_str("28/08/2026") == "20260828"

    def test_ambiguous_slash_defaults_to_dd_mm(self):
        """When both parts <= 12 and no AM/PM, default to DD/MM (Indian convention)."""
        assert _date_str("1/2/2026") == "20260201"

    def test_single_digit_day_month_dd_mm(self):
        assert _date_str("5/1/2026") == "20260105"

    def test_already_normalized_yyyymmdd(self):
        assert _date_str("20260828") == "20260828"

    def test_cams_key_with_string_date(self):
        """Composite key builder works with string dates from feeds."""
        row = {
            "original_trans_number": "462400251803",
            "transaction_type": "P0818S",
            "transaction_number": "1648940947",
            "transaction_date": "28/08/2026",
        }
        assert build_cams_key(row) == "462400251803_P0818S_1648940947_20260828"

    def test_kfintech_key_with_string_date(self):
        row = {
            "transaction_number": "1227",
            "parent_transaction_number": "0",
            "folio_number": "91046479506",
            "transaction_date": "8/28/2026  12:00:00 AM",
        }
        assert build_kfintech_key(row) == "1227_0_91046479506_20260828"

    def test_all_formats_produce_same_key(self):
        """Multiple date representations for the same calendar day produce identical keys."""
        base = {
            "original_trans_number": "TXN001",
            "transaction_type": "P",
            "transaction_number": "999",
        }
        date_variants = [
            date(2026, 8, 28),
            "28/08/2026",
            "8/28/2026  12:00:00 AM",
            "28-08-2026",
            "2026-08-28",
        ]
        keys = {build_cams_key({**base, "transaction_date": d}) for d in date_variants}
        assert len(keys) == 1, f"Expected 1 unique key, got {keys}"
