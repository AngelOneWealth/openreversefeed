"""Account resolver handling single and family PAN cases."""
from __future__ import annotations

from typing import Any

from openreversefeed.core.cache import PrewarmCache


class AmbiguousPanError(Exception):
    def __init__(self, pan: str, candidate_ids: list[str]) -> None:
        self.pan = pan
        self.candidate_ids = candidate_ids
        super().__init__(f"family PAN {pan} ambiguous: {candidate_ids}")


class PanNotFoundError(Exception):
    pass


def _canonicalize_name(value: Any) -> str:
    """Normalize an investor name for equality comparison.

    Collapses whitespace runs, upper-cases, strips punctuation-like
    leading/trailing spaces. Deliberately NOT a fuzzy match — two
    names only tie if they agree after canonicalization. This catches
    the common "RAJESH KUMAR" vs "Rajesh  Kumar" (double space) vs
    " rajesh kumar" case without introducing false positives.
    """
    if value is None:
        return ""
    return " ".join(str(value).upper().split())


def resolve_account(row: dict[str, Any], cache: PrewarmCache) -> dict[str, Any]:
    pan = str(row["pan"]).strip().upper()
    by_ownership = cache.accounts_by_pan.get(pan)
    if not by_ownership:
        raise PanNotFoundError(pan)

    # Single account
    if len(by_ownership) == 1:
        return next(iter(by_ownership.values()))

    # Explicit ownership match
    ot = row.get("ownership_type")
    if ot and ot in by_ownership:
        return by_ownership[ot]

    # Investor-name fallback for family PANs. When multiple accounts share
    # the PAN and the row doesn't declare an ownership_type we can match
    # against, try a canonicalised name equality against the stored
    # account names. The adapters already emit an investor_name column
    # (CAMS INVNAME, KFintech INV_NAME).
    feed_name = _canonicalize_name(row.get("investor_name"))
    if feed_name:
        matches = [
            acc
            for acc in by_ownership.values()
            if _canonicalize_name(acc.get("name")) == feed_name
        ]
        if len(matches) == 1:
            return matches[0]

    # Prefer 'individual' default
    if "individual" in by_ownership:
        return by_ownership["individual"]

    raise AmbiguousPanError(pan, [acc["id"] for acc in by_ownership.values()])
