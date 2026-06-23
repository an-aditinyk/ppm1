# The Engine — Step by Step

A walkthrough of how TallyImporter turns a **Zoho Books export** into **TallyPrime
import XML**, one stage at a time. Use this to explain the engine end to end. It follows
**one sales invoice** (`INV1`, customer `Acme & Co`, total `1000`) the whole way down.

---

## The big idea

```
Zoho export ─►  [ S01 .. S05 ]  ─►  CanonicalBatch  ─►  [ S06 .. S12 ]  ─►  Tally XML
                 adapter region        the SEAM            spine
              (knows the source)   (source-neutral)     (knows Tally)
```

- **One canonical model** sits in the middle. Above it: source-shaped data. Below it: a
  pure double-entry accounting batch that knows nothing about Zoho.
- **Each stage is a pure function** with a typed input and a typed output. Stages never
  import each other; they share types through `contracts/`.
- **Two rules make the output trustworthy:** every boundary *validates or raises* (fail
  loud), and the same input always yields *byte-identical* output (deterministic).

Two facts the engine leans on, learned by importing into real TallyPrime:
1. The Tally **sign convention** — debit = `ISDEEMEDPOSITIVE=Yes` with a **negative**
   amount, credit = `No` with a **positive** amount, and a voucher's amounts **sum to 0**.
2. **Minimal ledger masters** suffice — `NAME` + `PARENT` + `ACTION`; Tally fills the rest.

---

## Stage by stage

Legend: **In →** input type · **Out →** output type · **Guards** = what makes it fail loud.

### S01 — Ingest  *(the Zoho adapter)*
- **In →** raw `bytes` of the `.zip` · **Out →** `IngestedArchive`
- **What it does:** opens the ZIP and tags each known file with an **accounting role**
  (`Sales_Invoices.csv → SALES_INVOICES`), keeping the raw bytes. Unknown files are
  *recorded* (not consumed); `Projects/Time_Entries` are ignored. It does **not** parse
  CSV — just unpack and label.
- **Guards:** corrupt zip · missing a **required** file (`Contacts`, `Sales_Invoices`,
  `Customer_Payments`, `Vendor_Payments`) · empty file · bad encoding.
- **Why a role, not a filename?** A filename only means something *because Zoho exists*.
  Downstream sees the role; the `filename→role` table is the only Zoho-specific thing here.

> **Our invoice:** the bytes of `Sales_Invoices.csv` become a `RawArtifact(role=SALES_INVOICES)`.

### S02 — Parse
- **In →** `IngestedArchive` · **Out →** `SourceDataset` (a table per role)
- **What it does:** turns each file's CSV into a header + rows, and runs the **record-level
  checks**: malformed/ragged rows, duplicate primary ids, and **referential integrity**
  (every `customer_id` on an invoice must exist in `Contacts`).
- **Guards:** ragged row · duplicate id · **unjoinable id** · missing expected column.

> **Our invoice:** `SourceTable(role=SALES_INVOICES, headers=(invoice_id, customer_id, total),
> rows=[("INV1","C1","1000")])`; the join `C1 ∈ Contacts.contact_id` passes.

### S03 — Normalize
- **In →** `SourceDataset` · **Out →** `SourceDataset`
- **What it does:** cleans *values* — trims cells and turns amount columns into exact
  `Decimal` text (no floats, ever). It assigns **no** accounting meaning yet.
- **Guards:** an amount that isn't a finite number.

> **Our invoice:** `total "1000"` is validated as `Decimal("1000")`.

### S04 — Classify
- **In →** `SourceDataset` · **Out →** `ClassifiedTxn[]`
- **What it does:** decides each transaction's **Tally voucher type** and attaches an
  explicit **confidence** (1.0 when the role maps directly). It reads each row into a
  classified transaction carrying the id, signed amount, and party id.
- **Guards:** empty document id · unparseable amount · unknown type.

> **Our invoice:** `ClassifiedTxn(type="Sales", confidence=1.0, number="INV1",
> amount=1000, party_id="C1", debit="$PARTY", credit="Sales Account")`.
> *(`$PARTY` is a placeholder meaning "the party ledger for this row".)*

### S05 — Map ledgers
- **In →** `ClassifiedTxn[]` · **Out →** `MappedTxn[]`
- **What it does:** resolves every account name to a **concrete Tally ledger** through a
  single mapping point — the `$PARTY` placeholder becomes the customer's ledger name (from
  `Contacts`), control accounts pass through (or via overrides).
- **Guards:** a party/account that can't be resolved → fail loud (so Tally never sees a
  ledger that doesn't exist).

> **Our invoice:** `MappedTxn(debit_ledger="Acme & Co", credit_ledger="Sales Account",
> party_ledger="Acme & Co", amount=1000)`.

### S06 — Canonicalize  *(the seam)*
- **In →** `MappedTxn[]` · **Out →** `CanonicalBatch`
- **What it does:** builds **balanced double-entry vouchers**. Magnitude lives in `amount`
  (always positive); direction lives in `is_debit`. A negative source amount (refund)
  becomes a positive magnitude with the two sides **swapped**.
- **Guards (enforced by the model itself):** debit total = credit total · amount > 0 ·
  unique voucher numbers · party ledger must be one of the entries.

> **Our invoice:** `CanonicalVoucher(type="Sales", number="INV1", party_ledger="Acme & Co",
> entries=[ Dr "Acme & Co" 1000 , Cr "Sales Account" 1000 ])`.
> **Below this line, nothing knows the data came from Zoho.**

