# S01 — Ingest (Zoho Adapter) — Build Sheet

> **Status: DESIGN — architectural decisions LOCKED (review round 1). Not implemented.**
> The decisions D1–D6 from review are recorded here as resolved (§9), with rationale.
> They imply a contract change in `contracts/` and `stages/s01_ingest/contracts.py`
> (§6.5) — that change is a **separate reviewed step and is NOT made in this task**.
> This sheet records *that it is needed* and *what it must be*. No contract or code is
> modified here. (First stage build sheet authored; sets the format for S02–S12.)

---

## 1. Stage identity & single responsibility

`s01_ingest` is the **Zoho adapter**. Its sole job (**Option A — thin unpacker**, D1):

> **Unzip a known Zoho export archive into role-tagged, immutable raw bytes —
> a typed, validated, source-agnostic boundary output. Nothing else.**

It is **ALLOWED to know everything about Zoho on its input side** (the ZIP layout, the
CSV file names, the encoding Zoho writes). That Zoho knowledge lives **only inside
s01's implementation**. Its **output** is the source-agnostic boundary type in
`stages/s01_ingest/contracts.py` — source-agnosticism is a property of that **output
contract**, not of s01's internals (D3).

**Explicitly NOT s01's job** (D1):
- **Does NOT parse CSVs into records** (rows/columns/typed cells) → S02.
- **Does NOT validate cross-file joins / referential integrity** → S02 (D2).
- Does NOT normalize values (dates, amounts) → S03.
- Does NOT classify voucher types → S04; map ledgers → S05; canonicalize → S06.

**Boundary principle (D1 rationale):** *any check requiring record-level understanding
is parse-stage work by definition.* If a validation needs to read a row, a column, or
two columns that "join", it is S02's, not s01's. s01 operates at the **archive + byte**
level only.

> This resolves the earlier pipeline tension: we keep IMPLEMENTATION_PLAN's
> **S01 = unpack / S02 = parse** split, which preserves single-responsibility (a core
> invariant). See D1 (§9).

---

## 2. Position in the pipeline

```
Zoho export ZIP  ──▶  [ s01_ingest : Zoho adapter ]  ──▶  source-agnostic boundary output  ──▶  S02 parse …
   (bytes on disk)         (knows Zoho internally)        (role-tagged immutable bytes;            (parses rows,
                                                           no Zoho concept is load-bearing)         checks joins)
```

- **Upstream:** a file on disk / byte blob. The only Zoho-aware edge in the system.
- **Downstream:** S02+ consume the boundary output and **must never need to know it
  came from Zoho**. If S02 has to branch on a Zoho file name, the boundary leaked (§6.2).

---

## 3. Input / output signatures

Imports allowed: **`contracts/` and `core/` only** — never another `stages/*` package
(enforced by import-linter `stage-independence`).

### Imperative shell (I/O at the edge)
```python
# reads bytes from disk; the ONLY place s01 touches the filesystem
def load_archive(request: IngestRequest) -> bytes: ...
```
- `IngestRequest` (exists, `contracts.py`): `source_system: str`, `location: str`.
  `location` is the path to the Zoho export ZIP. Zoho knowledge on the **input** side
  is allowed, so these are fine as-is.

### Pure core (bytes → boundary; deterministic, no I/O)
```python
def ingest_zoho(archive: bytes, *, source_system: str) -> <IngestedArchive>: ...
```
- **Input:** raw ZIP bytes (immutable original; never mutated).
- **Output:** the **source-agnostic boundary type** from
  `stages/s01_ingest/contracts.py`. Per Option A the target shape is **role-tagged
  immutable bytes + provenance + extra-artifacts record** (defined in §6.5).
  - The **current** `RawSourceDocument(source_system, filename, content: bytes)` is
    **not** that shape (it makes `filename` load-bearing and has no extra-artifacts
    record). Replacing it is the separate contract step (§6.5). Signatures here name the
    **target**, not today's stub.

### Typed errors
- Every boundary violation raises a **typed error** descending from a **shared stage
  error base** (D4) — not a bare `BadZipFile`/`UnicodeDecodeError`. That base does not
  yet exist in `contracts/errors.py`; adding it is part of §6.5 (separate step).

---

