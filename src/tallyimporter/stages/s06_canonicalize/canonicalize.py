"""S06 — Canonicalize: assemble the source-agnostic CanonicalBatch from mapped
transactions. Builds balanced double-entry vouchers; resolves a negative source amount
to magnitude + swapped direction (§5.1). The canonical model enforces balance and
uniqueness at construction. Imports only ``contracts/`` and ``core/``.
"""

from __future__ import annotations

from datetime import date

from tallyimporter.contracts.canonical import (
    CanonicalBatch,
    CanonicalLedgerEntry,
    CanonicalVoucher,
)
from tallyimporter.contracts.source import MappedTxn


def _voucher(txn: MappedTxn, posting_date: date) -> CanonicalVoucher:
    debit, credit, magnitude = txn.debit_ledger, txn.credit_ledger, txn.amount
    if magnitude < 0:  # reversal: swap sides, take magnitude (§5.1 input adaptation)
        debit, credit = credit, debit
        magnitude = -magnitude
    return CanonicalVoucher(
        voucher_type=txn.voucher_type,
        date=posting_date,
        voucher_number=txn.voucher_number,
        narration=None,
        confidence=txn.confidence,
        party_ledger=txn.party_ledger,
        entries=(
            CanonicalLedgerEntry(ledger_name=debit, is_debit=True, amount=magnitude),
            CanonicalLedgerEntry(ledger_name=credit, is_debit=False, amount=magnitude),
        ),
    )


def canonicalize(
    txns: tuple[MappedTxn, ...], *, company_name: str, source_system: str, posting_date: date
) -> CanonicalBatch:
    """Build the canonical batch. ``posting_date`` is supplied because the Zoho sample
    export carries no per-document date; real exports would map a date column here."""
    vouchers = tuple(_voucher(t, posting_date) for t in txns)
    return CanonicalBatch(company_name=company_name, source_system=source_system, vouchers=vouchers)
