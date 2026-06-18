# TallyPrime Smoke-Import Kit

> **The gate is TallyPrime accepting this import — not our validator passing.**
> `validate_tally_xml` only proves the bytes match our reading of the §2 contract.
> It cannot prove that reading is *correct*. This kit exists so a human loads the
> XML into a real TallyPrime company and confirms Tally itself accepts it. Treat a
> green `validate_tally_xml` as necessary, never sufficient.

## What's in the kit

| File | What it is |
|------|------------|
| `masters.xml` | "All Masters" envelope creating the 13 ledgers the slice references, each under a Tally **predefined** group. Import this **first**. |
| `vouchers_slice.xml` | 30-voucher `Import / Data / Vouchers` envelope: 9 Sales, 11 Receipt, 10 Payment, including 5 negative-amount **reversal** vouchers. Import this **second**. |
| `build_smoke_kit.py` | Regenerates both files deterministically from the Zoho→Tally run. |

Slice composition (from `vouchers_slice.xml`):
- Voucher types exercised: **Sales, Receipt, Payment** (every type we emit).
- Reversals: **5** (3 Receipt, 2 Payment) — e.g. `Cus000059` posts
  `Dr Accounts Receivable -580.00 / Cr Bank Account 580.00`.
- Posting date for all 30: **20260401** (1-Apr-2026, first day of FY 2026–27).
- All `VOUCHERNUMBER`s unique; all vouchers net to zero.

Ledgers created by `masters.xml` and their groups:

| Ledger | Parent group (Tally predefined) |
|--------|---------------------------------|
| `Sales Account` | `Sales Accounts` |
| `Bank Account` | `Bank Accounts` |
| `Accounts Receivable` | `Sundry Debtors` |
| `Accounts Payable` | `Sundry Creditors` |
| `Customer 189`, `Customer 773`, … (9 contact ledgers) | `Sundry Debtors` |

## Prerequisites

1. **TallyPrime** (this kit is written against TallyPrime; ERP 9 menu names noted below).
2. A **dedicated test company** (do **not** use production books). Create one named
   `Zoho Sample Co` — the envelopes set `SVCURRENTCOMPANY` to that name, and the
   company you import into must be the **selected/active** company.
3. The company's **financial year must include 1-Apr-2026** (i.e. FY 2026–27, books
   beginning on/before 1-Apr-2026). If your test company uses a different FY, either
   set "Beginning of books" accordingly, or regenerate the kit with a date inside
   your FY:
   ```bash
   SMOKE_DATE=20250401 python smoke_import/build_smoke_kit.py   # e.g. FY 2025–26
   ```
4. Note your TallyPrime **application/data folder** — Tally writes the import log to
   `Tally.imp` there, and (depending on config) resolves relative import paths there.
   Use **absolute paths** to the XML files to avoid "file not found".

## Procedure

Import **masters first, then vouchers**. Ledgers must exist before vouchers reference
them, otherwise Tally fails with "ledger does not exist".

### Step 1 — Import masters
1. **Gateway of Tally → Import → Masters** (TallyPrime).
   *(Tally.ERP 9: Gateway of Tally → Import of Data → Masters.)*
2. **File to import**: full path to `masters.xml`.
3. **Behaviour for existing masters**: `Add new / Combine Opening Balances` (or
   "Modify with new data") — on a fresh company nothing exists yet, so all 13 are new.
4. Accept. Watch the on-screen result and then open `Tally.imp` (see logs below).
5. **Verify in UI**: Gateway of Tally → Chart of Accounts → Ledgers → confirm all 13
   ledgers exist under the expected groups.

### Step 2 — Import vouchers
1. **Gateway of Tally → Import → Vouchers** (TallyPrime).
   *(Tally.ERP 9: Gateway of Tally → Import of Data → Vouchers.)*
2. **File to import**: full path to `vouchers_slice.xml`.
3. Accept. Watch the result, then open `Tally.imp`.
4. **Verify in UI**: Display More Reports → Day Book (set period to include
   1-Apr-2026). You should see 30 vouchers. Open the reversal `Cus000059` and confirm
   it shows `Accounts Receivable` debited and `Bank Account` credited.

> Re-running an import is **not** idempotent for vouchers: a second voucher import can
> create duplicates or be rejected on duplicate `VOUCHERNUMBER`, depending on company
> settings. If you need a clean re-run, restore the test company or delete the
> imported day's vouchers first.

## What a clean `Tally.imp` log looks like