## 4. Architectural invariants (must hold)

| Invariant | How s01 honors it |
|---|---|
| **Immutable original** | `archive: bytes` is read-only; never mutated. Output models `frozen=True, extra="forbid"`. |
| **Determinism** | Same archive bytes → byte-identical output. **Sort artifacts by role** (stable), never by ZIP/dir iteration order. No clocks, no randomness. |
| **Pure core / imperative shell** | All unpacking is a pure function of `bytes`; only `load_archive` does I/O. |
| **Source-agnostic output** | Zoho file taxonomy stays inside s01; the boundary carries an accounting-named **role**, not the filename, as load-bearing data (§6, D3). |
| **Imports** | Only `contracts/` + `core/`. No `stages/*`. No new third-party dep without review. |
| **Fail loud** | Every archive/byte-level violation raises a typed error (§5); nothing silently skipped or coerced. (Record-level violations are S02's, by D1.) |

---

## 5. Fail-loud validation & typed errors (archive + byte level only)

Per D1, s01 validates only what it can see **without parsing rows**. Each row below is a
validation s01 performs and a negative test it must have; each raises a typed error
(descending from the shared base, D4) naming the offending artifact.

| # | Condition | Behavior |
|---|---|---|
| V1 | **Not a ZIP / corrupt archive** (bad magic, truncated, `BadZipFile`) | Fail loud; no partial processing. |
| V2 | **Missing REQUIRED artifact** (a required Zoho file absent — list in §6.4) | **Fail loud**, naming the missing role/artifact (D5). |
| V3 | **Unexpected EXTRA artifact** (entry not in the known set) | **Warn-and-record, do NOT fail** — the boundary carries an "extra artifacts seen" record (D5). |
| V4 | **Encoding** — an artifact's bytes are not decodable as the declared text encoding | Fail loud. **Zoho reality (this dataset): UTF-8, no BOM.** Be BOM-tolerant (`utf-8-sig`); reject undecodable bytes rather than mojibake-coercing. (Decoding bytes to verify ≠ parsing rows, so this stays in s01. Contrast: Tally *exports* are UTF-16 — that's S12/response territory.) |
| V5 | **Empty required artifact** — present but **zero/whitespace-only bytes** | Fail loud; a required artifact with no bytes is a corrupt export. *("Header-only / zero data rows" needs row parsing → that check is S02, not here.)* |

> **Relocated to S02 (record-level — by D1/D2):** malformed CSV structure (ragged rows,
> wrong column count), **duplicate primary IDs within an artifact**, "header-only/empty
> data" detection, and **referential-integrity / unjoinable IDs**. These all require
> parsing CSVs into records and knowing which columns are meant to join — semantic work,
> not unpacking.
>
> **Real Zoho join keys — recorded here for the S02 sheet to pick up (D2):**
> - `Sales_Invoices.customer_id` → `Contacts.contact_id`
> - `Sales_Invoice_Items.invoice_id` → `Sales_Invoices.invoice_id`
> - `Sales_Invoice_Items.item_id` → `Items.item_id`
> - (analogously) `Bills`/`Bill_Items`, `Vendor_Payments` → `Vendors`
>
> These key names are **Zoho's** and must never appear in s01's boundary output (§6.2).

---

## 6. CRITICAL — source-agnostic discipline

### 6.1 Accounting concepts the boundary output must carry (named after accounting reality)

The boundary describes the **artifacts present**, named by what they *are*, not by the
Zoho file that produced them. s01 maps Zoho → these **roles** internally (D3).

| Accounting **role** (boundary name) | Mapped internally from (Zoho) — stays inside s01 |
|---|---|
| **Parties: customers** | `Contacts.csv` |
| **Parties: suppliers** | `Vendors.csv` |
| **Stock items** | `Items.csv` |
| **Sales invoices** / **…line items** | `Sales_Invoices.csv` / `Sales_Invoice_Items.csv` |
| **Customer receipts** | `Customer_Payments.csv` |
| **Purchase bills** / **…line items** | `Bills.csv` / `Bill_Items.csv` |
| **Supplier payments** | `Vendor_Payments.csv` |
| **Credit notes** | `Credit_Notes.csv` |
| **Journal entries** | `Journals.csv` |
| **Bank transactions** | `Bank_Transactions.csv` |
| **Tax transactions** | `GST_Transactions.csv` |
| **Orders / memoranda** (non-posting) | `Sales_Orders.csv`, `Purchase_Orders.csv` |
| **Inventory movements / adjustments** | `Inventory_Transactions.csv`, `Inventory_Adjustments.csv` |

