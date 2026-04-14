from datetime import date

import pandas as pd

from openreversefeed.adapters.cams import CamsAdapter
from openreversefeed.adapters.kfintech import KFintechFormat1Adapter
from openreversefeed.core.cleaner import Cleaner


def test_cleaner_runs_all_steps_on_minimal_cams_df():
    cleaner = Cleaner()
    adapter = CamsAdapter()
    df = pd.DataFrame(
        [
            {
                "transaction_id": "1",
                "folio_number": "F1",
                "product_code": "P1",
                "scheme_code": "S1",
                "units": 100.0,
                "amount": 10000.0,
                "transaction_date": date(2025, 1, 1),
                "transaction_mode": "N",
                "transaction_type": "P",
                "transaction_number": "T1",
                "registrar_row_index": 0,
                "__source_meta": [{}],
            }
        ]
    )
    out = cleaner.run(df, adapter)
    assert not out.empty
    assert "composite_key" in out.columns
    assert "action" in out.columns
    assert "action_tag" in out.columns


def test_cleaner_kfintech_preserves_group_columns_through_conflict_resolution():
    """Regression: the conflict resolver must not strip transaction_number or
    folio_number from the cleaned DataFrame, otherwise the composite-key
    builder fails with KeyError downstream."""
    cleaner = Cleaner()
    adapter = KFintechFormat1Adapter()
    df = pd.DataFrame(
        [
            {
                "transaction_id": "KF001",
                "transaction_number": "T1",
                "parent_transaction_number": "0",
                "folio_number": "F1",
                "product_code": "P1",
                "scheme_code": "S1",
                "units": 100.0,
                "amount": 10000.0,
                "transaction_date": date(2025, 1, 1),
                "transaction_mode": "N",
                "transaction_purred": "P",
                "transaction_flag": "",
                "transaction_type": "",
                "registrar_row_index": 0,
                "__source_meta": [{}],
            },
            {
                "transaction_id": "KF002",
                "transaction_number": "T2",
                "parent_transaction_number": "0",
                "folio_number": "F1",
                "product_code": "P1",
                "scheme_code": "S1",
                "units": 50.0,
                "amount": 5000.0,
                "transaction_date": date(2025, 1, 2),
                "transaction_mode": "N",
                "transaction_purred": "R",
                "transaction_flag": "TO",
                "transaction_type": "",
                "registrar_row_index": 1,
                "__source_meta": [{}],
            },
        ]
    )
    out = cleaner.run(df, adapter)
    assert "transaction_number" in out.columns, (
        "transaction_number must survive the cleaner pipeline — "
        "otherwise build_kfintech_key raises KeyError"
    )
    assert "folio_number" in out.columns
    assert "composite_key" in out.columns
    assert not out["composite_key"].isna().any()
