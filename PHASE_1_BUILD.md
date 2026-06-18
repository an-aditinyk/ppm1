# TallyImporter — Phase 1 (M0 Foundations)

This is the authoritative Phase 1 build spec. The frozen Tally XML contract in §2 is
the source of truth referenced by `.cursorrules` and the code.

## 1. Objective

Stand up the foundation and prove the contract spine end-to-end with one real
vertical slice: a deterministic, source-agnostic Canonical model → verified Tally
import XML serializer, fully tested with golden-file snapshots.

## 2. VERIFIED Tally import XML contract (build to this exactly)

Source: Tally official Developer Reference, "Case Study I – XML Request and Response
Formats" and TallyHelp Import/Export Masters & Vouchers.

### 2.1 Voucher import envelope (the Phase 1 target)

```xml
<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Import</TALLYREQUEST>
    <TYPE>Data</TYPE>
    <ID>Vouchers</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVCURRENTCOMPANY>ACME Pvt Ltd</SVCURRENTCOMPANY>
      </STATICVARIABLES>
    </DESC>
    <DATA>
      <TALLYMESSAGE xmlns:UDF="TallyUDF">
        <VOUCHER VCHTYPE="Payment" ACTION="Create">
          <DATE>20080402</DATE>
          <NARRATION>Ch. No. Tested</NARRATION>
          <VOUCHERTYPENAME>Payment</VOUCHERTYPENAME>
          <VOUCHERNUMBER>1</VOUCHERNUMBER>
          <ALLLEDGERENTRIES.LIST>
            <LEDGERNAME>Conveyance</LEDGERNAME>
            <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
            <AMOUNT>-12000.00</AMOUNT>
          </ALLLEDGERENTRIES.LIST>
          <ALLLEDGERENTRIES.LIST>
            <LEDGERNAME>Bank of India</LEDGERNAME>
            <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
            <AMOUNT>12000.00</AMOUNT>
          </ALLLEDGERENTRIES.LIST>
        </VOUCHER>
      </TALLYMESSAGE>
    </DATA>
  </BODY>
</ENVELOPE>
```

### 2.2 Hard rules (each encoded as a validation + a test)

1. Root element is `ENVELOPE`. Order is fixed: `HEADER` then `BODY`; `BODY` is `DESC`
   then `DATA`.
2. Header for voucher import: `VERSION=1`, `TALLYREQUEST=Import`, `TYPE=Data`,
   `ID=Vouchers`. For masters: `ID=All Masters`.
3. Date is `YYYYMMDD` (e.g. `20260115`). Reject any other format. Dates must fall
   within the target company financial year (validation hook; enforcement value is
   configurable).
4. Each ledger line is its own `<ALLLEDGERENTRIES.LIST>` element containing exactly
   `LEDGERNAME`, `ISDEEMEDPOSITIVE`, `AMOUNT` (bill allocations / GST extend this
   later — not in Phase 1).
5. Sign convention (verified from Tally's Payment example):
   - Debit side → `ISDEEMEDPOSITIVE = Yes`, `AMOUNT` is negative.
   - Credit side → `ISDEEMEDPOSITIVE = No`, `AMOUNT` is positive.
   - The signed `AMOUNT` values within a single voucher must sum to exactly 0. Fail
     loud otherwise.
6. `AMOUNT` is rendered with 2 decimal places (`-12000.00`). Use `Decimal`, never
   float. Round half-up to 2dp at the serialization boundary only.
7. XML-escape `&`, `<`, `>`, `"` in all text values. The serializer guarantees this
   (uses `lxml`, never hand-concatenated strings).
8. `VOUCHERNUMBER` values must be unique within a batch — Tally rejects an entire
   import file on duplicate voucher numbers. Validate uniqueness and fail loud.
9. `VCHTYPE` / `VOUCHERTYPENAME` must match a Tally voucher type name; `LEDGERNAME`
   must match an existing Tally ledger name. Phase 1 trusts canonical names as-is but
   routes them through a single mapping point for later validation.
10. Action semantics: `ACTION="Create"` for new. `Alter`/`Cancel`/`Delete` identify
    the target voucher via `DATE`, `TAGNAME`, `TAGVALUE`, `VCHTYPE`. Phase 1
    implements Create only, but the model carries an `action` field so the serializer
    is forward-compatible.
11. Tag/attribute names are effectively case-insensitive in Tally; our output uses one
    canonical casing (uppercase tags, `VCHTYPE`/`ACTION` attributes) and never relies
    on Tally's leniency.

### 2.3 Import response shape (modelled now, parsed in a later stage)

```xml
<ENVELOPE><HEADER><VERSION>1</VERSION><STATUS>1</STATUS></HEADER>
  <BODY><DATA><IMPORTRESULT>
    <CREATED>2</CREATED><ALTERED>0</ALTERED><LASTVCHID>119</LASTVCHID>
    <LASTMID>0</LASTMID><COMBINED>0</COMBINED><IGNORED>0</IGNORED><ERRORS>0</ERRORS>
  </IMPORTRESULT></DATA></BODY>
</ENVELOPE>
```

A frozen `TallyImportResult` model captures this now (no parser yet).

## Definition of Done

See §1 of the task and `IMPLEMENTATION_PLAN.md`. Phase 1 is complete when the
scaffold matches the spec, `make check` is green (ruff, mypy strict, import-linter,
pytest with ≥90% coverage), the contract spine + mapper + serializer + validator are
implemented and pure, golden snapshots match byte-for-byte, the zero-sum property
holds, and CI is green on a clean clone.
