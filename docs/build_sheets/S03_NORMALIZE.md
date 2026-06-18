# S03 — Normalize — Build Sheet

> **Status: DESIGN. Doc-only.** Inherits X1–X6 (`README.md`). No contract/code change here.

## 1. Single responsibility
Turn S02's **source-shaped records** into **normalized records**: canonical field *names*
and normalized value *formats* (whitespace, dates → `YYYY-MM-DD`/`date`, amounts → exact
`Decimal` text, booleans/signs as written). One row in → one row out.
**NOT this stage:** deciding voucher type (S04), mapping ledger names (S05), building
double-entry or sign (S06), validating business rules (S07).

## 2. Position
`S02 records ─►` **S03 normalize** `─► normalized records ─► S04 classify`

## 3. Signatures (`s03_normalize/contracts.py`)
```python
def normalize(parsed: <ParsedRecordSet'>, profile: <SourceProfile>) -> NormalizedRecordSet: ...
```
- `NormalizedRecord(fields)` / `NormalizedRecordSet(source_system, records)` — same generic
  shape, but field **keys are now canonical** (e.g. `document_id`, `document_date`,
  `party_id`, `amount`, `line_item_id`, `quantity`, `rate`).

## 4. Decisions
- **D-S03.1 — field renaming is data, not code (X3).** A per-source **profile** maps source
  columns → canonical field names (Zoho: `total→amount`, `invoice_id→document_id`,
  `customer_id→party_id`, `qty→quantity`). Generic S03 logic applies the profile.
  *Rationale:* concentrates Zoho knowledge in a reviewable table; Busy ships its own profile,
  S03 code unchanged.
- **D-S03.2 — normalize format only, never accounting meaning.** S03 produces exact typed
  *values* (Decimal-clean amounts, ISO dates) but assigns no debit/credit, no voucher type,
  no ledger. Sign/magnitude split (§5.1) is S06's.
- **D-S03.3 — money stays `Decimal` text (X6); reject floats.** Reuse `core/money.py`.

## 5. Fail-loud
| # | Condition | Behavior |
|---|---|---|
| N1 | Unparseable date / amount in a field declared numeric/temporal by the profile | Fail loud (field + value). |
| N2 | Profile has no canonical name for a required source field | Fail loud (missing mapping). |
| N3 | Float or non-finite where money expected | Fail loud (X6). |
| N4 | Value normalizes ambiguously (e.g. locale-ambiguous date) | Fail loud — never guess. |

## 6. Source-agnostic note
Last stage where source column names appear (as profile *input*). Output keys are canonical,
so S04+ see source-neutral field names. Profile is data (X3).

## 7. Contract gap
A typed **`SourceProfile`** (field-name map + per-field type hints) is needed — it does not
exist in `contracts/`. Flag as a required contract addition (separate step). `NormalizedRecord`
generic shape is otherwise sufficient.

## 8. DoD + tests
- [ ] Pure; deterministic; imports only `contracts/`+`core/`; no `float` anywhere.
- [ ] T: Zoho profile renames keys to canonical; amounts become exact `Decimal` text.
- [ ] T-N1…N4 negatives each raise the shared-base typed error (X4).
- [ ] `make check` green.
