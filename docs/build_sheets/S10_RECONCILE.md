# S10 — Reconcile — Build Sheet

> **Status: DESIGN — Phase ≥2.** Doc-only. Inherits X1–X6 (`README.md`). Needs prior-state
> carrier (§7). No contract/code change here.

## 1. Single responsibility
Compare the batch against **what's already in Tally / prior imports** and mark vouchers that
would **duplicate** existing data, so re-imports are safe (the importer is not idempotent —
`SMOKE_IMPORT.md`).
**NOT this stage:** numbering (S09), human approval (S11), emitting (S12).

## 2. Position
`S09 NumberedBatch ─►` **S10 reconcile** `─► ReconciliationResult(batch, unmatched…) ─► S11…`

## 3. Signatures (`s10_reconcile/contracts.py`)
```python
def reconcile(batch: CanonicalBatch, *, prior: <PriorImportState>) -> ReconciliationResult: ...
```
- `ReconciliationResult(batch, unmatched_voucher_numbers)` — vouchers with no prior match are
  "unmatched" (new, safe to import); matched ones are flagged to skip.

## 4. Decisions
- **D-S10.1 — reconcile against an explicit prior-state input, never a live Tally query in
  core.** Any Tally read is an imperative-shell concern; the pure core takes a
  `PriorImportState` value. *Rationale:* pure-core/imperative-shell + determinism.
- **D-S10.2 — match on a stable identity** (source document id + type + date + amount), not on
  Tally's auto-number (which we don't control — X5). *Rationale:* Tally renumbers, so its
  number is not a reliable cross-run key.
- **D-S10.3 — report, don't delete.** S10 flags duplicates; it never mutates Tally or drops
  vouchers silently. *Rationale:* fail-loud/immutability; destructive dedupe is out of scope.

## 5. Fail-loud
| # | Condition | Behavior |
|---|---|---|
| R1 | Ambiguous match (one source voucher matches several priors) | Fail loud or flag for review, per policy. |
| R2 | Corrupt/unreadable prior-state input | Fail loud. |

## 6. Source-agnostic note
Spine (X1). Identity is built from canonical/Tally fields only.

## 7. Contract gap
A typed **`PriorImportState`** (the set of already-imported voucher identities, likely sourced
from `TallyImportResult` + a local ledger) does not exist in `contracts/`. Flag as required
addition (separate step). `ReconciliationResult` shape is sufficient.

## 8. DoD + tests (when unblocked)
- [ ] Pure core; deterministic; imports only `contracts/`+`core/`.
- [ ] T: a batch re-run against its own prior state → all matched (none unmatched).
- [ ] T: a fresh voucher → unmatched. T-R1 ambiguous → fail/flag.
- [ ] `make check` green.
