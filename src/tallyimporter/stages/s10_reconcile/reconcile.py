"""S10 - Reconcile: flag vouchers already present in prior imports so re-runs are safe.

Matches on stable source identity (number, type, date), not Tally's auto-number (X5).
Reports; never mutates Tally or drops vouchers. Imports only ``contracts/``.
"""

from __future__ import annotations

from tallyimporter.contracts.canonical import CanonicalBatch
from tallyimporter.contracts.errors import ReconcileError
from tallyimporter.stages.s10_reconcile.contracts import (
    PriorImportState,
    ReconciliationResult,
)


def reconcile(batch: CanonicalBatch, *, prior: PriorImportState) -> ReconciliationResult:
    """Split the batch into matched (already imported) and unmatched voucher numbers."""
    prior_keys: set[tuple[str, str, str]] = set()
    for ref in prior.imported:
        key = (ref.voucher_number, ref.voucher_type, ref.date.isoformat())
        if key in prior_keys:
            raise ReconcileError(
                f"ambiguous prior import entry: {key}",
                code="ambiguous_prior",
                detail={"voucher": ref.voucher_number},
            )
        prior_keys.add(key)

    matched: list[str] = []
    unmatched: list[str] = []
    for v in batch.vouchers:
        key = (v.voucher_number, v.voucher_type, v.date.isoformat())
        (matched if key in prior_keys else unmatched).append(v.voucher_number)

    return ReconciliationResult(
        batch=batch,
        unmatched_voucher_numbers=tuple(unmatched),
        matched_voucher_numbers=tuple(matched),
    )
