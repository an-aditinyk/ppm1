"""S10 reconcile - boundary contracts."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from tallyimporter.contracts.canonical import CanonicalBatch

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class ImportedVoucherRef(BaseModel):
    """A stable identity for a voucher we already emitted/imported. Built from source
    fields, never Tally's auto-number (X5)."""

    model_config = _FROZEN

    voucher_number: str = Field(min_length=1)
    voucher_type: str = Field(min_length=1)
    date: date
    amount: str = Field(min_length=1)  # gross magnitude, rendered, as a tiebreaker


class PriorImportState(BaseModel):
    """What has already been imported (our bookkeeping; the §2.3 response only returns
    counts). Loaded/saved by the imperative shell; the S10 core takes it as a value."""

    model_config = _FROZEN

    imported: tuple[ImportedVoucherRef, ...] = ()


class ReconciliationResult(BaseModel):
    model_config = _FROZEN

    batch: CanonicalBatch
    unmatched_voucher_numbers: tuple[str, ...]
    matched_voucher_numbers: tuple[str, ...] = ()
