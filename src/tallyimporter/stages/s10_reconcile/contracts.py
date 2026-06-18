"""S10 reconcile — boundary contracts.

Reconciles the batch against existing Tally data / prior imports.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from tallyimporter.contracts.canonical import CanonicalBatch

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class ReconciliationResult(BaseModel):
    model_config = _FROZEN

    batch: CanonicalBatch
    unmatched_voucher_numbers: tuple[str, ...]
