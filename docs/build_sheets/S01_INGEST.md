# S01 — Ingest (Zoho Adapter) — Build Sheet

> **Status: DESIGN / FOR REVIEW. Do not implement yet.**
> This sheet defines the build for `stages/s01_ingest`. It also raises a **contract
> gap** (§6.4): the existing boundary type `RawSourceDocument` is not sufficient to be
> source-agnostic and carries a Zoho-coupled field. Per the working rules, contract
> changes in `contracts/` (and the stage `contracts.py`) are a **separate reviewed
> step** — this sheet flags the gap and stops; it does not modify any contract.
> (This is also the first stage build sheet authored; it sets the format for S02–S12.)

---

## 1. Stage identity & single responsibility

`s01_ingest` is the **Zoho adapter**. Its sole job:

> **Take a Zoho Books export archive → produce a typed, validated, source-agnostic
> boundary output. Nothing else.**

It is **ALLOWED to know everything about Zoho on its input side** (the ZIP layout, the
CSV file names, their columns, the encoding Zoho writes). That Zoho knowledge lives
**only inside s01's implementation**. Its **output** is the source-agnostic boundary
type declared in `stages/s01_ingest/contracts.py` — source-agnosticism is an
architectural goal (IMPLEMENTATION_PLAN.md) and it lives in that output contract, not
in s01's internals.

**Explicitly NOT s01's job** (later stages own these):
- Normalizing values (dates, amounts, encodings of *content*) → S03.
- Parsing CSV rows into typed business records with coerced types → S02.
- Classifying voucher types → S04.
- Mapping source accounts to Tally ledgers → S05.
- Building the `CanonicalBatch` → S06.

If s01 ever imports `Decimal` to interpret an amount, picks a voucher type, or renames
an account, it has overstepped.

> **Pipeline tension to resolve before implementation (see §6.4).** IMPLEMENTATION_PLAN
> describes S01 as "read raw artifacts into raw byte/record payloads" (pure unzip) and
> S02 as the parser. Your framing for this sheet asks s01's *output* to be
> source-agnostic and to fail loud on **unjoinable IDs** — which requires reading the
> CSV id columns (light parsing) inside s01. These two readings imply **different
> boundary outputs**. §6.4 states the options; the boundary contract must be decided
> (and reviewed) before code is written.

---

## 2. Position in the pipeline

```
Zoho export ZIP  ──▶  [ s01_ingest : Zoho adapter ]  ──▶  source-agnostic boundary output  ──▶  S02 parse …
   (bytes on disk)         (knows Zoho internally)        (no Zoho concepts on this edge)
```

- **Upstream:** a file on disk / a byte blob. The only Zoho-aware edge in the system.
- **Downstream:** S02+ consume the boundary output and **must never need to know it
  came from Zoho**. If S02 has to branch on a Zoho file name, the boundary leaked.

---

## 3. Input / output signatures

Imports allowed: **`contracts/` and `core/` only**. Never another `stages/*` package
(enforced by import-linter `stage-independence`).

### Imperative shell (I/O at the edge)
```python
# reads bytes from disk; the ONLY place s01 touches the filesystem
def load_archive(request: IngestRequest) -> bytes: ...
```
- `IngestRequest` (exists, `contracts.py`): `source_system: str`, `location: str`.
  `location` is the path to the Zoho export ZIP. Zoho knowledge on the input side is
  allowed, so `location`/`source_system` are fine here.

### Pure core (bytes → boundary; deterministic, no I/O)
```python
def ingest_zoho(archive: bytes, *, source_system: str) -> <BoundaryOutput>: ...
```
- **Input:** the raw ZIP bytes (immutable original; never mutated).
- **Output:** the **source-agnostic boundary type** from
  `stages/s01_ingest/contracts.py`.
  - **Current contract:** `tuple[RawSourceDocument, ...]` where
    `RawSourceDocument(source_system, filename, content: bytes)`.
  - **⚠ This output type is flagged insufficient/leaky in §6.4 — pending contract
    review.** Signatures here are written against the *current* contract only to show
    intent; the real output type is a review output, not a decision made in this sheet.

