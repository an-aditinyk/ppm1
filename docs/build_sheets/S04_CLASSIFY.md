# S04 — Classify — Build Sheet

> **Status: DESIGN. Doc-only.** Inherits X1–X6 (`README.md`). No contract/code change here.

## 1. Single responsibility
Decide the **Tally voucher type** for each normalized document and attach an **explicit
confidence** (0.0–1.0). One document → one classification.
**NOT this stage:** mapping ledger names (S05), building entries/sign (S06), thresholding
for human review (S11 consumes the confidence S04 produces).

## 2. Position
`S03 normalized records ─►` **S04 classify** `─► classified records (+confidence) ─► S05`

## 3. Signatures (`s04_classify/contracts.py`)
```python
def classify(records: NormalizedRecordSet, profile: <SourceProfile>) -> ClassifiedRecordSet: ...
```
- `ClassifiedRecord(voucher_type, fields, confidence)` — already carries the confidence
  invariant. `voucher_type` is a **Tally** voucher-type name (predefined: `Sales`,
  `Receipt`, `Payment`, …) — the §2.2 rule-9 name target.

## 4. Decisions
- **D-S04.1 — classify primarily by artifact role (deterministic, confidence 1.0).** The
  role already names the document kind (sales invoice → `Sales`; customer receipt →
  `Receipt`; supplier payment → `Payment`). *Rationale:* role is a reliable signal; this is
  the path we validated end-to-end against TallyPrime.
- **D-S04.2 — ambiguous documents get rules + sub-1.0 confidence, never a silent guess.**
  Journals/bank transactions (no inherent posting type) classify via profile rules; if no
  rule fires confidently, emit the best candidate with low confidence (→ S11 review) or fail
  loud if unclassifiable. *Rationale:* explicit confidence is an invariant; review is the
  safety net, not silent defaulting.
- **D-S04.3 — voucher-type vocabulary is data (X3).** Role→type and rule tables live in the
  source profile; S04 logic is generic. Only predefined Tally types are emitted unless a
  voucher-type master is planned (flagged in S12).

## 5. Fail-loud
| # | Condition | Behavior |
|---|---|---|
| C1 | Document matches no rule and no role default | Fail loud (or route to review per policy) — never default silently. |
| C2 | Confidence outside [0,1] | Fail loud (model already enforces). |
| C3 | Resolved `voucher_type` empty / not a known Tally type name | Fail loud (§2.2 rule 9). |

## 6. Source-agnostic note
Spine-facing: output `voucher_type` is a Tally concept, `confidence` is neutral. Source rules
are profile data (X3); the contract is source-neutral (X2).

## 7. Contract gap
None in shape. Depends on `SourceProfile` (S03 §7). A future **voucher-type master** emission
(if non-predefined types are ever needed) is an S12 concern, flagged there.

## 8. DoD + tests
- [ ] Pure; deterministic; imports only `contracts/`+`core/`.
- [ ] T: sales/receipt/payment roles → correct types at confidence 1.0.
- [ ] T: an ambiguous journal → sub-1.0 confidence (or C1 per policy).
- [ ] T-C1…C3 negatives raise the shared-base typed error (X4).
- [ ] `make check` green.
