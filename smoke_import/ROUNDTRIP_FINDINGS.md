# TallyPrime Round-Trip Validation — Findings

Real-instance validation of the §2 contract: data emitted by our serializer was
imported into TallyPrime (zero errors) and then **exported back out by Tally**. This
records what round-tripped faithfully and what Tally added/changed. Source artifacts
(not committed — large, UTF-16): a full `All Masters` export (1000 ledgers), and a
single `Day Book` voucher export (a Payment).

**Provenance / cross-device note.** The voucher export was produced on an
**independent machine** by a coworker who imported our files into *his own* active
company (`Test1`) and exported one Day Book voucher. So this is also a **cross-device,
cross-company** validation. Two consequences: (a) the import landed in his **active**
company despite our envelope's `SVCURRENTCOMPANY` — Tally imports into the selected
company and does not hard-bind to that tag; (b) the voucher-number override (below)
reproduces on an independent install, so it is real Tally behavior, not a local fluke.

## Verdict: the §2 voucher contract round-trips faithfully ✅

Every field our emitter controls came back from Tally **unchanged**, including the
exact §2.2 rule-5 sign convention:

| Field (we emit) | We sent | Tally stored | Match |
|---|---|---|---|
| `DATE` | `20260401` | `20260401` | ✅ (YYYYMMDD) |
| `VOUCHERTYPENAME` | `Payment` | `Payment` | ✅ |
| `ALLLEDGERENTRIES.LIST` #1 | `Accounts Payable` / `Yes` / `-6232.00` | identical | ✅ debit = Yes + negative |
| `ALLLEDGERENTRIES.LIST` #2 | `Bank Account` / `No` / `6232.00` | identical | ✅ credit = No + positive |
| signed `AMOUNT` sum | `0.00` | `0.00` | ✅ zero-sum |
| `AMOUNT` format | 2dp | `-6232.00` / `6232.00` | ✅ |

So Tally not only **accepted** the import — it **persisted our structure byte-faithfully**
and re-emitted it with our exact tags and signs. This is the real gate passing.

## Masters round-trip

- All **998** ledgers we created are present, **0 missing, 0 wrong-parent** (correct
  Tally predefined groups). The 2 extras are Tally's predefined `Cash` and
  `Profit & Loss A/c`.
- Our **minimal 3-tag `LEDGER`** (`NAME.LIST/NAME` + `PARENT` + `ACTION="Create"`) is
  **sufficient**: Tally created each ledger and auto-populated ~185 default fields.
  → The minimal master structure in `masters.xml` is now grounded by a real Tally
  round-trip; no master tags need adding.

## What Tally adds on its own (none of it required for import)

- **Envelope frame:** Tally *exports* as `TALLYREQUEST=Import Data` →
  `IMPORTDATA/REQUESTDESC/REQUESTDATA` (and even tags a voucher export
  `REPORTNAME=All Masters`). Our *import* envelope (`Import/Data/Vouchers` with
  `DESC/DATA`) was accepted regardless — both frames are import-valid.
- **VOUCHER attributes:** `REMOTEID`, `VCHKEY`, `SENDERID`, `OBJVIEW`, plus `GUID` —
  Tally-internal identity, not import inputs.
- **Derived/context fields:** `PARTYLEDGERNAME=Accounts Payable` (Tally inferred the
  party = debit ledger), `CMPGSTSTATE=Odisha`, `CMPGSTREGISTRATIONTYPE=Regular`,
  `EFFECTIVEDATE`, `PERSISTEDVIEW`, and ~148 boolean flags defaulted to `No`, plus
  many empty `*.LIST` allocation containers (`BILLALLOCATIONS.LIST`,
  `BANKALLOCATIONS.LIST`, …). A trailing `COMPANY/REMOTECMPINFO.LIST` message.

## Open items (future phases — not Phase 1 contract defects)

1. **Voucher numbering is overridden.** We emit source IDs as `VOUCHERNUMBER`
   (e.g. `Ven000001`), but Tally stored **`19`** with `NUMBERINGSTYLE=Auto Retain` —
   the predefined Payment/Receipt/Sales types use automatic numbering, so Tally
   renumbered (reproduced on an independent device/company).
   **Decision: let Tally auto-number (accepted).** We do not force Manual numbering
   on the voucher types — Tally's automatic voucher number is authoritative. The
   emitter still sets a unique `VOUCHERNUMBER` per §2.2 rule 8 (the import file must
   not contain duplicates), but Tally may override it on auto-numbered voucher types,
   and that's fine. Consequence: the source id is not preserved as the Tally voucher
   number; if source↔Tally traceability is ever required, carry the source id in a
   reference field/UDF — explicitly **not** pursued for now.
2. **Party ledger.** Tally derived `PARTYLEDGERNAME`; emitting it explicitly on
   Payment/Receipt may be needed once bill-wise allocation is added.
3. **Bill allocations.** Customer/vendor ledgers default to `ISBILLWISEON=Yes`;
   posting against open bills will need `BILLALLOCATIONS.LIST` (Phase ≥2).
4. **Response/export parsing (§2.3).** Tally writes **UTF-16** and embeds control
   chars (`&#4; Not Applicable`, a mangled ₹) that break a strict XML parser. The
   response-handling stage must decode UTF-16 and use a recovering parser. Our
   emitter stays UTF-8 and is unaffected.

## Bottom line

The Phase 1 §2 voucher contract and the minimal master structure are **validated
end-to-end against a real TallyPrime instance** — accepted on import and round-tripped
faithfully on export. The open items above are forward-looking (numbering strategy,
party/bill allocations, response parsing), not corrections to Phase 1.
