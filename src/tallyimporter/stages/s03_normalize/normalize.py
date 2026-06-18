"""S03 — Normalize: clean cell *values* (whitespace) and validate transaction amounts
parse to exact Decimal. Format-only; assigns no accounting meaning. Money stays Decimal
text (X6). Imports only ``contracts/`` and ``core/``.

(Header renaming to canonical names is deferred for this build; column names ride as
data and the source profile references the source column names directly. See
docs/build_sheets/S03_NORMALIZE.md.)
"""

from __future__ import annotations

from tallyimporter.contracts.errors import MoneyError, NormalizeError
from tallyimporter.contracts.source import (
    ArtifactRole,
    SourceDataset,
    SourceProfile,
    SourceTable,
)
from tallyimporter.core.money import parse_money


def _amount_columns(profile: SourceProfile) -> dict[ArtifactRole, str]:
    return {t.role: t.amount_column for t in profile.transactions}


def normalize(dataset: SourceDataset, profile: SourceProfile) -> SourceDataset:
    """Trim every cell; normalize transaction amount columns to canonical Decimal text."""
    amount_cols = _amount_columns(profile)
    out: list[SourceTable] = []
    for table in dataset.tables:
        amount_idx: int | None = None
        if table.role in amount_cols:
            col = amount_cols[table.role]
            if col not in table.headers:
                raise NormalizeError(
                    f"{table.role.value}: amount column {col!r} missing",
                    code="missing_amount_column",
                    detail={"role": table.role.value, "column": col},
                )
            amount_idx = table.headers.index(col)

        new_rows: list[tuple[str, ...]] = []
        for i, row in enumerate(table.rows, start=2):
            cells = [c.strip() for c in row]
            if amount_idx is not None:
                raw = cells[amount_idx]
                try:
                    cells[amount_idx] = str(parse_money(raw))
                except MoneyError as exc:
                    raise NormalizeError(
                        f"{table.role.value} row {i}: bad amount {raw!r}",
                        code="bad_amount",
                        detail={"role": table.role.value, "row": str(i), "value": raw},
                    ) from exc
            new_rows.append(tuple(cells))
        out.append(SourceTable(role=table.role, headers=table.headers, rows=tuple(new_rows)))
    return SourceDataset(source_system=dataset.source_system, tables=tuple(out))
