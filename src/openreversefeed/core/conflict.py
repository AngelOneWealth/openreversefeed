"""KFintech conflict resolution — P+SIN dedup. See spec §5 step 4e."""
from __future__ import annotations

import pandas as pd


def resolve_kfintech_conflicts(df: pd.DataFrame) -> pd.DataFrame:
    """If a `(transaction_number, folio_number)` group contains both a plain
    ``P`` (purchase) and any ``*SIN`` marker row, keep only the first ``P``
    and drop the SIN rows. Groups without that collision are untouched.

    Implemented as a manual row-index scan rather than ``groupby.apply`` so
    that the returned DataFrame keeps every column of the input — using
    ``groupby.apply`` with ``include_groups=False`` strips the group columns
    from the output, and ``include_groups=True`` is deprecated in pandas
    2.2.
    """
    if df.empty:
        return df.copy()

    required = {"transaction_number", "folio_number", "transaction_purred"}
    if not required.issubset(df.columns):
        return df.copy()

    kept_indices: list = []
    for _key, group in df.groupby(
        ["transaction_number", "folio_number"], sort=False
    ):
        purreds = set(group["transaction_purred"])
        has_sin = any(
            isinstance(p, str) and (p == "SIN" or p.endswith("SIN"))
            for p in purreds
        )
        if "P" in purreds and has_sin:
            first_p = group[group["transaction_purred"] == "P"].head(1)
            kept_indices.extend(first_p.index.tolist())
        else:
            kept_indices.extend(group.index.tolist())

    return df.loc[kept_indices].reset_index(drop=True)
