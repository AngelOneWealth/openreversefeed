from openreversefeed.core.models import Action, CorrectionType, Registrar, TransactionStatus


def test_action_values():
    assert Action.BUY.value == "buy"
    assert Action.SELL.value == "sell"
    assert Action.NO_EFFECT.value == "no_effect"


def test_status_values():
    assert {s.value for s in TransactionStatus} == {"pending", "successful", "reversed", "failed"}


def test_registrar_values():
    assert {r.value for r in Registrar} == {"cams", "kfintech"}


def test_correction_types():
    assert {c.value for c in CorrectionType} == {
        "duplicate_pan",
        "pan_not_found",
        "user_mismatch",
        "folio_mismatch",
        "scheme_not_found",
        "transfer_in_unmatched",
        "other",
    }
