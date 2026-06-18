"""S09 — Number: guarantee unique voucher numbers within the batch (§2.2 rule 8).

Tally is authoritative for the *stored* number (X5); S09 only ensures the import file
is duplicate-free. The canonical model already enforces uniqueness at construction, so
this is a verification stage. Imports only ``contracts/`` and ``core/``.
"""

from __future__ import annotations

from tallyimporter.contracts.canonical import CanonicalBatch
from tallyimporter.contracts.errors import StageError
from tallyimporter.stages.s09_number.contracts import NumberedBatch


class _NumberError(StageError):
    stage = "s09_number"


def assign_numbers(batch: CanonicalBatch) -> NumberedBatch:
    """Verify batch voucher-number uniqueness and emptiness; fail loud otherwise."""
    seen: set[str] = set()
    for v in batch.vouchers:
        if not v.voucher_number:
            raise _NumberError("empty voucher number", code="empty_number")
        if v.voucher_number in seen:
            raise _NumberError(
                f"duplicate voucher number {v.voucher_number!r}",
                code="duplicate_number",
                detail={"voucher": v.voucher_number},
            )
        seen.add(v.voucher_number)
    return NumberedBatch(batch=batch)