`Tally.imp` is appended to on every import. A clean masters import ends with a block
reporting only creations and **zero errors**, e.g.:

```
Importing data from masters.xml ...
Company: Zoho Sample Co
Masters : Created 13, Altered 0, Combined 0, Ignored 0, Errors 0
```

A clean voucher import:

```
Importing data from vouchers_slice.xml ...
Company: Zoho Sample Co
Vouchers : Created 30, Altered 0, Combined 0, Ignored 0, Errors 0
```

This mirrors the `IMPORTRESULT` response (`CREATED` / `ALTERED` / `IGNORED` /
`ERRORS`) in §2.3 of the contract. **The pass condition is `Errors 0` AND the
created counts matching (13 ledgers, 30 vouchers).** `Ignored > 0` or `Errors > 0`
means the import did **not** fully succeed even if Tally didn't pop an error dialog —
always read the log, don't trust the absence of a dialog.

## Failure signatures to watch for

| Symptom in `Tally.imp` / UI | Likely cause | Fix |
|---|---|---|
| `Voucher Type 'XXX' does not exist` / `Could not find Voucher Type` | A `VCHTYPE` / `VOUCHERTYPENAME` doesn't match a Tally voucher type. We emit only the predefined `Sales`, `Receipt`, `Payment`, so this firing is a real contract finding (e.g. a localized/renamed type in your company). | Confirm the voucher types exist (Gateway → Chart of Accounts → Voucher Types) or adjust the emitter's type names. |
| `Ledger 'Customer 189' does not exist` (or any ledger) | Vouchers imported **before** masters, or a name mismatch between `masters.xml` and `vouchers_slice.xml`. | Import `masters.xml` first; ensure exact name match (Tally matches ledgers by name, case/space-sensitive). |
| `Date is out of range` / `… outside the financial year` / vouchers ignored | Company FY does not include `20260401`. | Set the test company's FY to include 1-Apr-2026, or regenerate with `SMOKE_DATE` inside your FY. |
| Dialog `Error in TDL` / `Invalid XML` / `Could not understand the request`, **nothing imported** | Envelope-level rejection: wrong header (`TALLYREQUEST`/`TYPE`/`ID`), malformed structure, or an encoding issue. | This is the most important finding — it means our §2 envelope reading is wrong. Capture the exact dialog text and the `Tally.imp` line and report back. |
| `Errors N` with `N > 0`, or `Ignored N` | Per-voucher/master rejection (unbalanced, unknown parent group, missing required master field). | Read the specific `LINEERROR:` lines in `Tally.imp`; they name the offending voucher/master. |
| Masters rejected: `Could not find Group 'XXX'` / required field missing on `LEDGER` | A parent group name is wrong, or Tally requires more ledger fields than we emit. | See "Master-tag grounding" below — this is exactly what the smoke test is meant to surface. |

## Master-tag grounding (read this)

Our **verified contract (§2)** authoritatively covers the *voucher* import envelope.
For masters it specifies only the envelope frame — `Import / Data / **All Masters**`
(§2.2 rule 2) — which `masters.xml` reuses verbatim from the §2.1 structure
(`HEADER` → `BODY` → `DESC`/`DATA` → `TALLYMESSAGE`).

The `LEDGER` element itself is **not** in our repo's verified docs. `masters.xml`
therefore uses only the **minimal, well-documented** Tally ledger-master tags:

```xml
<LEDGER NAME="Sales Account" ACTION="Create">
  <NAME.LIST><NAME>Sales Account</NAME></NAME.LIST>
  <PARENT>Sales Accounts</PARENT>
</LEDGER>
```

- `NAME` attribute + `NAME.LIST/NAME` — the ledger name (Tally's standard master
  name-list structure).
- `PARENT` — the group; all parents used are Tally **predefined** groups
  (`Sales Accounts`, `Bank Accounts`, `Sundry Debtors`, `Sundry Creditors`).
- `ACTION="Create"` — same action semantics as §2.2 rule 10.

No other master tags are invented or guessed. **If TallyPrime rejects the masters for
a missing field, that is a genuine result of this smoke test** — capture the
`Tally.imp` message and we will add the required tag *with a doc reference* before
promoting any master structure into `src/`.

## Reporting back

Please paste, for each step: the on-screen result line and the matching `Tally.imp`
block (created/altered/ignored/errors), plus any error dialog text verbatim. That log
— not our validator — is the Phase 1 §2 contract gate.
