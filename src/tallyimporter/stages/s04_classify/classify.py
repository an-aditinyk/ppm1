"""S04 — Classify: turn transaction rows into classified transactions with a Tally
voucher type and explicit confidence. Role-driven (D-S04.1). Imports only
``contracts/`` and ``core/``.
"""

from __future__ import annotations

from decimal import Decimal

from tallyimporter.contracts.errors import ClassifyError, MoneyError
from tallyimporter.contracts.source import (
    ClassifiedTxn,
    SourceDataset,
    SourceProfile,
    SourceTable,
)
from tallyimporter.core.money import parse_money


def _index(table: SourceTable, column: str) -> int:
    try:
        return table.headers.index(column)
    except ValueError as exc:
        raise ClassifyError(
            f"{table.role.value}: column {column!r} not found",
            code="missing_column",
            detail={"role": table.role.value, "column": column},
        ) from exc


def classify(dataset: SourceDataset, profile: SourceProfile) -> tuple[ClassifiedTxn, ...]:
    """Classify every transaction row per its template (role → voucher type)."""
    by_role = {t.role: t for t in dataset.tables}
    out: list[ClassifiedTxn] = []
    for tpl in profile.transactions:
        table = by_role.get(tpl.role)
        if table is None:
            continue  # optional artifact absent
        id_idx = _index(table, tpl.id_column)
        amt_idx = _index(table, tpl.amount_column)
        party_idx = _index(table, tpl.party_column) if tpl.party_column else None
        for i, row in enumerate(table.rows, start=2):
            number = row[id_idx]
            if not number:
                raise ClassifyError(
                    f"{tpl.role.value} row {i}: empty document id",
                    code="empty_id",
                    detail={"role": tpl.role.value, "row": str(i)},
                )
            try:
                amount: Decimal = parse_money(row[amt_idx])
            except MoneyError as exc:
                raise ClassifyError(
                    f"{tpl.role.value} row {i}: bad amount {row[amt_idx]!r}",
                    code="bad_amount",
                    detail={"role": tpl.role.value, "row": str(i)},
                ) from exc
            out.append(
                ClassifiedTxn(
                    role=tpl.role,
                    voucher_type=tpl.voucher_type,
                    confidence=tpl.confidence,
                    voucher_number=number,
                    amount=amount,
                    party_id=row[party_idx] if party_idx is not None else None,
                    debit_account=tpl.debit_account,
                    credit_account=tpl.credit_account,
                )
            )
    if not out:
        raise ClassifyError("no transactions classified", code="empty")
    return tuple(out)
