"""S08 - Enrich: attach bill-wise allocations to party ledger entries.

Additive and balance-preserving (it never changes a voucher's net): for bill-wise
voucher types that name a party ledger, the party entry gains a single "New Ref"
allocation equal to the entry amount, referenced by the voucher number. Grounded in the
round-trip (party ledgers default to ISBILLWISEON=Yes). Imports only ``contracts/``.
"""

from __future__ import annotations

from pydantic import ValidationError as PydValidationError

from tallyimporter.contracts.canonical import (
    BillAllocation,
    CanonicalBatch,
    CanonicalLedgerEntry,
    CanonicalVoucher,
)
from tallyimporter.contracts.errors import EnrichError
from tallyimporter.stages.s08_enrich.contracts import EnrichedBatch

_DEFAULT_BILL_WISE: tuple[str, ...] = ("Sales",)


def _with_bill(entry: CanonicalLedgerEntry, reference: str) -> CanonicalLedgerEntry:
    alloc = BillAllocation(reference=reference, kind="new", amount=entry.amount)
    return CanonicalLedgerEntry(
        ledger_name=entry.ledger_name,
        is_debit=entry.is_debit,
        amount=entry.amount,
        bill_allocations=(alloc,),
    )


def enrich(
    batch: CanonicalBatch, *, bill_wise_types: tuple[str, ...] = _DEFAULT_BILL_WISE
) -> EnrichedBatch:
    """Return the batch with bill-wise allocations added to party entries."""
    vouchers: list[CanonicalVoucher] = []
    for v in batch.vouchers:
        if v.voucher_type in bill_wise_types and v.party_ledger is not None:
            entries = tuple(
                _with_bill(e, v.voucher_number)
                if e.ledger_name == v.party_ledger and not e.bill_allocations
                else e
                for e in v.entries
            )
            try:
                v = CanonicalVoucher(
                    voucher_type=v.voucher_type,
                    date=v.date,
                    voucher_number=v.voucher_number,
                    narration=v.narration,
                    confidence=v.confidence,
                    party_ledger=v.party_ledger,
                    entries=entries,
                )
            except PydValidationError as exc:
                raise EnrichError(
                    f"enrichment of voucher {v.voucher_number} is invalid",
                    code="invalid",
                    detail={"voucher": v.voucher_number},
                ) from exc
        vouchers.append(v)
    return EnrichedBatch(
        batch=CanonicalBatch(
            company_name=batch.company_name,
            source_system=batch.source_system,
            vouchers=tuple(vouchers),
        )
    )