The role is an **accounting-named enum**. Bytes are carried opaque; typing/coercion is
S02/S03.

### 6.2 The leak rule + audit of the existing contract (D3)

**Rule:** *If a field in the boundary type only makes sense because Zoho exists, and it
is **load-bearing** (consumed by downstream dispatch/branching), it is a leak.* The leak
rule applies to **what crosses the boundary as load-bearing data**, not to what s01
knows internally.

| Field | Verdict |
|---|---|
| `source_system: str` | **OK.** Generic source tag (`"zoho"`, later `"busy"`). |
| `content: bytes` | **OK as opaque bytes.** Carries no Zoho semantics. |
| `filename: str` (current, load-bearing) | **LEAK as currently shaped.** If downstream dispatches on `"Sales_Invoices.csv"` it becomes Zoho-aware. **Fix (D3):** the boundary carries the **role** (accounting enum) as the load-bearing key; the filename may be retained as **provenance metadata only**, which **no downstream logic may consume for dispatch or branching.** |

**Blessed Zoho input-side knowledge (D3):** s01 *may* contain a Zoho-specific
`filename → role` dispatch table internally. That is the adapter doing its job, not a
leak — source-agnosticism is a property of the **output**, and s01 is explicitly the
Zoho adapter with full Zoho knowledge on its **input** side.

**`T-LEAK` guard (revised, D3):** the guard test must assert **no Zoho filename is
load-bearing downstream** — i.e. role drives all dispatch and nothing branches on the
provenance filename. It must **NOT** assert the filename string is absent entirely;
retaining it as provenance metadata is permitted.

### 6.3 Busy must produce the SAME boundary (without changing the contract)

A future **Busy adapter** must emit the **same** boundary type. Contract test:
*"Could a Busy adapter populate this type from a Busy export without renaming a field or
adding a Zoho-shaped one?"* If not, the contract is Zoho-coupled.

- **Do NOT** write a Busy mapping here.
- **Do NOT** invent Busy file names, columns, or schemas — that is the
  XML-tag-invention hallucination risk generalized; we have no Busy export to ground
  against, so any such names would be fiction.
- **Only** obligation: express the boundary in accounting roles (§6.1) so it *doesn't
  preclude* Busy. The Busy `filename → role` table would live inside a *Busy* adapter,
  exactly as Zoho's lives inside s01.

### 6.4 Required vs. extra Zoho artifacts (D5)

Two outcomes, by reality:

- **Missing a REQUIRED artifact → fail loud** (V2). A missing required file is a real
  "reality differs from our assumptions" signal and must surface, not be swallowed.
- **An unexpected EXTRA artifact present → warn-and-record, do not fail** (V3). Zoho's
  export set varies by enabled account features, so "any unknown file = hard fail" would
  reject valid exports. The boundary therefore carries an **"extra artifacts seen"**
  record.

**REQUIRED Zoho artifacts (s01 fails if any is absent):**
`Contacts.csv`, `Sales_Invoices.csv`, `Customer_Payments.csv`, `Vendor_Payments.csv`.

- *Rationale:* this is exactly the set the current voucher-generation path consumes
  (customer parties → ledgers; sales → Sales vouchers; customer/vendor payments →
  Receipt/Payment vouchers). Their absence makes the export unusable for our purpose.
- ⚠ *Judgment call — flag for revisit (per D5):* the required set should **expand** as
  voucher scope grows (e.g. `Bills`, `Journals`, `Credit_Notes`, `Vendors`,
  `Sales_Invoice_Items`). Treated as required-now = "what we actually consume today",
  deliberately conservative to avoid rejecting valid exports.

**KNOWN-OPTIONAL artifacts** (recognized roles; consumed if present, absence is fine):
`Vendors.csv`, `Items.csv`, `Sales_Invoice_Items.csv`, `Bill_Items.csv`, `Bills.csv`,
`Credit_Notes.csv`, `Bank_Transactions.csv`, `GST_Transactions.csv`,
`Sales_Orders.csv`, `Purchase_Orders.csv`, `Inventory_Transactions.csv`,
`Inventory_Adjustments.csv`.

