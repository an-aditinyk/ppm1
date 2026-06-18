"""S02 — Parse: role-tagged bytes → structured tables, with record-level validation.

Owns referential-integrity / join validation (relocated from S01, D2), malformed-row
and duplicate-id checks. Keys stay source-shaped here (canonical naming is S03).
Imports only ``contracts/`` and ``core/``.
"""

from __future__ import annotations

import csv
import io

from tallyimporter.contracts.errors import ParseError
from tallyimporter.contracts.source import (
    ArtifactRole,
    IngestedArchive,
    SourceDataset,
    SourceProfile,
    SourceTable,
)


def _read_csv(name: str, text: str) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    reader = csv.reader(io.StringIO(text))
    rows = [tuple(r) for r in reader]
    if not rows:
        raise ParseError(
            f"artifact {name!r} has no header", code="no_header", detail={"role": name}
        )
    header = rows[0]
    if not header or any(h == "" for h in header):
        raise ParseError(f"artifact {name!r} has an empty header cell", code="bad_header")
    body: list[tuple[str, ...]] = []
    for i, row in enumerate(rows[1:], start=2):
        if len(row) != len(header):
            raise ParseError(
                f"artifact {name!r} row {i} has {len(row)} cols, expected {len(header)}",
                code="ragged_row",
                detail={"role": name, "row": str(i)},
            )
        body.append(row)
    return header, tuple(body)


def _col(headers: tuple[str, ...], name: str, role: ArtifactRole) -> int:
    try:
        return headers.index(name)
    except ValueError as exc:
        raise ParseError(
            f"{role.value}: expected column {name!r} not found",
            code="missing_column",
            detail={"role": role.value, "column": name},
        ) from exc


def parse(archive: IngestedArchive, profile: SourceProfile) -> SourceDataset:
    """Parse each artifact's CSV into a table; validate structure, ids, and joins."""
    tables: dict[ArtifactRole, SourceTable] = {}
    for art in archive.artifacts:
        text = art.content.decode("utf-8-sig")  # BOM-tolerant; S01 already gated encoding
        headers, rows = _read_csv(art.role.value, text)
        tables[art.role] = SourceTable(role=art.role, headers=headers, rows=rows)

    # Duplicate primary id within party + transaction artifacts.
    id_cols: dict[ArtifactRole, str] = {p.role: p.id_column for p in profile.parties}
    for t in profile.transactions:
        id_cols[t.role] = t.id_column
    for role, id_col in id_cols.items():
        table = tables.get(role)
        if table is None:
            continue
        idx = _col(table.headers, id_col, role)
        seen: set[str] = set()
        for row in table.rows:
            key = row[idx]
            if key in seen:
                raise ParseError(
                    f"{role.value}: duplicate id {key!r}",
                    code="duplicate_id",
                    detail={"role": role.value, "id": key},
                )
            seen.add(key)

    # Referential integrity: every transaction party id resolves to a party row (D-S02.1).
    for t in profile.transactions:
        if t.party_column is None or t.party_role is None:
            continue
        txn = tables.get(t.role)
        if txn is None:
            continue
        party = tables.get(t.party_role)
        if party is None:
            raise ParseError(
                f"{t.role.value}: party table {t.party_role.value} absent for join",
                code="missing_party_table",
                detail={"role": t.role.value, "party_role": t.party_role.value},
            )
        party_id_col = next(p.id_column for p in profile.parties if p.role == t.party_role)
        valid = {row[_col(party.headers, party_id_col, t.party_role)] for row in party.rows}
        pcol = _col(txn.headers, t.party_column, t.role)
        for row in txn.rows:
            if row[pcol] not in valid:
                raise ParseError(
                    f"{t.role.value}: party id {row[pcol]!r} has no {t.party_role.value} row",
                    code="unjoinable_id",
                    detail={"role": t.role.value, "party_id": row[pcol]},
                )

    ordered = tuple(tables[r] for r in sorted(tables, key=lambda x: x.value))
    return SourceDataset(source_system=archive.source_system, tables=ordered)
