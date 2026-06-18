"""Pure canonical → Tally mapper (§5.3).

Applies the verified sign convention (§2.2 rule 5):

- debit  → ``is_deemed_positive = True``,  signed amount is negative
- credit → ``is_deemed_positive = False``, signed amount is positive

Ordering from the input tuples is preserved. A voucher that does not net to zero
raises ``BalanceError`` (via ``TallyVoucher``'s zero-sum validator).
"""

from __future__ import annotations

from tallyimporter.contracts.canonical import (
    CanonicalBatch,
    CanonicalLedgerEntry,
    CanonicalVoucher,
)
from tallyimporter.contracts.tally import (
    TallyBillAllocation,
    TallyImportEnvelope,
    TallyLedgerEntry,
    TallyVoucher,
)

# Bill-kind → Tally BILLTYPE (single mapping point).
_BILL_TYPE: dict[str, str] = {
    "new": "New Ref",
    "against": "Agst Ref",
    "advance": "Advance",
    "on_account": "On Account",
}


def _map_entry(entry: CanonicalLedgerEntry) -> TallyLedgerEntry:
    signed = -entry.amount if entry.is_debit else entry.amount
    allocations = tuple(
        TallyBillAllocation(
            name=b.reference,
            bill_type=_BILL_TYPE[b.kind],
            amount=-b.amount if entry.is_debit else b.amount,
        )
        for b in entry.bill_allocations
    )
    return TallyLedgerEntry(
        ledger_name=entry.ledger_name,
        is_deemed_positive=entry.is_debit,
        amount=signed,
        bill_allocations=allocations,
    )


def _map_voucher(voucher: CanonicalVoucher) -> TallyVoucher:
    return TallyVoucher(
        action="Create",
        vch_type=voucher.voucher_type,
        date=voucher.date,
        voucher_number=voucher.voucher_number,
        narration=voucher.narration,
        party_ledger=voucher.party_ledger,
        entries=tuple(_map_entry(e) for e in voucher.entries),
    )


def canonical_to_tally(batch: CanonicalBatch) -> TallyImportEnvelope:
    """Map a canonical batch to a Tally import envelope. Pure; never mutates input."""
    return TallyImportEnvelope(
        company_name=batch.company_name,
        vouchers=tuple(_map_voucher(v) for v in batch.vouchers),
    )
