# S02 — Parse — Build Sheet

> **Status: DESIGN. Doc-only.** Inherits cross-cutting decisions X1–X6 (`README.md`).
> Flags a contract gap (§7). No contract/code change here.

## 1. Single responsibility
Turn S01's **role-tagged raw bytes** into **structured, source-shaped records** (rows as
ordered key/value fields), per artifact role — and validate everything that needs
record-level understanding.
**NOT this stage:** renaming fields to canonical names (S03), interpreting which column is
an amount/date (S03), classifying voucher type (S04), mapping ledgers (S05).

## 2. Position
`S01 role-tagged bytes ─►` **S02 parse** `─► structured per-role records ─► S03 normalize`

## 3. Signatures (reference stubs: `s02_parse/contracts.py`)
```python
def parse(source: <S01 IngestedArchive>) -> <ParsedRecordSet'>: ...   # pure
```
- Output today: `ParsedRecordSet(source_system, records: tuple[SourceRecord, ...])`,
  `SourceRecord(fields: tuple[tuple[str,str],...])` — generic ordered key/value rows
  (X2-compliant: column names are *data keys*, not contract fields).
- CSV parsing itself is **generic** (any CSV) — the source-structural knowledge S02 needs
  is minimal; per X3 it dispatches on `source_system` only if a source isn't plain CSV.

## 4. Decisions
- **D-S02.1 — S02 owns referential-integrity (relocated from S01, per S01 D2).** It parses
  id columns and validates the **real Zoho join keys** recorded in `S01_INGEST.md` §5
  (`Sales_Invoices.customer_id→Contacts.contact_id`, `Sales_Invoice_Items.invoice_id→
  Sales_Invoices.invoice_id`, `…item_id→Items.item_id`, `Bills/Bill_Items`,
  `Vendor_Payments→Vendors`). *Rationale:* a join needs records + knowledge that two
  columns join — parse work by definition.
- **D-S02.2 — S02 also owns the record-level checks moved off S01:** malformed/ragged rows,
  duplicate primary IDs, header-only/empty-data. *Rationale:* same "needs parsed rows" test.
- **D-S02.3 — keys stay source-shaped here.** S02 does not canonicalize field names; that's
  S03 (X1/X2). Output keys are Zoho headers, carried opaquely.

## 5. Fail-loud (record level)
| # | Condition | Behavior |
|---|---|---|
| P1 | Malformed CSV: ragged row / wrong column count / missing header | Fail loud (artifact + row). |
| P2 | Duplicate primary id within an artifact | Fail loud (id). |
| P3 | Header present but zero data rows in a **required** artifact | Fail loud. |
| P4 | Unjoinable id (join key with no target) | Fail loud, naming the dangling ref. |
| P5 | A declared role's bytes aren't the expected shape (e.g. not CSV) | Fail loud. |

## 6. Source-agnostic note
Adapter region (X1). The OUTPUT type is generic (X2); Zoho column names live only inside
the `fields` data. Downstream must not branch on the role string for anything but routing.

## 7. Contract gap (separate reviewed step — NOT done here)
`ParsedRecordSet` **lacks the artifact role** and row provenance — records from invoices vs
payments are indistinguishable, and P-errors can't cite a row. Reshape needed: records
grouped/tagged by **role** + a row index/source-line for diagnostics + a place to surface
the referential-integrity outcome. Flag; do not modify `contracts/`.

## 8. DoD + tests
- [ ] Pure `parse`; imports only `contracts/`+`core/`; deterministic (stable row order).
- [ ] T: real Zoho sample → records grouped by role; counts match per artifact.
- [ ] T-P1…P5 negatives each raise the shared-base typed error (X4).
- [ ] T: join validation passes on the real sample; a doctored dangling `customer_id` → P4.
- [ ] `make check` green.
