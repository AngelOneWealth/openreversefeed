"""FeedAdapter ABC and per-registrar strategy interfaces."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import pandas as pd

from openreversefeed.core.models import Action, Registrar


class PairRemovalStrategy(ABC):
    """Strategy for removing redemption+reversal pairs from a cleaned DataFrame."""

    @abstractmethod
    def remove(self, df: pd.DataFrame) -> pd.DataFrame: ...


class AggregationStrategy(ABC):
    """Strategy for merging partial transfer/switch rows into one business transaction."""

    @abstractmethod
    def merge_partial_records(self, df: pd.DataFrame) -> pd.DataFrame: ...


class FeedAdapter(ABC):
    """Base class for registrar-specific feed adapters. See spec §6.1."""

    name: str
    registrar: Registrar
    priority: int
    mandatory_headers: set[str]
    discriminator_headers: set[str]
    field_map: dict[str, str]
    type_flip_map: dict[str, str]

    @abstractmethod
    def parse(self, file_path: str | Path) -> pd.DataFrame:
        """Read the file from disk, return a raw DataFrame (source column names)."""

    @abstractmethod
    def normalize(self, raw: pd.DataFrame) -> pd.DataFrame:
        """Rename columns to canonical names, add __source_meta dict column, add registrar_row_index."""

    @abstractmethod
    def pair_strategy(self) -> PairRemovalStrategy: ...

    @abstractmethod
    def aggregation_strategy(self) -> AggregationStrategy: ...

    @abstractmethod
    def classify_row(self, row: dict[str, Any]) -> tuple[Action, str, bool]:
        """Return (action, action_tag, is_reversal) for a single normalized row."""

    @abstractmethod
    def composite_key(self, row: dict[str, Any]) -> str:
        """Build the deterministic composite key for a single normalized row."""
