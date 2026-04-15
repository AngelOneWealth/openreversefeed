import pytest

from openreversefeed.core.cache import PrewarmCache
from openreversefeed.core.models import CorrectionType
from openreversefeed.core.validator import ValidationError, validate_row

_CACHE = PrewarmCache(
    schemes_by_code={"SCH1": {"id": 1, "amc_id": 10}},
    accounts_by_pan={"ABCDE1234F": {"individual": {"id": "acc-1"}}},
)

_VALID = {
    "pan": "ABCDE1234F",
    "folio_number": "F1",
    "scheme_code": "SCH1",
    "amount": 1000.0,
    "units": 10.0,
    "transaction_date": "2025-01-01",
}


def test_valid_row_passes():
    validate_row(dict(_VALID), _CACHE)


def test_missing_pan_raises_pan_not_found():
    row = dict(_VALID)
    row["pan"] = ""
    with pytest.raises(ValidationError) as exc_info:
        validate_row(row, _CACHE)
    assert exc_info.value.correction_type is CorrectionType.OTHER


def test_invalid_pan_format_raises():
    row = dict(_VALID)
    row["pan"] = "NOTAPAN"
    with pytest.raises(ValidationError) as exc_info:
        validate_row(row, _CACHE)
    assert exc_info.value.correction_type is CorrectionType.PAN_NOT_FOUND


def test_unknown_pan_in_cache_raises():
    row = dict(_VALID)
    row["pan"] = "ZZZZZ9999Z"
    with pytest.raises(ValidationError) as exc_info:
        validate_row(row, _CACHE)
    assert exc_info.value.correction_type is CorrectionType.PAN_NOT_FOUND


def test_unknown_scheme_raises():
    row = dict(_VALID)
    row["scheme_code"] = "UNKNOWN"
    with pytest.raises(ValidationError) as exc_info:
        validate_row(row, _CACHE)
    assert exc_info.value.correction_type is CorrectionType.SCHEME_NOT_FOUND


def test_missing_folio_number():
    row = dict(_VALID)
    row["folio_number"] = ""
    with pytest.raises(ValidationError) as exc_info:
        validate_row(row, _CACHE)
    assert exc_info.value.correction_type is CorrectionType.OTHER
    assert "folio_number" in exc_info.value.message


def test_plan_type_mismatch_between_feed_and_scheme_raises():
    """When the feed's translated plan_type disagrees with the scheme
    master, the row must not silently pass. This is the LinkedIn-comment
    case: historical files with 'DIVIDEND PAYOUT' wording against a
    master that's been migrated to 'idcw_reinvest'."""
    cache = PrewarmCache(
        schemes_by_code={"SCH1": {"id": 1, "amc_id": 10, "plan_type": "idcw_reinvest"}},
        accounts_by_pan={"ABCDE1234F": {"individual": {"id": "acc-1"}}},
    )
    row = dict(_VALID)
    row["plan_type_from_feed"] = "idcw_payout"
    with pytest.raises(ValidationError) as exc_info:
        validate_row(row, cache)
    assert exc_info.value.correction_type is CorrectionType.OTHER
    assert "plan_type mismatch" in exc_info.value.message


def test_plan_type_matching_feed_and_scheme_passes():
    cache = PrewarmCache(
        schemes_by_code={"SCH1": {"id": 1, "amc_id": 10, "plan_type": "idcw_payout"}},
        accounts_by_pan={"ABCDE1234F": {"individual": {"id": "acc-1"}}},
    )
    row = dict(_VALID)
    row["plan_type_from_feed"] = "idcw_payout"
    validate_row(row, cache)  # should not raise


def test_plan_type_silent_feed_does_not_block():
    """When the feed doesn't declare a plan_type (empty / None), we must
    not block the row — the scheme master remains the source of truth."""
    cache = PrewarmCache(
        schemes_by_code={"SCH1": {"id": 1, "amc_id": 10, "plan_type": "idcw_payout"}},
        accounts_by_pan={"ABCDE1234F": {"individual": {"id": "acc-1"}}},
    )
    row = dict(_VALID)
    row["plan_type_from_feed"] = None
    validate_row(row, cache)  # should not raise
