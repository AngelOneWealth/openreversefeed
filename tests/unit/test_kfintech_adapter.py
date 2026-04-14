from datetime import date

import pandas as pd

from openreversefeed.adapters.kfintech import (
    KFintechCsvAdapter,
    KFintechFormat1Adapter,
    KFintechFormat2Adapter,
)
from openreversefeed.adapters.registry import AdapterRegistry, default_registry
from openreversefeed.core.models import Action


def test_kfintech_format_priorities():
    assert KFintechFormat1Adapter.priority == 90
    assert KFintechFormat2Adapter.priority == 80
    assert KFintechCsvAdapter.priority == 70


def test_kfintech_format1_discriminators():
    assert KFintechFormat1Adapter.discriminator_headers == {"TD_PURRED", "TRFLAG"}
    assert KFintechFormat1Adapter.mandatory_headers == {
        "INWARDNUM0",
        "TD_TRNO",
        "TD_ACNO",
        "FMCODE",
        "TD_UNITS",
        "TD_AMT",
        "TRNMODE",
    }


def test_kfintech_format1_normalize():
    raw = pd.DataFrame(
        {
            "INWARDNUM0": ["551316"],
            "TD_TRNO": ["1227"],
            "TD_PTRNO": ["0"],
            "TD_ACNO": ["91046479506"],
            "FMCODE": ["SYN01"],
            "SCHPLN": ["SYNTEST00001"],
            "TD_UNITS": [593.677],
            "TD_AMT": [59367.7],
            "TD_TRDT": [date(2020, 7, 8)],
            "TRNMODE": ["N"],
            "TD_PURRED": ["P"],
            "TRFLAG": [""],
            "INV_NAME": ["John"],
        }
    )
    adapter = KFintechFormat1Adapter()
    df = adapter.normalize(raw)
    assert "transaction_id" in df.columns
    assert "parent_transaction_number" in df.columns
    assert "transaction_purred" in df.columns
    assert "transaction_flag" in df.columns
    assert df["transaction_id"].iloc[0] == "551316"


def test_kfintech_classify_trflag_overrides_purred():
    adapter = KFintechFormat1Adapter()
    row = {"transaction_flag": "TO", "transaction_purred": "P", "transaction_mode": "N"}
    assert adapter.classify_row(row)[:2] == (Action.SELL, "transfer_out")

    row = {"transaction_flag": "TI", "transaction_purred": "R", "transaction_mode": "N"}
    assert adapter.classify_row(row)[:2] == (Action.BUY, "transfer_in")


def test_kfintech_classify_purred_fallthrough():
    adapter = KFintechFormat1Adapter()
    for purred, expected in [
        ("P", (Action.BUY, "purchase")),
        ("R", (Action.SELL, "redemption")),
        ("D", (Action.BUY, "dividend")),
        ("DP", (Action.SELL, "dividend_payout")),
    ]:
        row = {"transaction_flag": "", "transaction_purred": purred, "transaction_mode": "N"}
        assert adapter.classify_row(row)[:2] == expected


def test_kfintech_classify_reversal_override():
    adapter = KFintechFormat1Adapter()
    row = {"transaction_flag": "", "transaction_purred": "P", "transaction_mode": "R"}
    _action, tag, is_rev = adapter.classify_row(row)
    assert tag == "reversal"
    assert is_rev is True


def test_kfintech_composite_key():
    adapter = KFintechFormat1Adapter()
    row = {
        "transaction_number": "1227",
        "parent_transaction_number": "0",
        "folio_number": "91046479506",
        "transaction_date": date(2020, 7, 8),
    }
    assert adapter.composite_key(row) == "1227_0_91046479506_20200708"


def test_kfintech_composite_key_missing_parent_defaults_zero():
    adapter = KFintechFormat1Adapter()
    row = {
        "transaction_number": "1227",
        "parent_transaction_number": None,
        "folio_number": "91046479506",
        "transaction_date": date(2020, 7, 8),
    }
    assert adapter.composite_key(row) == "1227_0_91046479506_20200708"


def test_kfintech_registrations():
    import openreversefeed.adapters.kfintech  # noqa: F401

    names = [cls.name for cls in default_registry._adapters]
    assert "kfintech_format1" in names
    assert "kfintech_format2" in names
    assert "kfintech_csv" in names


def test_kfintech_detection_priority_picks_format1_over_format2():
    reg = AdapterRegistry()
    reg.register(KFintechFormat1Adapter)
    reg.register(KFintechFormat2Adapter)
    headers = {
        "INWARDNUM0",
        "INWARDNO",
        "TD_TRNO",
        "TD_ACNO",
        "FMCODE",
        "TD_UNITS",
        "TD_AMT",
        "TD_NAV",
        "TRNMODE",
        "TD_PURRED",
        "TRFLAG",
    }
    assert reg.detect(headers).name == "kfintech_format1"
