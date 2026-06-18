# S09 — Number — Build Sheet

> **Status: DESIGN. Doc-only.** Inherits X1–X6 (`README.md`). Scope shaped by **X5** (Tally is
> authoritative for numbering). No contract/code change here.

## 1. Single responsibility
Guarantee every voucher in the batch has a **unique** `voucher_number` so the import file is
valid (§2.2 rule 8) — using the source document id as that number.
**NOT this stage:** controlling Tally's stored number (Tally auto-numbers — X5), creating
ledgers, validation (S07).

## 2. Position
`S08 EnrichedBatch ─►` **S09 number** `─► NumberedBatch(batch) ─► S10…`

## 3. Signatures (`s09_number/contracts.py`)
```python
def assign_numbers(batch: CanonicalBatch, *, policy: <NumberPolicy>) -> NumberedBatch: ...
```
- `NumberedBatch(batch)`. In practice the canonical voucher already carries
  `voucher_number` (the source id); S09 **verifies/repairs uniqueness**, it rarely invents.

## 4. Decisions
- **D-S09.1 — let Tally auto-number; we only guarantee batch-uniqueness (X5).** Per
  `ROUNDTRIP_FINDINGS.md`, TallyPrime's predefined voucher types renumbered our `Ven…` ids to
  `19` on import — and we **accepted** that. So S09's job shrinks to: ensure no duplicate
  `VOUCHERNUMBER` in the file (Tally rejects whole files on duplicates); the stored number is
  Tally's. *Rationale:* recorded decision; fighting Tally's numbering buys nothing.
- **D-S09.2 — deterministic disambiguation.** If two source documents share an id, append a
  stable, deterministic suffix; never random, never order-dependent.
- **D-S09.3 — source-id traceability is explicitly not guaranteed downstream of Tally** (X5
  consequence); if ever needed, it's a reference-field feature (out of current scope).

## 5. Fail-loud
| # | Condition | Behavior |
|---|---|---|
| U1 | Duplicate `voucher_number` that policy can't deterministically disambiguate | Fail loud. |
| U2 | Empty `voucher_number` | Fail loud (§2.2 rule 8). |

## 6. Source-agnostic note
Spine (X1). The number is a string; its source origin is irrelevant to Tally.

## 7. Contract gap
None in shape. An optional `NumberPolicy` (disambiguation strategy) may be added; minor,
flag only.

## 8. DoD + tests
- [ ] Pure; deterministic; imports only `contracts/`+`core/`.
- [ ] T: already-unique numbers pass through unchanged.
- [ ] T: a forced duplicate → deterministic suffix (or U1 if undisambiguable).
- [ ] `make check` green.
