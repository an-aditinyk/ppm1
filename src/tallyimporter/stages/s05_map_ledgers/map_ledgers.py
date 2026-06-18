"""S05 — Map ledgers: resolve every account reference to a concrete Tally ledger name
through a single mapping point. Resolves the PARTY sentinel via the party tables and
applies ledger overrides. Unmapped names fail loud (D-S05.2). Imports only
``contracts/`` and ``core/``.
"""

from __future__ import annotations

from tallyimporter.contracts.errors import MapError
from tallyimporter.contracts.source import (
    PARTY_SENTINEL,
    ClassifiedTxn,
    MappedTxn,
    SourceDataset,
    SourceProfile,
)


def _party_name_index(dataset: SourceDataset, profile: SourceProfile) -> dict[str, str]:
    """Build {party_id: party_name} across all party tables present."""
    index: dict[str, str] = {}
    by_role = {t.role: t for t in dataset.tables}
    for party in profile.parties:
        table = by_role.get(party.role)
        if table is None:
            continue
        try:
            id_i = table.headers.index(party.id_column)
            name_i = table.headers.index(party.name_column)
        except ValueError as exc:
            raise MapError(
                f"{party.role.value}: id/name column missing",
                code="missing_party_column",
                detail={"role": party.role.value},
            ) from exc
        for row in table.rows:
            index[row[id_i]] = row[name_i]
    return index


def map_ledgers(
    txns: tuple[ClassifiedTxn, ...], dataset: SourceDataset, profile: SourceProfile
) -> tuple[MappedTxn, ...]:
    """Resolve debit/credit accounts to concrete Tally ledger names."""
    overrides = dict(profile.ledger_overrides)
    parties = _party_name_index(dataset, profile)

    def resolve(account: str, txn: ClassifiedTxn) -> str:
        if account == PARTY_SENTINEL:
            if txn.party_id is None:
                raise MapError(
                    f"{txn.role.value} {txn.voucher_number}: party required but absent",
                    code="missing_party",
                    detail={"voucher": txn.voucher_number},
                )
            name = parties.get(txn.party_id)
            if name is None:
                raise MapError(
                    f"party id {txn.party_id!r} not found in party tables",
                    code="unmapped_party",
                    detail={"party_id": txn.party_id},
                )
            account = name
        resolved = overrides.get(account, account)
        if not resolved.strip():
            raise MapError(
                f"account {account!r} maps to an empty ledger name",
                code="empty_ledger",
                detail={"account": account},
            )
        return resolved

    out: list[MappedTxn] = []
    for txn in txns:
        out.append(
            MappedTxn(
                voucher_type=txn.voucher_type,
                confidence=txn.confidence,
                voucher_number=txn.voucher_number,
                amount=txn.amount,
                debit_ledger=resolve(txn.debit_account, txn),
                credit_ledger=resolve(txn.credit_account, txn),
            )
        )
    return tuple(out)
