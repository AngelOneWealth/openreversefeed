"""Cleaner — composes all df-level cleaning steps from spec §5 steps 4-6."""
from __future__ import annotations

import pandas as pd

from openreversefeed.adapters.base import FeedAdapter
from openreversefeed.core.aggregation import aggregate_cams_switches, aggregate_kfintech_transfers
from openreversefeed.core.composite_key import assign_composite_keys
from openreversefeed.core.conflict import resolve_kfintech_conflicts
from openreversefeed.core.dedup import drop_in_file_duplicates
from openreversefeed.core.models import Registrar
from openreversefeed.core.negative_fix import correct_negative_rows
from openreversefeed.core.pair_removal import remove_cams_pairs, remove_kfintech_pairs


class Cleaner:
    def run(self, df: pd.DataFrame, adapter: FeedAdapter) -> pd.DataFrame:
        if df.empty:
            return df.copy()

        step = df.copy()

        # Drop rows whose transaction_type is in the adapter's rejected set
        # (e.g. CAMS TICOB / TOCOB). These do not represent real orders and
        # silently classifying them as transfer in/out would corrupt positions.
        rejected = getattr(adapter, "rejected_types", set()) or set()
        if rejected and "transaction_type" in step.columns:
            step = step[~step["transaction_type"].isin(rejected)].reset_index(drop=True)
            if step.empty:
                return step

        # Step 4b — pair removal (registrar-specific)
        if adapter.registrar is Registrar.KFINTECH:
            step = remove_kfintech_pairs(step)
        else:
            step = remove_cams_pairs(step)

        # Step 4c — negative value correction
        step = correct_negative_rows(step, adapter.type_flip_map)

        # Step 4d — aggregation (also sets original_trans_number)
        if adapter.registrar is Registrar.KFINTECH:
            step = aggregate_kfintech_transfers(step)
        else:
            step = aggregate_cams_switches(step)

        # Step 4e — KFintech P+SIN conflict resolution
        if adapter.registrar is Registrar.KFINTECH:
            step = resolve_kfintech_conflicts(step)

        # Step 5 — assign composite keys
        step = assign_composite_keys(step, adapter.registrar)

        # Step 4a — in-file duplicate removal (AFTER composite keys are assigned)
        step = drop_in_file_duplicates(step)

        # Step 6 — classify action per row
        if not step.empty:
            classifications = step.apply(
                lambda row: adapter.classify_row(row.to_dict()),
                axis=1,
                result_type="expand",
            )
            classifications.columns = ["action", "action_tag", "is_reversal"]
            step = pd.concat([step, classifications], axis=1)

        return step
