# S07 — Validate — Build Sheet

> **Status: DESIGN. Doc-only.** Inherits X1–X6 (`README.md`). No contract/code change here.

## 1. Single responsibility
Check a `CanonicalBatch` against **business rules** and emit a typed **`ValidationReport`**
of issues (error/warning). It **reports**; it does not mutate the batch or stop the pipeline
by itself.
**NOT this stage:** structural model invariants (enforced at construction in S06), enrichment
(S08), human gating (S11 consumes severities/confidence), emitting (S12).

## 2. Position
`S06 CanonicalBatch ─►` **S07 validate** `─► ValidationReport(batch, issues) ─► S08…`

## 3. Signatures (`s07_validate/contracts.py`)
```python
def validate(batch: CanonicalBatch, *, policy: <ValidationPolicy>) -> ValidationReport: ...
```
- `ValidationIssue(voucher_number, message, severity)` + `ValidationReport(batch, issues)`.
  Pure function; returns issues rather than raising, so callers can collect all problems.

## 4. Decisions
- **D-S07.1 — separate *report* from *enforcement*.** S07 returns issues; the orchestrator
  decides to block on any `error`. *Rationale:* deterministic, collect-all diagnostics beat
  fail-on-first for a human-facing importer.
- **D-S07.2 — rules in scope:** date within the **company financial year** (the §2.2 rule-3
  configurable hook — real reality: FY must include the posting date, as the smoke import
  showed), voucher-type and ledger names non-empty/known (§2.2 rule 9), per-voucher zero-sum
  re-check, batch voucher-number uniqueness (§2.2 rule 8), confidence ≥ policy floor (warn).
- **D-S07.3 — financial-year value is configuration, not hard-coded.** *Rationale:* the FY is
  per-company (we hit "date out of range" precisely because FY is company-specific).
- **D-S07.4 — structural invariants are NOT re-implemented here** — they're guaranteed by the
  frozen model. S07 covers cross-voucher/company rules the model can't see.

## 5. Fail-loud vs. report
- Genuine *input* faults (not a `CanonicalBatch`, corrupt policy) → fail loud (typed, X4).
- *Business* findings → `ValidationIssue`s, not exceptions. `error` severity = must-block.

## 6. Source-agnostic note
Spine (X1): operates only on canonical + Tally concepts; no source reference.

## 7. Contract gap
A typed **`ValidationPolicy`** (financial-year window, confidence floor, known-name sets) is
needed and absent from `contracts/`. Flag (separate step). `ValidationReport` shape is
sufficient.

## 8. DoD + tests
- [ ] Pure; deterministic; imports only `contracts/`+`core/`.
- [ ] T: a date outside the configured FY → one `error` issue (no exception).
- [ ] T: a low-confidence voucher → one `warning` issue.
- [ ] T: clean batch → empty issues.
- [ ] `make check` green.
