from datetime import date

import pandas as pd

from openreversefeed.adapters.cams import CamsAdapter
from openreversefeed.adapters.registry import default_registry
from openreversefeed.core.models import Action, Registrar


def test_cams_adapter_registered_priority_100():
    assert CamsAdapter.priority == 100
    assert CamsAdapter.registrar is Registrar.CAMS
    assert CamsAdapter.mandatory_headers == {
        "USRTRXNO",
        "FOLIO_NO",
        "PRODCODE",
        "SCHEME_CODE",
        "UNITS",
        "AMOUNT",
        "TRADDATE",
        "TRXNMODE",
        "TRXNTYPE",
    }


def test_cams_normalize_renames_columns():
    raw = pd.DataFrame(
        {
            "USRTRXNO": ["1997865738"],
            "FOLIO_NO": ["1310253377"],
            "PRODCODE": ["SYN24-GR"],
            "SCHEME_CODE": ["SYNTEST00001"],
            "UNITS": [100.5],
            "AMOUNT": [10050.0],
            "TRADDATE": [date(2025, 7, 28)],
            "TRXNMODE": ["N"],
            "TRXNTYPE": ["P"],
            "TRNSERIALNO": ["abc"],
        }
    )
    adapter = CamsAdapter()
    normalized = adapter.normalize(raw)

    expected_cols = {
        "transaction_id",
        "folio_number",
        "product_code",
        "scheme_code",
        "units",
        "amount",
        "transaction_date",
        "transaction_mode",
        "transaction_type",
        "__source_meta",
        "registrar_row_index",
    }
    assert expected_cols.issubset(set(normalized.columns))
    assert normalized["transaction_id"].iloc[0] == "1997865738"
    assert normalized["units"].iloc[0] == 100.5
    assert normalized["registrar_row_index"].iloc[0] == 0


def test_cams_classify_purchase():
    adapter = CamsAdapter()
    row = {"transaction_type": "P", "transaction_mode": "N"}
    action, tag, is_rev = adapter.classify_row(row)
    assert action is Action.BUY
    assert tag == "purchase"
    assert is_rev is False


def test_cams_classify_reversal_override():
    adapter = CamsAdapter()
    row = {"transaction_type": "P", "transaction_mode": "R"}
    action, tag, is_rev = adapter.classify_row(row)
    assert tag == "reversal"
    assert is_rev is True


def test_cams_classify_switch_in_and_out():
    adapter = CamsAdapter()
    assert adapter.classify_row({"transaction_type": "SI", "transaction_mode": "N"}) == (
        Action.BUY,
        "switch_in",
        False,
    )
    assert adapter.classify_row({"transaction_type": "SO", "transaction_mode": "N"}) == (
        Action.SELL,
        "switch_out",
        False,
    )


def test_cams_classify_non_financial_no_effect():
    adapter = CamsAdapter()
    action, _tag, _ = adapter.classify_row({"transaction_type": "N", "transaction_mode": "N"})
    assert action is Action.NO_EFFECT


def test_cams_composite_key_deterministic():
    adapter = CamsAdapter()
    row = {
        "original_trans_number": "1997865738",
        "transaction_type": "SI",
        "transaction_number": "1311531177",
        "transaction_date": date(2025, 7, 29),
    }
    assert adapter.composite_key(row) == "1997865738_SI_1311531177_20250729"


def test_cams_registered_in_default_registry():
    import openreversefeed.adapters.cams  # noqa: F401

    assert any(a is CamsAdapter for a in default_registry._adapters)
