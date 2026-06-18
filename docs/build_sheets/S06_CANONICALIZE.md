# S06 — Canonicalize — Build Sheet

> **Status: DESIGN. Doc-only.** Inherits X1–X6 (`README.md`). **This is the source-agnostic
> seam.** No contract/code change here.

## 1. Single responsibility
Assemble the **`CanonicalBatch`** from mapped/classified/normalized records: build balanced
double-entry `CanonicalVoucher`s with `CanonicalLedgerEntry`s (positive magnitude +
`is_debit`, §5.1), carrying `confidence`.
**NOT this stage:** Tally XML/sign (S12), business-rule reporting (S07), enrichment (S08),
numbering policy (S09). It *constructs* the canonical model; it does not *emit* anything.

## 2. Position
`S05 mapped records ─►` **S06 canonicalize** `─► CanonicalBatch ─► S07 validate`
Below this line, **no source concept may appear** (X1).

## 3. Signatures (`s06_canonicalize/contracts.py` → `contracts/canonical.py`)
```python
def canonicalize(records: <MappedRecordSet>, *, company_name: str, source_system: str)
    -> CanonicalizeResult: ...     # .batch: CanonicalBatch
```
- Reuses the **frozen** `CanonicalBatch/Voucher/LedgerEntry` — model invariants (amount>0,
  per-voucher balance, unique voucher numbers, confidence∈[0,1]) are enforced at construction.

## 4. Decisions
- **D-S06.1 — double-entry construction lives here.** Turning one source document into
  balanced entries (e.g. sales invoice → Dr party / Cr Sales [+ Cr GST]; customer receipt →
  Dr Bank / Cr AR) is canonicalization. *Rationale:* it's the act of expressing source data
  as source-neutral accounting; it needs mapped ledgers (S05) and types (S04), and produces
  the seam model.
- **D-S06.2 — magnitude+`is_debit`, never signed (§5.1, X6).** Reversals/negatives from the
  source are resolved to magnitude + direction *here* (the adapter-side input adaptation the
  smoke harness modeled); the canonical model rejects raw negatives loudly.
- **D-S06.3 — fail loud on imbalance.** A document that can't form a zero-net voucher raises;
  it is never emitted half-built. *Rationale:* the model already enforces debit==credit.
- **D-S06.4 — `source_system` is retained as a provenance tag only** (already a
  `CanonicalBatch` field) — it labels origin but no spine stage branches on it (X1).

## 5. Fail-loud
| # | Condition | Behavior |
|---|---|---|
| K1 | Entries don't balance (debit total ≠ credit total) | Fail loud (model raises). |
| K2 | Zero/negative magnitude, or `float` amount | Fail loud (§5.1/X6). |
| K3 | Duplicate voucher numbers within the batch | Fail loud (model raises). |
| K4 | Missing required field (ledger name, date, type) | Fail loud. |

## 6. Source-agnostic note
The **output is the canonical model** — the definition of source-agnostic. The only permitted
trace of origin is the opaque `source_system` provenance string (D-S06.4).

## 7. Contract gap
Input type (`MappedRecordSet`, S05 §7) must be defined first. Canonical *output* is the
existing frozen spine — no change. GST line splits / bill references are **not** added here;
they're S08 enrichment (canonical extension flagged in `README.md` §5).

## 8. DoD + tests
- [ ] Pure; deterministic; imports only `contracts/`+`core/`.
- [ ] T: a sales invoice and a payment each canonicalize to a balanced 2-line voucher.
- [ ] T: a source negative resolves to magnitude+direction (no raw negative reaches canonical).
- [ ] T-K1…K4 negatives raise (model or shared-base typed error, X4).
- [ ] `make check` green.