### Typed errors
- Must raise a **typed ingest error** on every boundary violation (§5).
- `contracts/errors.py` currently defines `MoneyError`, `BalanceError`,
  `ValidationError`, `XmlContractError` — **no ingest error type**. Adding an
  `IngestError` family is a `contracts/` change ⇒ **separate reviewed step** (§6.4).
  Until then this sheet names the *intended* error semantics, not a concrete class.

---

## 4. Architectural invariants (must hold)

| Invariant | How s01 honors it |
|---|---|
| **Immutable original** | Treat `archive: bytes` as read-only; never mutate input. Output models are `frozen=True, extra="forbid"`. |
| **Determinism** | Same archive bytes → byte-identical boundary output. **Sort archive entries by a stable key** (artifact role, then name) — never rely on ZIP/dir iteration order. No clocks, no randomness, no `datetime.now()`. |
| **Pure core / imperative shell** | All parsing is a pure function of `bytes`. Only `load_archive` does I/O. |
| **Source-agnostic output** | The Zoho file taxonomy stays inside s01; the output names concepts by accounting reality (§6). |
| **Imports** | Only `contracts/` + `core/`. No `stages/*`. No new third-party dep beyond what's already approved without review. |
| **Fail loud** | Every malformed-input case raises a typed error (§5); nothing is silently skipped or coerced. |

---

## 5. Fail-loud validation & typed errors

Each row is a validation s01 must perform and a negative test it must have. Every
violation raises a **typed ingest error** (pending the error-type review, §3) with a
message naming the offending artifact — never a bare `KeyError`/`UnicodeDecodeError`.

