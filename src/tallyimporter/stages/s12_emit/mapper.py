"""Pure canonical → Tally mapper (§5.3).

Applies the verified sign convention (§2.2 rule 5):

- debit  → ``is_deemed_positive = True``,  signed amount is negative
- credit → ``is_deemed_positive = False``, signed amount is positive

Ordering from the input tuples is preserved. A voucher that does not net to zero
raises ``BalanceError`` (via ``TallyVoucher``'s zero-sum validator).
"""

from __future__ import annotations

from tallyimporter.contracts.canonical import CanonicalBatch, CanonicalVoucher
from tallyimporter.contracts.tally import (
    TallyImportEnvelope,
    TallyLedgerEntry,
    TallyVoucher,
)


def _map_voucher(voucher: CanonicalVoucher) -> TallyVoucher:
    entries = tuple(
        TallyLedgerEntry(
            ledger_name=entry.ledger_name,
            is_deemed_positive=entry.is_debit,
            amount=-entry.amount if entry.is_debit else entry.amount,
        )
        for entry in voucher.entries
    )
    return TallyVoucher(
        action="Create",
        vch_type=voucher.voucher_type,
        date=voucher.date,
        voucher_number=voucher.voucher_number,
        narration=voucher.narration,
        entries=entries,
    )


def canonical_to_tally(batch: CanonicalBatch) -> TallyImportEnvelope:
    """Map a canonical batch to a Tally import envelope. Pure; never mutates input."""
    return TallyImportEnvelope(
        company_name=batch.company_name,
        vouchers=tuple(_map_voucher(v) for v in batch.vouchers),
    )
