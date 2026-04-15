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
    # CAMS ships an "REINVEST_F" column that encodes whether the dividend
    # option on the scheme is a reinvestment or a payout. We capture the
    # raw flag so validators / downstream can check it against the scheme
    # master's plan_type.
    "REINVEST_F": "dividend_option_flag",
}

# Mapping from the raw CAMS REINVEST_F flag to the canonical plan_type
# vocabulary the scheme master stores. 'Y' means reinvest, 'N' means
# payout. Anything else (empty, 'P' for pure growth, nulls) → None,
# which means "the feed doesn't tell us, don't assert anything."
CAMS_REINVEST_F_TO_PLAN_TYPE: dict[str, str] = {
    "Y": "idcw_reinvest",
    "N": "idcw_payout",
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

_BUY_TYPES = {"P", "SI", "TI", "D", "BON", "NFO"}
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
    # NFO (New Fund Offer): initial subscription to a new scheme during the
    # offer period. Classified as a purchase in the ledger — the investor is
    # acquiring units at the NFO price (usually ₹10) and the outcome is a
    # buy position just like a regular purchase.
    "NFO": "new_fund_offer",
}

# CAMS transaction types we actively refuse. TICOB / TOCOB are the
# "close of business" variants of transfer in/out and the source system
# rejects them at validation time. If you have a registrar that ships real
# COB data you want to process, subclass CamsAdapter and clear this set.
_REJECTED_TYPES = {"TICOB", "TOCOB"}


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
    rejected_types = _REJECTED_TYPES

    def parse(self, file_path: str | Path) -> pd.DataFrame:
        path = Path(file_path)
        suffix = path.suffix.lower()
        if suffix in (".xls", ".xlsx"):
            return pd.read_excel(path, dtype=str)
        if suffix == ".csv":
            return pd.read_csv(path, dtype=str)
        if suffix == ".dbf":
            from dbfread import DBF

            records = [dict(r) for r in DBF(str(path), load=True, char_decode_errors="ignore")]
            return pd.DataFrame(records, dtype=str)
        raise ValueError(f"unsupported file type for CAMS: {suffix}")

    def normalize(self, raw: pd.DataFrame) -> pd.DataFrame:
        canonical_cols = {src: dst for src, dst in self.field_map.items() if src in raw.columns}
        unknown_cols = [c for c in raw.columns if c not in canonical_cols]

        df = raw.rename(columns=canonical_cols).copy()

        if unknown_cols:
            df["__source_meta"] = raw[unknown_cols].to_dict(orient="records")
        else:
            df["__source_meta"] = [{}] * len(df)

        # Translate the CAMS REINVEST_F flag into the canonical plan_type
        # vocabulary the scheme master uses. Leaves None where the feed
        # is silent so the validator can skip the check cleanly.
        if "dividend_option_flag" in df.columns:
            df["plan_type_from_feed"] = (
                df["dividend_option_flag"]
                .astype(str)
                .str.strip()
                .str.upper()
                .map(CAMS_REINVEST_F_TO_PLAN_TYPE)
            )
        else:
            df["plan_type_from_feed"] = None

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
