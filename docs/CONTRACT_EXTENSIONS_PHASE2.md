# Contract Extensions — Phase 2 (ACCEPTED & IMPLEMENTED)

> **Status: ACCEPTED and applied.** The proposal below was approved and implemented:
> `BillAllocation` + `bill_allocations` + `party_ledger` (canonical & Tally), the S12
> emit/validate of both, `contracts/validation.py` (shared `ValidationReport`),
> `s10_reconcile.contracts` (`ImportedVoucherRef`/`PriorImportState` + matched set), and
> `s11_review.contracts` (`ReviewPolicy`/`ReviewItem`, reshaped `ReviewQueue`). GST stayed
> Tier A (ordinary entries); Tier-B statutory metadata remains deferred. The text below is
> retained as the design record.
>
> **Original status: PROPOSAL. No `contracts/` changed by this document.** This is the separate
> reviewed step the build sheets point to (S08 §7, S10 §7, S11 §7; `build_sheets/README.md`
> §5 items 4–5). It proposes the model changes that unblock S08 (enrich), S10 (reconcile),
> and S11 (review), with rationale, invariants, Tally mapping, and open questions. Nothing
> is implemented until you approve the shapes.

## 0. Status of previously-flagged contract changes

| README §5 item | Status |
|---|---|
| 1. Shared stage-error base | **Done** — `contracts/errors.py::StageError` (+ per-stage subclasses). |
| 2. Reshape S01 boundary | **Done** — `contracts/source.py` (`IngestedArchive`/`RawArtifact` + extras). |
| 3. S02 boundary: role + referential-integrity | **Done** — `SourceDataset`/`SourceTable`; joins validated in S02. (Row-index provenance lives only in error `detail`, not the DTO — *minor, flagged*.) |
| 4. Canonical extension for S08 | **This proposal — §1.** |
| 5. S10 / S11 carriers | **This proposal — §2, §3.** |

Design rules for everything below (unchanged invariants): all models stay
`frozen=True, extra="forbid"`; money is `Decimal`, never `float`; additions are
**optional with empty/None defaults** so existing 2-line vouchers and golden snapshots
are byte-unchanged; canonical concepts are **named after accounting reality**, not after
Zoho or Tally tags.

---

## 1. S08 — canonical model extension (bill allocations, party ledger, tax detail)

**Grounded in the round-trip** (`smoke_import/ROUNDTRIP_FINDINGS.md`): Tally stored
`PARTYLEDGERNAME`, customer/vendor ledgers default to `ISBILLWISEON=Yes`, and each line
carries an empty `BILLALLOCATIONS.LIST`. So posting against open bills needs bill
references, and the party ledger is a real concept Tally tracks.

### 1.1 Bill allocations

```python
# proposed — contracts/canonical.py (NOT applied)
class BillAllocation(BaseModel):
    model_config = _FROZEN
    reference: str            # the bill/invoice reference being settled or raised
    kind: Literal["new", "against", "advance", "on_account"]
    amount: Decimal           # positive magnitude; same side as the parent entry

class CanonicalLedgerEntry(BaseModel):           # + one optional field
    ...
    bill_allocations: tuple[BillAllocation, ...] = ()
```

- **Invariant (new, balance-preserving):** if `bill_allocations` is non-empty, their
  amounts sum **exactly** to the entry's `amount`. Empty = untracked (today's behavior).
- **Source-agnostic:** `reference`/`kind` are accounting concepts; the Zoho→reference and
  Zoho→kind mapping lives in the adapter (S08 / source profile), not the model.
- **Tally mapping (S12):** emit `<BILLALLOCATIONS.LIST>` inside the ledger entry with
  `<NAME>reference</NAME>`, `<BILLTYPE>` from `kind` (`new`→"New Ref",
  `against`→"Agst Ref", `advance`→"Advance", `on_account`→"On Account"), and signed
  `<AMOUNT>`. The `kind`→Tally-string map is a single point (like the §2.2 sign rule).

### 1.2 Party ledger

```python
class CanonicalVoucher(BaseModel):               # + one optional field
    ...
    party_ledger: str | None = None              # the principal party ledger, if any
```

- **Rationale:** Tally *derived* `PARTYLEDGERNAME` for us (import succeeded), but setting it
  explicitly is needed for correct bill-wise/party reporting and removes reliance on Tally's
  inference. Optional → no change for vouchers without a party.
- **Validator:** if set, `party_ledger` must match one of the voucher's entry ledger names.
- **Tally mapping:** `<PARTYLEDGERNAME>` on `<VOUCHER>` (only when set).

### 1.3 Tax (GST) detail — two-tier proposal

- **Tier A (no model change, recommended first):** GST is just **more ledger entries** —
  a Sales voucher becomes `Dr party / Cr Sales / Cr Output CGST / Cr Output SGST`. The
  canonical model **already supports N balanced entries**, so GST *posting* needs **zero
  extension**; it's S04/S06 work + ledger mappings. This is the cheapest correct path.
- **Tier B (deferred, statutory reporting):** if GST *returns* metadata is needed (HSN, rate,
  taxable value per line), propose an optional `tax_detail: TaxDetail | None` carrier:
  ```python
  class TaxDetail(BaseModel):
      model_config = _FROZEN
      hsn_or_sac: str | None
      rate_percent: Decimal | None
      taxable_value: Decimal | None
  ```
  Flagged as a **separate, later** decision — do not build until a real GST-return
  requirement and a grounded Tally structure exist (avoid inventing GST tags).