| # | Condition | Behavior |
|---|---|---|
| V1 | **Not a ZIP / corrupt archive** (bad magic, truncated, `BadZipFile`) | Raise typed error; do not partially process. |
| V2 | **Missing expected artifact(s)** — a required Zoho file absent from the archive | Raise, listing which expected artifact role is missing. |
| V3 | **Unexpected / unknown entries** | Decide policy (reject vs. ignore-with-record). Default: **reject loud** if an entry can't be mapped to a known artifact role — silent drop hides data. |
| V4 | **Encoding** — content not decodable as the declared encoding | Raise. **Zoho reality (this dataset): UTF-8, no BOM.** Be BOM-tolerant (`utf-8-sig`); reject undecodable bytes loudly rather than mojibake-coercing. (Contrast: Tally *exports* are UTF-16 — that's S12/response territory, not here.) |
| V5 | **Empty file** — a present artifact with zero bytes or header-only | Raise; an empty required artifact is a corrupt export, not "no data". |
| V6 | **Malformed CSV structure** — header missing, ragged rows, wrong column count | Raise, naming artifact + row. |
| V7 | **Unjoinable IDs** — referential integrity across artifacts (see keys below) | Raise, naming the dangling reference. *Placement depends on §6.4 — this requires reading id columns.* |
| V8 | **Duplicate primary IDs** within an artifact | Raise; duplicate source-document ids are ambiguous. |

**Known Zoho join keys (referential-integrity targets for V7):**
- `Sales_Invoices.customer_id` → `Contacts.contact_id`
- `Sales_Invoice_Items.invoice_id` → `Sales_Invoices.invoice_id`
- `Sales_Invoice_Items.item_id` → `Items.item_id`
- (analogously) `Bills`/`Bill_Items`, `Vendor_Payments` → `Vendors`

> These key names are **Zoho's** and stay *inside* s01. They must **not** appear in the
> boundary output (§6).

---

## 6. CRITICAL — source-agnostic discipline

### 6.1 Accounting concepts the boundary output must carry (named after accounting reality)

The boundary output describes the **accounting artifacts present in the export**, named
by what they *are*, not by the Zoho file/column that produced them. s01 maps Zoho →
these concepts internally.

| Accounting concept (boundary name) | Sourced internally from (Zoho) — stays inside s01 |
|---|---|
| **Parties** (customers & suppliers) | `Contacts.csv`, `Vendors.csv` |
| **Stock items** | `Items.csv` |
| **Sales invoices** (+ their line items) | `Sales_Invoices.csv`, `Sales_Invoice_Items.csv` |
| **Customer receipts** | `Customer_Payments.csv` |
| **Purchase bills** (+ line items) | `Bills.csv`, `Bill_Items.csv` |
| **Supplier payments** | `Vendor_Payments.csv` |
| **Credit notes** | `Credit_Notes.csv` |
| **Journal entries** | `Journals.csv` |
| **Bank transactions** | `Bank_Transactions.csv` |
| **Tax transactions** | `GST_Transactions.csv` |
| **Orders / memoranda** (non-posting) | `Sales_Orders.csv`, `Purchase_Orders.csv` |
| **Inventory movements / adjustments** | `Inventory_Transactions.csv`, `Inventory_Adjustments.csv` |
| **Non-financial** (likely out of scope) | `Projects.csv`, `Time_Entries.csv` |

Identifiers carried at the boundary are **opaque source-document ids** ("the source's
own id for this document"), not "Zoho invoice id". A `Decimal`-free, value-neutral
container — s01 carries raw cell text; typing/coercion is S02/S03.

### 6.2 The leak rule + audit of the existing contract

**Rule:** *If a field in the boundary type only makes sense because Zoho exists, it is
a leak.* Apply it to the existing `RawSourceDocument`:

| Field | Verdict |
|---|---|
| `source_system: str` | **OK.** Generic source tag (`"zoho"`, later `"busy"`). Names the adapter, not a Zoho concept. (Could become an enum later.) |
| `content: bytes` | **OK as opaque bytes** — but carries **zero accounting concepts**, so by itself it does not satisfy "the boundary must carry accounting concepts" (it's a pure unzip). |
| `filename: str` | **LEAK.** `"Sales_Invoices.csv"` only exists because Zoho. If any downstream stage switches on this string it becomes Zoho-aware. The boundary should carry a **source-neutral artifact role** (an accounting category from §6.1), with the Zoho `filename → role` mapping kept inside s01. Keep the literal filename, if at all, only as opaque *provenance* that downstream is forbidden to branch on. |

### 6.3 Busy must produce the SAME boundary (without changing the contract)

A future `s02…`-unaware **Busy adapter** must emit the **same** boundary type. Design
test for the contract: *"Could a Busy adapter populate this type from a Busy export
without renaming a field or adding a Zoho-shaped one?"* If not, the contract is
Zoho-coupled.

- **Do NOT** write a Busy mapping here.
- **Do NOT** invent Busy file names, column names, or schemas — that is the
  XML-tag-invention hallucination risk generalized. We have no Busy export to ground
  against, so anything we'd write would be fiction.
- **Only** obligation: ensure the boundary type is expressed in accounting concepts
  (§6.1) so it *doesn't preclude* Busy. Nothing more.

### 6.4 ⚠ CONTRACT GAP — STOP

The existing `stages/s01_ingest/contracts.py` boundary is **not adequate** for the
source-agnostic goal as framed:

1. **`filename` is Zoho-coupled** (§6.2) — a leak if used for dispatch.
2. **`RawSourceDocument` carries no accounting concepts** — pure `(filename, bytes)`.
   Under "the boundary must carry accounting concepts named after accounting reality"
   (§6.1) and the **unjoinable-ID** fail-loud requirement (V7, which needs id columns),
   a pure-bytes container is **insufficient**.
3. **No typed ingest error** exists in `contracts/errors.py` (§3).
4. **Pipeline tension** (§1): pure-unzip-S01 (plan) vs. adapter-emits-structure-S01
   (this sheet's framing) are different contracts. They must be reconciled.

**Two coherent resolutions (for the review, not decided here):**

- **Option A — keep S01 a thin unpacker; fix only the leak.** Boundary = a sorted
  collection of artifacts keyed by a **source-neutral artifact role** (enum from §6.1) +
  declared text encoding + opaque provenance; `content` stays bytes. CSV row parsing
  and referential checks (V6–V8) **move to S02**. Smallest contract change; keeps the
  planned pipeline; removes the `filename` leak. Accounting concepts carried = the
  **roles**.
- **Option B — S01 is the full adapter.** Boundary = source-neutral accounting
  artifacts (parties, documents, line items) as typed-but-unnormalized records; V6–V8
  belong in s01. Larger contract; overlaps the planned S02 "parse" responsibility and
  must be reconciled with IMPLEMENTATION_PLAN.

**Action: STOP.** Do not modify `contracts/` or `stages/s01_ingest/contracts.py`.
Decide Option A vs B (and the typed-error family) in a separate **contract-review**
step. The §7 task list is **blocked** on that decision.

---

## 7. Definition of Done

> **Blocked by §6.4.** DoD becomes actionable once the boundary contract + ingest
> error type are reviewed and frozen. Stated now so the review has a target.

- [ ] Boundary contract for s01 decided (Option A/B), reviewed, and frozen; typed
      ingest error added to `contracts/errors.py` (separate reviewed step).
- [ ] `s01_ingest` implements `load_archive` (shell) + `ingest_zoho` (pure core)
      against the frozen boundary; imports only `contracts/` + `core/`.
- [ ] All Zoho file→concept mapping lives **inside** s01; no Zoho name appears in the
      boundary output.
- [ ] Deterministic: same archive → byte-identical output (entries stably sorted).
- [ ] Immutable original: input bytes never mutated; outputs frozen.
- [ ] `make check` green (ruff, mypy strict, import-linter, pytest ≥90%).

**Explicit test cases (each a test; negatives/edges first):**

*Happy path*
- [ ] T-OK1: the real 19-file Zoho sample → boundary output with the expected set of
      artifact roles; counts match; output is source-agnostic (assert **no** Zoho file
      name / column name appears anywhere in the serialized boundary).
- [ ] T-OK2: determinism — ingest twice → identical bytes; re-zipping inputs in a
      different entry order → identical output.

*Negatives / edges (map to §5)*
- [ ] T-V1a: not-a-zip bytes → typed error. T-V1b: truncated/corrupt zip → typed error.
- [ ] T-V2: archive missing a required artifact → typed error naming the role.
- [ ] T-V3: archive with an unknown extra entry → reject-loud (or recorded, per policy).
- [ ] T-V4a: UTF-8 **with** BOM → accepted (BOM-tolerant).
      T-V4b: invalid byte sequence → typed error (no mojibake).
- [ ] T-V5: present-but-empty / header-only artifact → typed error.
- [ ] T-V6: ragged row / missing header → typed error naming artifact+row.
- [ ] T-V7: `Sales_Invoices.customer_id` with no matching `Contacts.contact_id`
      → typed error naming the dangling reference *(placement per §6.4 option)*.
- [ ] T-V8: duplicate primary id within an artifact → typed error.
- [ ] T-EDGE: artifact present but all-blank amount column → carried as raw text (s01
      does **not** coerce/validate amounts — that's S02/S03); assert no `Decimal` use.
- [ ] T-LEAK: property/guard test — the boundary output type has **no field** whose
      name or value vocabulary is Zoho-specific (guards §6.2 in CI).

---

## 8. Ordered task list (gated, test-first) — BLOCKED on §6.4

1. *(separate review)* Decide & freeze the s01 boundary contract + `IngestError`.
2. Write failing tests T-V1…T-V8, T-LEAK against the frozen boundary.
3. Implement pure `ingest_zoho(bytes)`; make negatives pass.
4. Implement `load_archive` shell; wire happy path T-OK1/T-OK2.
5. `make check` green; confirm import-linter shows s01 importing only `contracts/`+`core/`.

---

## 9. Open decisions for review (answer before implementation)

1. **Option A vs B** (§6.4): thin unpacker (roles + bytes; parsing→S02) **or** full
   adapter (structured accounting records in s01)?
2. **Typed error**: add `IngestError` (+ subtypes) to `contracts/errors.py`? Names?
3. **V3 unknown-entry policy**: reject-loud vs. record-and-continue?
4. **V7 placement**: referential-integrity in s01 (implies Option B-ish) or S02?
5. **Scope**: are `Projects` / `Time_Entries` (non-financial) in or out of the ingest
   artifact set?
