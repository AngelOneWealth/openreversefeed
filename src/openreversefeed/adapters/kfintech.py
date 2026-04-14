"""KFintech (formerly KARVY) adapters. Three sub-formats: FORMAT1, FORMAT2, CSV."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from openreversefeed.adapters.base import AggregationStrategy, FeedAdapter, PairRemovalStrategy
from openreversefeed.adapters.registry import default_registry
from openreversefeed.core.models import Action, Registrar

_FORMAT1_FIELD_MAP = {
    "INWARDNUM0": "transaction_id",
    "TD_TRNO": "transaction_number",
    "TD_PTRNO": "parent_transaction_number",
    "TD_ACNO": "folio_number",
    "FMCODE": "product_code",
    "SCHPLN": "scheme_code",
    "TD_UNITS": "units",
    "TD_AMT": "amount",
    "TD_NAV": "nav",
    "TD_TRDT": "transaction_date",
    "TRNMODE": "transaction_mode",
    "TD_PURRED": "transaction_purred",
    "TRFLAG": "transaction_flag",
    "TD_TRTYPE": "transaction_type",
    "PANNO": "pan",
    "INV_NAME": "investor_name",
    "BROK_CODE": "broker_code",
}

_FORMAT2_FIELD_MAP = dict(_FORMAT1_FIELD_MAP)
_FORMAT2_FIELD_MAP.pop("INWARDNUM0", None)
_FORMAT2_FIELD_MAP["INWARDNO"] = "transaction_id"

_CSV_FIELD_MAP = {
    "Inward Number": "transaction_id",
    "Transaction Number": "transaction_number",
    "Parent Transaction Number": "parent_transaction_number",
    "Folio Number": "folio_number",
    "AMC Code": "product_code",
    "Scheme Code": "scheme_code",
    "Units": "units",
    "Amount": "amount",
    "NAV": "nav",
    "Transaction Date": "transaction_date",
    "Transaction Mode": "transaction_mode",
    "Transaction Purred": "transaction_purred",
    "Transfer Flag": "transaction_flag",
    "Transaction Type": "transaction_type",
    "PAN": "pan",
    "Investor Name": "investor_name",
    "Broker Code": "broker_code",
}

_TYPE_FLIP_MAP = {"P": "R", "R": "P", "D": "DP", "DP": "D"}

_PURRED_TO_ACTION = {
    "P": (Action.BUY, "purchase"),
    "R": (Action.SELL, "redemption"),
    "D": (Action.BUY, "dividend"),
    "DP": (Action.SELL, "dividend_payout"),
}

_FLAG_TO_ACTION = {
    "TI": (Action.BUY, "transfer_in"),
    "TO": (Action.SELL, "transfer_out"),
    "SI": (Action.BUY, "switch_in"),
    "SO": (Action.SELL, "switch_out"),
}


class _KFintechPairStrategy(PairRemovalStrategy):
    def remove(self, df: pd.DataFrame) -> pd.DataFrame:
        from openreversefeed.core.pair_removal import remove_kfintech_pairs

        return remove_kfintech_pairs(df)


class _KFintechAggregation(AggregationStrategy):
    def merge_partial_records(self, df: pd.DataFrame) -> pd.DataFrame:
        from openreversefeed.core.aggregation import aggregate_kfintech_transfers

        return aggregate_kfintech_transfers(df)


class _KFintechBase(FeedAdapter):
    registrar = Registrar.KFINTECH
    type_flip_map = _TYPE_FLIP_MAP

    def _normalize_with_map(self, raw: pd.DataFrame, fmap: dict[str, str]) -> pd.DataFrame:
        canonical_cols = {src: dst for src, dst in fmap.items() if src in raw.columns}
        unknown_cols = [c for c in raw.columns if c not in canonical_cols]
        df = raw.rename(columns=canonical_cols).copy()
        if unknown_cols:
            df["__source_meta"] = raw[unknown_cols].to_dict(orient="records")
        else:
            df["__source_meta"] = [{}] * len(df)
        df.insert(0, "registrar_row_index", range(len(df)))
        return df

    def pair_strategy(self) -> PairRemovalStrategy:
        return _KFintechPairStrategy()

    def aggregation_strategy(self) -> AggregationStrategy:
        return _KFintechAggregation()

    def classify_row(self, row: dict[str, Any]) -> tuple[Action, str, bool]:
        mode = row.get("transaction_mode")
        flag = row.get("transaction_flag") or ""
        purred = row.get("transaction_purred") or ""

        if flag in _FLAG_TO_ACTION:
            action, tag = _FLAG_TO_ACTION[flag]
        elif purred in _PURRED_TO_ACTION:
            action, tag = _PURRED_TO_ACTION[purred]
        else:
            action, tag = Action.NO_EFFECT, "other"

        if mode == "R":
            return action, "reversal", True
        return action, tag, False

    def composite_key(self, row: dict[str, Any]) -> str:
        parent = row.get("parent_transaction_number") or "0"
        date_val = row["transaction_date"]
        date_str = date_val.strftime("%Y%m%d") if hasattr(date_val, "strftime") else str(date_val)
        return f"{row['transaction_number']}_{parent}_{row['folio_number']}_{date_str}"


class KFintechFormat1Adapter(_KFintechBase):
    name = "kfintech_format1"
    priority = 90
    mandatory_headers = {
        "INWARDNUM0",
        "TD_TRNO",
        "TD_ACNO",
        "FMCODE",
        "TD_UNITS",
        "TD_AMT",
        "TRNMODE",
    }
    discriminator_headers = {"TD_PURRED", "TRFLAG"}
    field_map = _FORMAT1_FIELD_MAP

    def parse(self, file_path: str | Path) -> pd.DataFrame:
        return pd.read_excel(Path(file_path), dtype=str)

    def normalize(self, raw: pd.DataFrame) -> pd.DataFrame:
        return self._normalize_with_map(raw, _FORMAT1_FIELD_MAP)


class KFintechFormat2Adapter(_KFintechBase):
    name = "kfintech_format2"
    priority = 80
    mandatory_headers = {"INWARDNO", "TD_ACNO", "TD_UNITS", "TD_NAV"}
    discriminator_headers: set[str] = set()
    field_map = _FORMAT2_FIELD_MAP

    def parse(self, file_path: str | Path) -> pd.DataFrame:
        return pd.read_excel(Path(file_path), dtype=str)

    def normalize(self, raw: pd.DataFrame) -> pd.DataFrame:
        return self._normalize_with_map(raw, _FORMAT2_FIELD_MAP)


class KFintechCsvAdapter(_KFintechBase):
    name = "kfintech_csv"
    priority = 70
    mandatory_headers = {"Inward Number", "Folio Number", "Units", "NAV"}
    discriminator_headers: set[str] = set()
    field_map = _CSV_FIELD_MAP

    def parse(self, file_path: str | Path) -> pd.DataFrame:
        return pd.read_csv(Path(file_path), dtype=str)

    def normalize(self, raw: pd.DataFrame) -> pd.DataFrame:
        return self._normalize_with_map(raw, _CSV_FIELD_MAP)


default_registry.register(KFintechFormat1Adapter)
default_registry.register(KFintechFormat2Adapter)
default_registry.register(KFintechCsvAdapter)
