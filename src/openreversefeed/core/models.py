"""Canonical enums shared across the codebase."""
from __future__ import annotations

from enum import Enum


class Registrar(str, Enum):
    CAMS = "cams"
    KFINTECH = "kfintech"


class Action(str, Enum):
    BUY = "buy"
    SELL = "sell"
    NO_EFFECT = "no_effect"


class TransactionStatus(str, Enum):
    PENDING = "pending"
    SUCCESSFUL = "successful"
    REVERSED = "reversed"
    FAILED = "failed"


class CorrectionType(str, Enum):
    DUPLICATE_PAN = "duplicate_pan"
    PAN_NOT_FOUND = "pan_not_found"
    USER_MISMATCH = "user_mismatch"
    FOLIO_MISMATCH = "folio_mismatch"
    SCHEME_NOT_FOUND = "scheme_not_found"
    TRANSFER_IN_UNMATCHED = "transfer_in_unmatched"
    OTHER = "other"
