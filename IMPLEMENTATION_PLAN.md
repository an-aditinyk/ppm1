# TallyImporter — Implementation Plan

TallyImporter ingests accounting data exported from heterogeneous source systems
(Zoho Books, Busy, etc.) and produces a deterministic, verified Tally import XML
file. The architecture is a linear pipeline of single-responsibility stages that
communicate only through typed boundary contracts.

## Architectural invariants

- **Single responsibility per stage** — each stage does one transformation.
- **Typed inter-stage contracts** — stages exchange Pydantic v2 models declared in
  their `contracts.py`; those reference the frozen spine in `contracts/`.
- **Immutable originals** — models are `frozen=True, extra="forbid"`; a stage never
  mutates its input.
- **Determinism** — same input → byte-identical output. No clocks, no randomness, no
  reliance on dict iteration order in output.
- **Pure core / imperative shell** — transformation logic is pure functions on typed
  models; I/O lives only at the edges (ingest, emit).
- **Source-agnostic canonical model** — all source-specific shapes collapse into one
  `CanonicalBatch` before downstream processing.
- **Explicit confidence scoring** — every canonical voucher carries a confidence value.
- **Fail-loud boundary validation** — every boundary validates and raises a typed
  error on violation; data is never silently coerced or dropped.

## Import constraints (enforced by `.importlinter`)

- `core` and `contracts` may not import `stages`.
- Stage packages may not import one another; they depend only on `contracts/` and
  `core/`.

## The 12 pipeline stages

| Stage | Package | Responsibility |
|-------|---------|----------------|
| S01 | `s01_ingest` | Read raw source artifacts (files/exports) into raw byte/record payloads. |
| S02 | `s02_parse` | Parse raw payloads into structured, source-shaped records. |
| S03 | `s03_normalize` | Normalize encodings, dates, amounts and field names per source. |
| S04 | `s04_classify` | Determine voucher type (Payment/Receipt/Sales/…) per record. |
| S05 | `s05_map_ledgers` | Map source account names to Tally ledger names. |
| S06 | `s06_canonicalize` | Assemble the source-agnostic `CanonicalBatch`. |
| S07 | `s07_validate` | Validate canonical business rules (balance, field presence). |
| S08 | `s08_enrich` | Attach confidence scores and (later) bill allocations / GST. |
| S09 | `s09_number` | Assign / verify unique voucher numbers within the batch. |
| S10 | `s10_reconcile` | Reconcile against existing Tally data / prior imports. |
| S11 | `s11_review` | Gate low-confidence vouchers for human review. |
| S12 | `s12_emit` | Map canonical → Tally model, serialize XML, validate output. |

## Phase 1 (M0 Foundations) scope

Phase 1 stands up the scaffold and proves the contract spine end-to-end with the
S12 vertical slice: `CanonicalBatch` → `canonical_to_tally` → `serialize_envelope`
→ `validate_tally_xml`, with golden-file snapshots and property tests. Stages
S01–S11 exist as `contracts.py` boundary stubs only; their transformation logic
arrives in later phases.
