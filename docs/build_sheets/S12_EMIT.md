# S12 — Emit — Build Sheet

> **Status: IMPLEMENTED (Phase 1) + documented gaps.** Doc-only. Inherits X1–X6 (`README.md`).
> This sheet records the **as-built** slice and the gaps the TallyPrime round-trip surfaced.
> No contract/code change here.

## 1. Single responsibility
Turn a `CanonicalBatch` into a **verified Tally import XML** envelope: map canonical → Tally
target model, serialize deterministically, and validate the bytes against §2.2.
**NOT this stage:** any source concept (X1), business validation (S07), numbering policy (S09).

## 2. Position
`S11 approved CanonicalBatch ─►` **S12 emit** `─► EmitResult(envelope, xml bytes)` → TallyPrime

## 3. Signatures (as-built; `s12_emit/`)
```python
def canonical_to_tally(batch: CanonicalBatch) -> TallyImportEnvelope   # mapper.py (pure)
def serialize_envelope(env: TallyImportEnvelope) -> bytes              # serializer.py (lxml)
def validate_tally_xml(xml: bytes) -> None                             # validator.py (§2.2)
```
- Contracts: `EmitRequest(batch)` / `EmitResult(envelope, xml)`; target model
  `TallyImportEnvelope/Voucher/LedgerEntry` (frozen, zero-sum enforced).

## 4. Decisions (as-built, validated)
- **D-S12.1 — sign applied here only (§2.2 rule 5, X6):** `is_deemed_positive = is_debit`;
  `signed = -amount if debit else +amount`. **Confirmed by Tally's own export** (debit `Yes`
  + negative, credit `No` + positive; nets to zero) — `ROUNDTRIP_FINDINGS.md`.
- **D-S12.2 — deterministic bytes:** `lxml`, UTF-8, XML declaration, pretty-printed, fixed
  attribute order, one `TALLYMESSAGE` per voucher; never string-concatenated (auto-escaping).
  Golden + property tests lock byte-stability.
- **D-S12.3 — emitter validates its own output** (`validate_tally_xml`) — necessary but not
  the gate; **TallyPrime acceptance is the gate** (passed, cross-device).

## 5. Fail-loud
| # | Condition | Behavior |
|---|---|---|
| Z1 | Voucher signed amounts ≠ 0 | `BalanceError` (model). |
| Z2 | Output violates any §2.2 rule (root/header/order/date/signs/dup number) | `XmlContractError`. |
| Z3 | Non-finite/`float` amount at render | `MoneyError`. |

## 6. Source-agnostic note
Pure spine→Tally. No source concept appears; input is only `CanonicalBatch`.

## 7. Gaps / future work (flagged, not Phase 1)
- **Masters emission — DONE (now in `src/`).** `s12_emit/masters.py` derives the ledger set
  from a `CanonicalBatch` and assigns parent groups; `serialize_masters` emits the
  `All Masters` envelope (minimal `NAME.LIST/PARENT/ACTION`, grounded by the round-trip) and
  `validate_masters_xml` checks it. `pipeline.run_pipeline_full` returns both files
  (`TallyExport`). Output matches the TallyPrime-validated `masters_full.xml` byte-for-byte.
- **Voucher numbering:** Tally auto-numbers; we accept it (X5). No emitter change.
- **Bill allocations / GST / `PARTYLEDGERNAME`:** not emitted; depend on the S08 canonical
  extension (`README.md` §5 #4).
- **Response parsing (§2.3) — DONE.** `s12_emit/response.py::parse_import_result` decodes by
  BOM (UTF-16/UTF-8) and uses a recovering parser to tolerate Tally's embedded control chars
  (`&#4;`), returning `TallyImportResult`; `is_success` checks `errors==0 and ignored==0`. The
  UTF-8 emitter is unaffected (this is the read side).

## 8. DoD (met for Phase 1) + future tests
- [x] Pure mapper; deterministic serializer; validator covers §2.2 with negatives.
- [x] Golden snapshots byte-stable; property test (signed sums = 0; escaping round-trip).
- [x] Validated on real TallyPrime (imported clean; round-tripped faithfully).
- [x] masters emitter in `src/` (`serialize_masters` + `validate_masters_xml`); both files
      via `run_pipeline_full`.
- [x] response parser (UTF-16 + recovering) for §2.3 (`parse_import_result` / `is_success`).
- [x] `make check` green.