### S07 — Validate
- **In →** `CanonicalBatch` · **Out →** `ValidationReport`
- **What it does:** checks **business rules** and returns a list of issues (it reports; it
  doesn't throw): date inside the company financial year, confidence floor, etc. The
  orchestrator **blocks** if any issue is an `error`.
- **Note:** structural truths (balance, uniqueness) are already guaranteed by S06's model,
  so they aren't re-checked here.

### S08 — Enrich  *(optional)*
- **In →** `CanonicalBatch` · **Out →** `EnrichedBatch`
- **What it does:** adds **bill-wise allocations** to party entries (a "New Ref" equal to
  the invoice amount) — Tally tracks customer ledgers bill-by-bill. Purely **additive and
  balance-preserving**.

> **Our invoice (with `--enrich`):** the `Acme & Co` line gains a bill allocation
> `New Ref "INV1" = 1000`.

### S09 — Number
- **In →** `CanonicalBatch` · **Out →** `NumberedBatch`
- **What it does:** guarantees voucher numbers are **unique within the file** (Tally
  rejects a whole import on a duplicate). *Tally itself owns the final stored number* — its
  voucher types auto-number — so we don't fight it; we just keep the file valid.

### S10 — Reconcile  *(optional)*
- **In →** `CanonicalBatch` + `PriorImportState` · **Out →** `ReconciliationResult`
- **What it does:** flags vouchers **already imported** (matched on stable source identity,
  not Tally's auto-number) so re-runs are safe. The pipeline can drop matched ones.

### S11 — Review  *(optional, human-in-the-loop)*
- **In →** `CanonicalBatch` + `ValidationReport` + `ReviewPolicy` · **Out →** `ReviewQueue`
- **What it does:** queues low-confidence or flagged vouchers for a person; `apply_decisions`
  keeps only the **explicitly approved** ones (silence = withhold, never auto-approve).

### S12 — Emit  *(the Tally adapter)*
- **In →** `CanonicalBatch` · **Out →** `masters.xml` + `vouchers.xml`
- **Three sub-steps:**
  1. **Map** canonical → Tally model, applying the **sign rule** (debit → negative + `Yes`).
  2. **Serialize** with `lxml` (never string-concatenation, so everything is auto-escaped);
     output is UTF-8, declared, pretty-printed, **byte-stable**.
  3. **Validate** the bytes against the §2 contract (and masters against their structure).
- It also derives the **ledger masters** — every distinct ledger the batch touches, each
  under its Tally group (`Acme & Co → Sundry Debtors`, `Sales Account → Sales Accounts`).

> **Our invoice, as emitted:**
> ```xml
> <VOUCHER VCHTYPE="Sales" ACTION="Create">
>   <DATE>20260401</DATE>
>   <VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>
>   <VOUCHERNUMBER>INV1</VOUCHERNUMBER>
>   <PARTYLEDGERNAME>Acme &amp; Co</PARTYLEDGERNAME>
>   <ALLLEDGERENTRIES.LIST>
>     <LEDGERNAME>Acme &amp; Co</LEDGERNAME>
>     <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
>     <AMOUNT>-1000.00</AMOUNT>
>   </ALLLEDGERENTRIES.LIST>
>   <ALLLEDGERENTRIES.LIST>
>     <LEDGERNAME>Sales Account</LEDGERNAME>
>     <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
>     <AMOUNT>1000.00</AMOUNT>
>   </ALLLEDGERENTRIES.LIST>
> </VOUCHER>
> ```

### (Read side) — Parse import result
After Tally imports, it returns an `IMPORTRESULT` (created / altered / ignored / errors).
`parse_import_result` reads it back — decoding **UTF-16** and tolerating Tally's embedded
control characters — so a caller can confirm `errors == 0 and ignored == 0`.

---

## The full journey of `INV1`

| Stage | `INV1` looks like… |
|-------|--------------------|
| S01 ingest | bytes of `Sales_Invoices.csv`, tagged `SALES_INVOICES` |
| S02 parse | row `("INV1","C1","1000")`; `C1` joins to `Contacts` |
| S03 normalize | `total → Decimal("1000")` |
| S04 classify | `Sales`, confidence `1.0`, party `C1`, `Dr $PARTY / Cr Sales Account` |
| S05 map | `$PARTY → "Acme & Co"` |
| S06 canonicalize | balanced voucher: `Dr Acme & Co 1000 / Cr Sales Account 1000` |
| S07 validate | date in FY ✓, confidence ✓ → no errors |
| S08 enrich *(opt)* | `Acme & Co` line gains `New Ref "INV1" = 1000` |
| S09 number | `INV1` is unique ✓ |
| S12 emit | the `<VOUCHER>` XML above; `Acme & Co` master under `Sundry Debtors` |

And the two files land for TallyPrime: **`masters.xml`** (create `Acme & Co`,
`Sales Account`, …) imported **first**, then **`vouchers.xml`** imported **second**.

---

## Where to look in the code

| Concept | File |
|---|---|
| The canonical model (the seam) | `src/tallyimporter/contracts/canonical.py` |
| The Tally target + response model | `src/tallyimporter/contracts/tally.py` |
| Adapter data types + the source profile shape | `src/tallyimporter/contracts/source.py` |
| Zoho specifics (as data) | `src/tallyimporter/profiles/zoho.py` |
| Each stage | `src/tallyimporter/stages/sNN_*/…` |
| The orchestrator | `src/tallyimporter/pipeline.py` |
| The Tally XML contract (the spec) | `PHASE_1_BUILD.md` §2 |
| What real TallyPrime confirmed | `smoke_import/ROUNDTRIP_FINDINGS.md` |
