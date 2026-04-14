"""CAMS_FORMAT1 adapter. See spec §5 step 3."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from openreversefeed.adapters.base import AggregationStrategy, FeedAdapter, PairRemovalStrategy
from openreversefeed.adapters.registry import default_registry
from openreversefeed.core.models import Action, Registrar

_FIELD_MAP: dict[str, str] = {
    "USRTRXNO": "transaction_id",
    "FOLIO_NO": "folio_number",
    "PRODCODE": "product_code",
    "SCHEME_CODE": "scheme_code",
    "UNITS": "units",
    "AMOUNT": "amount",
    "TRADDATE": "transaction_date",
    "TRXNMODE": "transaction_mode",
    "TRXNTYPE": "transaction_type",
    "TRNSERIALNO": "transaction_number",
    "NAV": "nav",
    "BROKCODE": "broker_code",
    "PANNO": "pan",
    "INVNAME": "investor_name",
}

_TYPE_FLIP_MAP: dict[str, str] = {
    "P": "R",
    "R": "P",
    "SI": "SO",
    "SO": "SI",
    "TI": "TO",
    "TO": "TI",
    "D": "DP",
    "DP": "D",
}

_BUY_TYPES = {"P", "SI", "TI", "D", "BON"}
_SELL_TYPES = {"R", "SO", "TO", "DP"}
_NO_EFFECT_TYPES = {"N", "J"}

_TYPE_TO_TAG = {
    "P": "purchase",
    "R": "redemption",
    "SI": "switch_in",
    "SO": "switch_out",
    "TI": "transfer_in",
    "TO": "transfer_out",
    "D": "dividend",
    "DP": "dividend_payout",
    "BON": "bonus",
}


class _CamsPairStrategy(PairRemovalStrategy):
    def remove(self, df: pd.DataFrame) -> pd.DataFrame:
        from openreversefeed.core.pair_removal import remove_cams_pairs

        return remove_cams_pairs(df)


class _CamsAggregation(AggregationStrategy):
    def merge_partial_records(self, df: pd.DataFrame) -> pd.DataFrame:
        from openreversefeed.core.aggregation import aggregate_cams_switches

        return aggregate_cams_switches(df)


class CamsAdapter(FeedAdapter):
    name = "cams"
    registrar = Registrar.CAMS
    priority = 100
    mandatory_headers = {
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
    discriminator_headers: set[str] = set()
    field_map = _FIELD_MAP
    type_flip_map = _TYPE_FLIP_MAP

    def parse(self, file_path: str | Path) -> pd.DataFrame:
        path = Path(file_path)
        suffix = path.suffix.lower()
        if suffix in (".xls", ".xlsx"):
            return pd.read_excel(path, dtype=str)
        if suffix == ".csv":
            return pd.read_csv(path, dtype=str)
        raise ValueError(f"unsupported file type for CAMS: {suffix}")

    def normalize(self, raw: pd.DataFrame) -> pd.DataFrame:
        canonical_cols = {src: dst for src, dst in self.field_map.items() if src in raw.columns}
        unknown_cols = [c for c in raw.columns if c not in canonical_cols]

        df = raw.rename(columns=canonical_cols).copy()

        if unknown_cols:
            df["__source_meta"] = raw[unknown_cols].to_dict(orient="records")
        else:
            df["__source_meta"] = [{}] * len(df)

        df.insert(0, "registrar_row_index", range(len(df)))
        return df

    def pair_strategy(self) -> PairRemovalStrategy:
        return _CamsPairStrategy()

    def aggregation_strategy(self) -> AggregationStrategy:
        return _CamsAggregation()

    def classify_row(self, row: dict[str, Any]) -> tuple[Action, str, bool]:
        mode = row.get("transaction_mode")
        txn_type = str(row.get("transaction_type", ""))

        # Match on longest prefix (handles composite codes like SISF22S → SI)
        prefix = next(
            (
                t
                for t in sorted(_TYPE_TO_TAG.keys(), key=len, reverse=True)
                if txn_type.startswith(t)
            ),
            txn_type,
        )

        if prefix in _BUY_TYPES:
            action = Action.BUY
        elif prefix in _SELL_TYPES:
            action = Action.SELL
        elif prefix in _NO_EFFECT_TYPES:
            action = Action.NO_EFFECT
        else:
            action = Action.NO_EFFECT

        tag = _TYPE_TO_TAG.get(prefix, "other")

        if mode == "R":
            return action, "reversal", True
        return action, tag, False

    def composite_key(self, row: dict[str, Any]) -> str:
        date_val = row["transaction_date"]
        date_str = date_val.strftime("%Y%m%d") if hasattr(date_val, "strftime") else str(date_val)
        return (
            f"{row['original_trans_number']}_{row['transaction_type']}_"
            f"{row['transaction_number']}_{date_str}"
        )


default_registry.register(CamsAdapter)