**OUT OF SCOPE (D6):** `Projects.csv`, `Time_Entries.csv` — **deliberately excluded**
from the artifact set. *Rationale:* they are not postable accounting documents and the
product goal is voucher generation. This is a **decision, not an omission to fix later**;
if present in a real export they fall under "extra artifacts seen" (V3), recorded but
not consumed.

**UNKNOWN/EXTRA:** any archive entry not in the required or known-optional sets →
recorded in "extra artifacts seen" (V3), never consumed for dispatch.

### 6.5 Required contract changes (SEPARATE reviewed step — NOT done in this task)

Option A implies these `contracts/` changes. They are **flagged here, not made now**;
they are a separate reviewed step before s01 implementation:

1. **Replace the s01 boundary output type** (`stages/s01_ingest/contracts.py`) so it
   carries:
   - `role` — an **accounting-named enum** (load-bearing key; §6.1),
   - `content: bytes` — immutable raw bytes,
   - declared/validated text `encoding`,
   - `filename` (or similar) as **optional provenance metadata only** — downstream must
     not branch on it (D3),
   - an **"extra artifacts seen"** record at the archive level (D5).
   (Conceptually: a `RoleTaggedArtifact` per file + an `IngestedArchive` container; the
   exact shape is the review's to fix. The current `RawSourceDocument` is retired/reshaped.)
2. **Add a shared stage-error base to `contracts/errors.py`** (D4): a small base type
   with fields `stage`, `code`, human-readable `message`, machine-readable `detail`;
   `IngestError` subclasses it.
   - *Rationale:* `errors.py`'s ingest story is currently empty, and whatever s01 picks
     sets precedent for all 12 stages — defining a shared base **once** prevents twelve
     divergent error shapes.
   - ⚠ *Judgment call (per D4):* the "shared base vs. per-stage one-off" choice was made
     in review; flagged so it can be revisited before it's frozen across stages.

---

## 7. Definition of Done

> **Gated on §6.5** (boundary + error-base contract change, reviewed & frozen). Stated
> now so the contract review has a target.

- [ ] §6.5 contract change reviewed, frozen, merged (separate step).
- [ ] `s01_ingest` implements `load_archive` (shell) + `ingest_zoho` (pure core) against
      the frozen boundary; imports only `contracts/` + `core/`.
- [ ] All Zoho `filename → role` mapping lives **inside** s01; the boundary's
      load-bearing key is the **role**, never the filename.
- [ ] Deterministic: same archive → byte-identical output (artifacts stably sorted by role).
- [ ] Immutable original: input bytes never mutated; outputs frozen.
- [ ] `make check` green (ruff, mypy strict, import-linter, pytest ≥90%).

**Explicit test cases (each a test; negatives/edges first):**

*Happy path*
- [ ] T-OK1: the real 19-file Zoho sample → boundary with the expected **roles**; the 4
      required artifacts present; counts match.
- [ ] T-OK2: determinism — ingest twice → identical bytes; re-zipping inputs in a
      different entry order → identical output (artifacts sorted by role).
- [ ] T-OK3: an archive containing an unknown extra file → succeeds, with that file
      listed in "extra artifacts seen" and **not** consumed (D5/V3).
- [ ] T-OK4: `Projects.csv`/`Time_Entries.csv` present → recorded as extra, not consumed
      (D6); their absence → no error.

*Negatives / edges (map to §5)*
- [ ] T-V1a: not-a-zip bytes → typed error. T-V1b: truncated/corrupt zip → typed error.
- [ ] T-V2: archive missing a **required** artifact (e.g. `Customer_Payments.csv`) →
      typed error naming the missing role (D5).
- [ ] T-V4a: UTF-8 **with** BOM → accepted (BOM-tolerant). T-V4b: invalid byte sequence
      → typed error (no mojibake).
- [ ] T-V5: present-but-empty **required** artifact (zero/whitespace bytes) → typed error.
- [ ] T-LEAK: guard — **no Zoho filename is load-bearing** downstream (role drives
      dispatch); provenance filename MAY be present (D3). *(Not "filename absent".)*
- [ ] T-ERR: every raised error descends from the shared stage-error base and carries
      `stage`/`code`/`message`/`detail` (D4).

*Note:* malformed-row, duplicate-ID, header-only-empty, and unjoinable-ID tests live in
the **S02** sheet (D1/D2), not here.

---

## 8. Ordered task list (gated, test-first)

1. *(separate review, §6.5)* Decide & freeze the s01 boundary type + shared error base.
2. Write failing tests T-V1, T-V2, T-V4, T-V5, T-LEAK, T-ERR against the frozen boundary.
3. Implement pure `ingest_zoho(bytes)`; make negatives pass.
4. Implement `load_archive` shell; wire happy paths T-OK1…T-OK4.
5. `make check` green; confirm import-linter shows s01 importing only `contracts/`+`core/`.

---

## 9. Decisions (RESOLVED — review round 1)

Each records **verdict + rationale**; the next session must inherit *why*, not just *what*.

**D1 — Stage scope: Option A (thin unpacker).**
- *Verdict:* s01 unzips a known archive shape into role-tagged, immutable raw bytes. It
  does **not** parse CSVs into records, **not** validate cross-file joins, **not**
  canonicalize.
- *Rationale:* keeps single-responsibility (our invariant) and matches
  IMPLEMENTATION_PLAN's **S01 = unpack / S02 = parse** split. Any check requiring
  record-level understanding is parse-stage work by definition.

**D2 — Relocate the unjoinable-ID check (V7) to S02.**
- *Verdict:* removed from s01's fail-loud table; S02 owns referential-integrity
  validation. The real Zoho join keys are recorded in §5 for the S02 sheet to pick up.
- *Rationale:* a join check requires parsing CSVs into records and knowing two columns
  are meant to join — semantic/parse work, not unpacking. It was mis-assigned to s01 in
  the original prompt; corrected here.

**D3 — `filename → role` mapping is blessed Zoho input-side knowledge.**
- *Verdict:* s01 may hold a Zoho-specific `filename → role` dispatch table internally.
  The **boundary output** carries only the **role** (accounting-named enum), never the
  filename as load-bearing data. `filename` MAY be retained as **provenance metadata
  only**, never consumed downstream for dispatch/branching. `T-LEAK` asserts no Zoho
  filename is load-bearing — **not** that the string is absent.
- *Rationale:* source-agnosticism is a property of the **output** contract, not of s01's
  internals. s01 is explicitly the Zoho adapter, allowed full Zoho knowledge on its
  input side. The leak rule applies to what crosses the boundary, not to what s01 knows.

**D4 — Shared typed-error base, not a one-off `IngestError`.**
- *Verdict:* `contracts/errors.py` needs a small **shared base** (fields: `stage`,
  `code`, human-readable `message`, machine-readable `detail`); `IngestError`
  subclasses it. Recorded as a **required contract change** for the separate reviewed
  step (§6.5) — **not made now**.
- *Rationale:* `errors.py` is currently empty of an ingest story; whatever shape s01
  picks sets precedent for all 12 stages, so define the base **once** to prevent twelve
  divergent error shapes. ⚠ *Judgment call in review — flagged for possible revisit.*

**D5 — Unknown-entry policy: required-vs-extra split.**
- *Verdict:* **missing required** artifact = fail loud (typed error naming what's
  missing); **unexpected extra** artifact = warn-and-record, do not fail. The boundary
  carries an "extra artifacts seen" record. Required set listed in §6.4.
- *Rationale:* Zoho's export set varies by enabled features, so "any unknown file = hard
  fail" is too brittle and would reject valid exports; but a missing **required** file is
  a real "reality differs from assumptions" signal that must surface, not be swallowed.
  ⚠ *Judgment call in review — flagged (esp. the membership of the required set).*

**D6 — `Projects` / `Time_Entries`: out of scope.**
- *Verdict:* excluded from s01's required-artifact set; if present, recorded as "extra"
  (V3), not consumed.
- *Rationale:* not postable accounting documents; the product goal is voucher
  generation. Recorded as a **deliberate exclusion**, not an omission to "fix" later.