### 1.4 S12 emitter + Tally target model

The Tally target model (`contracts/tally.py`) mirrors §1.1–1.2: `TallyLedgerEntry` gains
`bill_allocations` (signed), `TallyVoucher` gains `party_ledger`; the S12 mapper carries
them and the serializer emits the new elements. **Backward-compatible:** defaults emit
nothing, so all current golden snapshots stay byte-identical.

**Open questions (1):** (a) Is Tier-A GST-as-entries acceptable as the Phase-2 GST story?
(b) `kind` vocabulary — are the four bill types sufficient? (c) Should `party_ledger` be
required for Receipt/Payment specifically, or always optional?

---

## 2. S10 — prior-import state carrier (reconcile)

S10 must flag vouchers already imported so re-runs are safe (the importer is not
idempotent). **Tally's auto-number is not a reliable cross-run key (X5)**, so identity must
be built from stable source/accounting fields.

```python
# proposed — new contracts/reconcile.py (NOT applied)
class ImportedVoucherRef(BaseModel):
    model_config = _FROZEN
    voucher_number: str       # our source document id (stable; what we emitted)
    voucher_type: str
    date: date
    amount: Decimal           # voucher gross magnitude, as a tiebreaker

class PriorImportState(BaseModel):
    model_config = _FROZEN
    imported: tuple[ImportedVoucherRef, ...] = ()
```

- **Where it comes from:** **our** bookkeeping of what we emitted (persisted across runs),
  *not* the `IMPORTRESULT` response — §2.3 returns counts + `LASTVCHID`, not per-voucher
  ids. Loading/saving `PriorImportState` is an imperative-shell concern; the **pure** S10
  core takes it as a value (D-S10.1).
- **Match key:** `(voucher_number, voucher_type, date)`; `amount` breaks ambiguity →
  ambiguous multi-match fails loud (R1).
- **`ReconciliationResult`** (exists) already carries `unmatched_voucher_numbers`; propose
  adding `matched_voucher_numbers: tuple[str, ...] = ()` so the orchestrator can skip matched
  vouchers explicitly rather than by difference.

**Open questions (2):** (a) Is source `voucher_number` the right identity anchor, or do we
also need source-system + company to avoid cross-company collisions? (b) Where does
`PriorImportState` persist (local file/db) — out of scope for the contract, but it drives the
shell design.

---

## 3. S11 — review policy + decisions (human gate)

S11 gates low-confidence / S07-flagged vouchers for human approval. The stub
`ReviewQueue`/`ReviewDecision` exist; what's missing is the **policy** (what gets gated) and a
**reason** on queued items.

```python
# proposed — contracts/review.py (NOT applied); Severity reused from s07 contracts
class ReviewPolicy(BaseModel):
    model_config = _FROZEN
    confidence_floor: float = Field(ge=0.0, le=1.0, default=1.0)
    gate_on_severities: tuple[Literal["error", "warning"], ...] = ("error",)

class ReviewItem(BaseModel):                      # richer than a bare voucher number
    model_config = _FROZEN
    voucher_number: str
    reason: str                                   # why it needs review (low confidence / rule)

class ReviewQueue(BaseModel):                     # proposed reshape of the stub
    model_config = _FROZEN
    batch: CanonicalBatch
    pending: tuple[ReviewItem, ...]
```

- **Gating rule (deterministic):** a voucher is pending iff `confidence < confidence_floor`
  **or** it carries an S07 issue whose severity ∈ `gate_on_severities`. Pure core; the human
  interaction (collecting `ReviewDecision`s) is the imperative shell (D-S11.2).
- **Fail-safe:** a pending voucher without an explicit `approved=True` is **withheld**, not
  emitted (D-S11.3).
- **Note:** reshaping `ReviewQueue` from `pending_voucher_numbers: tuple[str,...]` to
  `pending: tuple[ReviewItem,...]` is the only **breaking** change in this proposal; it
  touches a stub stage with no implementation yet, so impact is limited to its test.

**Open questions (3):** (a) default `confidence_floor` — `1.0` (gate everything below
certain) is safe but noisy; a lower default (e.g. `0.8`) may be more practical. (b) Should
`gate_on_severities` include `warning` by default?

---

## 4. Summary of proposed `contracts/` changes (for the review to accept/modify)

1. `contracts/canonical.py`: add `BillAllocation`; `CanonicalLedgerEntry.bill_allocations`
   (+ sum==amount validator); `CanonicalVoucher.party_ledger` (+ membership validator).
   *(Tier-B `TaxDetail` deferred.)*
2. `contracts/tally.py`: mirror bill allocations + party ledger on the target model; S12
   mapper/serializer emit them (golden snapshots unchanged by default).
3. New `contracts/reconcile.py`: `ImportedVoucherRef`, `PriorImportState`; extend
   `ReconciliationResult` with `matched_voucher_numbers`.
4. New `contracts/review.py`: `ReviewPolicy`, `ReviewItem`; reshape `ReviewQueue` to carry
   `ReviewItem`s.

All additive/optional except the `ReviewQueue` reshape (§3). On approval, each lands
**test-first** as its own change with `make check` kept green, followed by the S08/S10/S11
stage implementations.
