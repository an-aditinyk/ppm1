# S08 — Enrich — Build Sheet

> **Status: DESIGN — Phase ≥2.** Doc-only. Inherits X1–X6 (`README.md`). Requires a canonical
> model extension (§7) — separate reviewed step. No contract/code change here.

## 1. Single responsibility
Attach **derived accounting detail** the source didn't carry explicitly but Tally needs for
correct posting — **bill allocations**, **GST breakdown**, **party-ledger designation** — and
refine **confidence**. Enrichment **adds**; it never changes the balanced entries' net.
**NOT this stage:** building the base voucher (S06), emitting XML (S12), validation (S07).

## 2. Position
`S07-validated CanonicalBatch ─►` **S08 enrich** `─► EnrichedBatch(batch) ─► S09…`

## 3. Signatures (`s08_enrich/contracts.py`)
```python
def enrich(batch: CanonicalBatch, *, policy: <EnrichPolicy>) -> EnrichedBatch: ...
```
- `EnrichedBatch(batch)` today wraps a `CanonicalBatch` with **no place to put** allocations
  or GST — see §7.

## 4. Decisions
- **D-S08.1 — grounded by the round-trip, not invented.** TallyPrime showed customer/vendor
  ledgers default to `ISBILLWISEON=Yes` and derived `PARTYLEDGERNAME`. So posting bills/
  receipts against open items **will** need `BILLALLOCATIONS`. S08 is where that detail is
  computed. *Rationale:* real Tally behavior (`ROUNDTRIP_FINDINGS.md`), not speculation.
- **D-S08.2 — enrichment is additive and balance-preserving.** GST splits expand a line into
  sub-amounts that still net to zero; bill refs annotate without changing totals.
- **D-S08.3 — defer until the canonical model can carry it.** Phase 1's canonical model has no
  allocation/GST fields by design. S08 stays unbuilt until that extension is reviewed (§7).

## 5. Fail-loud
| # | Condition | Behavior |
|---|---|---|
| E1 | Enrichment would change a voucher's net (break zero-sum) | Fail loud. |
| E2 | Required allocation data missing for a bill-wise ledger | Fail loud or warn, per policy. |
| E3 | GST split inconsistent with line total | Fail loud. |

## 6. Source-agnostic note
Spine (X1). Bill/GST concepts are **accounting/Tally** concepts, not Zoho — named after
reality (the source-agnostic discipline generalized).

## 7. Contract gap (REQUIRED extension — separate step)
The **canonical model must gain** optional, immutable carriers for: bill allocations
(reference, amount), GST detail (rate, taxable value, tax amounts), and explicit party-ledger
designation. This is the `README.md` §5 item #4. Until reviewed and frozen, S08 cannot be
implemented. Do **not** modify `contracts/`.

## 8. DoD + tests (when unblocked)
- [ ] Pure; deterministic; additive; imports only `contracts/`+`core/`.
- [ ] T: a bill-wise receipt gains a balance-preserving bill allocation.
- [ ] T-E1: an enrichment that breaks zero-sum → fail loud.
- [ ] `make check` green.
