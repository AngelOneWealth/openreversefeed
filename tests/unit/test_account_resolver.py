import pytest

from openreversefeed.core.account_resolver import (
    AmbiguousPanError,
    PanNotFoundError,
    resolve_account,
)
from openreversefeed.core.cache import PrewarmCache


def test_single_account_resolves():
    cache = PrewarmCache(accounts_by_pan={"P1": {"individual": {"id": "u1"}}})
    row = {"pan": "P1", "ownership_type": "individual"}
    acc = resolve_account(row, cache)
    assert acc["id"] == "u1"


def test_family_pan_matches_ownership_type():
    cache = PrewarmCache(
        accounts_by_pan={"P1": {"individual": {"id": "u1"}, "joint": {"id": "u2"}}}
    )
    row = {"pan": "P1", "ownership_type": "joint"}
    acc = resolve_account(row, cache)
    assert acc["id"] == "u2"


def test_family_pan_ambiguous_raises():
    cache = PrewarmCache(
        accounts_by_pan={"P1": {"huf": {"id": "u1"}, "joint": {"id": "u2"}}}
    )
    row = {"pan": "P1", "ownership_type": None}
    with pytest.raises(AmbiguousPanError) as exc_info:
        resolve_account(row, cache)
    assert set(exc_info.value.candidate_ids) == {"u1", "u2"}


def test_family_pan_defaults_to_individual():
    cache = PrewarmCache(
        accounts_by_pan={"P1": {"individual": {"id": "u1"}, "huf": {"id": "u2"}}}
    )
    row = {"pan": "P1", "ownership_type": "unknown"}
    acc = resolve_account(row, cache)
    assert acc["id"] == "u1"


def test_pan_not_found():
    cache = PrewarmCache(accounts_by_pan={})
    with pytest.raises(PanNotFoundError):
        resolve_account({"pan": "P1"}, cache)


def test_family_pan_falls_back_to_investor_name_match():
    """When the ownership_type can't tie-break a family PAN, a canonical
    name match picks the right account. Catches the common
    'Rajesh  Kumar' vs 'RAJESH KUMAR' whitespace/case drift between the
    feed file and the account master."""
    cache = PrewarmCache(
        accounts_by_pan={
            "P1": {
                "huf": {"id": "u1", "name": "Suresh Kumar HUF"},
                "joint": {"id": "u2", "name": "Rajesh Kumar"},
            }
        }
    )
    row = {"pan": "P1", "ownership_type": None, "investor_name": "  rajesh   kumar "}
    acc = resolve_account(row, cache)
    assert acc["id"] == "u2"


def test_family_pan_name_fallback_needs_unique_match():
    """If two stored accounts both match the canonical name, fall through
    to the individual default / ambiguous error rather than picking one."""
    cache = PrewarmCache(
        accounts_by_pan={
            "P1": {
                "huf": {"id": "u1", "name": "Rajesh Kumar"},
                "joint": {"id": "u2", "name": "Rajesh Kumar"},
            }
        }
    )
    row = {"pan": "P1", "ownership_type": None, "investor_name": "RAJESH KUMAR"}
    with pytest.raises(AmbiguousPanError) as exc_info:
        resolve_account(row, cache)
    assert set(exc_info.value.candidate_ids) == {"u1", "u2"}


def test_family_pan_name_fallback_ignored_without_investor_name():
    """If the feed row doesn't ship an investor name at all, the fallback
    must not activate — we rely on the existing individual default."""
    cache = PrewarmCache(
        accounts_by_pan={
            "P1": {
                "individual": {"id": "u1", "name": "Rajesh Kumar"},
                "joint": {"id": "u2", "name": "Suresh Kumar"},
            }
        }
    )
    row = {"pan": "P1", "ownership_type": None, "investor_name": None}
    acc = resolve_account(row, cache)
    assert acc["id"] == "u1"
