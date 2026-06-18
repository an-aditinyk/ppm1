"""S12 emit — ledger masters.

Derive the "All Masters" ledger-creation envelope from a canonical batch: every distinct
ledger the batch references, each under its Tally parent group. Pure; deterministic
(first-seen order). The minimal LEDGER structure was confirmed sufficient by a real
TallyPrime round-trip (smoke_import/ROUNDTRIP_FINDINGS.md). Imports only ``contracts/``.
"""

from __future__ import annotations

from tallyimporter.contracts.canonical import CanonicalBatch
from tallyimporter.contracts.tally import TallyLedgerMaster, TallyMastersEnvelope


def masters_for_batch(
    batch: CanonicalBatch,
    *,
    group_of: tuple[tuple[str, str], ...] = (),
    default_group: str = "Sundry Debtors",
) -> TallyMastersEnvelope:
    """Build the masters envelope for every ledger ``batch`` references.

    ``group_of`` maps known control-account ledger names to their Tally parent group;
    any ledger not listed falls back to ``default_group``.
    """
    groups = dict(group_of)
    seen: list[str] = []
    for voucher in batch.vouchers:
        for entry in voucher.entries:
            if entry.ledger_name not in seen:
                seen.append(entry.ledger_name)
    ledgers = tuple(
        TallyLedgerMaster(name=name, parent=groups.get(name, default_group)) for name in seen
    )
    return TallyMastersEnvelope(company_name=batch.company_name, ledgers=ledgers)
