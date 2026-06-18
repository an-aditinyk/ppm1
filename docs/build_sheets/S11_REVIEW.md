# S11 — Review — Build Sheet

> **Status: DESIGN — Phase ≥2 (human loop).** Doc-only. Inherits X1–X6 (`README.md`). No
> contract/code change here.

## 1. Single responsibility
Gate **low-confidence** (and S07-flagged) vouchers for **human approval** before they reach
emit: produce a review queue, accept review decisions, and apply them.
**NOT this stage:** computing confidence (S04), validation (S07), emitting (S12).

## 2. Position
`S10 ReconciliationResult ─►` **S11 review** `─► approved subset ─► S12 emit`
(pending vouchers are withheld until decided)

## 3. Signatures (`s11_review/contracts.py`)
```python
def build_queue(batch: CanonicalBatch, report: ValidationReport, *, policy: <ReviewPolicy>)
    -> ReviewQueue: ...                                   # pure: who needs review
def apply_decisions(queue: ReviewQueue, decisions: tuple[ReviewDecision, ...])
    -> CanonicalBatch: ...                                # pure: approved-only batch
```
- `ReviewQueue(batch, pending_voucher_numbers)` + `ReviewDecision(voucher_number, approved)`.

## 4. Decisions
- **D-S11.1 — threshold is policy, gating is deterministic.** A voucher is pending iff
  `confidence < floor` or it carries an S07 `error`/flagged `warning`. *Rationale:* explicit
  confidence is an invariant; the floor is per-deployment config.
- **D-S11.2 — pure core; the human interaction is the imperative shell.** Core functions take
  decisions as values and return an approved batch; no UI/IO in core. *Rationale:*
  pure-core/imperative-shell + deterministic, testable gating.
- **D-S11.3 — nothing auto-approves.** A pending voucher without an explicit `approved=True`
  decision is **withheld**, not emitted. *Rationale:* fail-safe; silence ≠ consent.

## 5. Fail-loud
| # | Condition | Behavior |
|---|---|---|
| W1 | A decision references a voucher not in the queue | Fail loud. |
| W2 | A pending voucher has no decision at apply time | Withhold (not an error) — but emit a clear record. |
| W3 | Conflicting decisions for one voucher | Fail loud. |

## 6. Source-agnostic note
Spine (X1). Operates on canonical vouchers + confidence; no source concept.

## 7. Contract gap
A typed **`ReviewPolicy`** (confidence floor, which severities gate) is needed; absent from
`contracts/`. Flag (separate step). Queue/decision shapes are sufficient.

## 8. DoD + tests (when unblocked)
- [ ] Pure core; deterministic; imports only `contracts/`+`core/`.
- [ ] T: below-floor voucher → queued; approve → included; withhold → excluded.
- [ ] T-W1 unknown voucher decision → fail loud. T-W3 conflict → fail loud.
- [ ] `make check` green.
