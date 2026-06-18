# Build Sheets — Index, Product Synthesis & Cross-Cutting Decisions

This folder holds one build sheet per pipeline stage (S01–S12). Each sheet is a
**design spec**: single responsibility, exact signatures, invariants, fail-loud
behavior, decisions (verdict + rationale), DoD with tests, and any **contract gap** it
implies. Build sheets are **doc-only**; they never modify `contracts/`. Contract changes
are a separate reviewed step.

---

## 1. What the product is (final-state understanding)

**TallyImporter turns an accounting system's data export into a verified TallyPrime
import file.** Source in (Zoho Books today; Busy/others later) → **one source-agnostic
canonical accounting model** → **Tally import XML that TallyPrime accepts**.

```
Zoho export ZIP ─► [S01..S05  source-adapter region] ─► CanonicalBatch ─► [S06..S12  source-agnostic spine] ─► Tally XML
                    (knows the source)                  (the seam)         (knows Tally; never the source)
```

- The **canonical model** (`contracts/canonical.py`) is the architectural seam: above it,
  source-shaped data; below it, a source-neutral double-entry accounting batch.
- The **Tally contract** (`PHASE_1_BUILD.md` §2) is the output target — verified against a
  real TallyPrime instance (see `smoke_import/ROUNDTRIP_FINDINGS.md`).
- Determinism, immutability, pure-core/imperative-shell, fail-loud boundaries, and
  explicit confidence scoring hold across every stage (IMPLEMENTATION_PLAN.md).

## 2. What Phase 1 (M0 Foundations) actually delivered — DONE

Phase 1 was **never "all 12 stages"**. It was the foundation + one real vertical slice:

- Repo scaffold, tooling gates (ruff, mypy strict, import-linter, pytest ≥90%), CI.
- The **frozen contract spine**: `CanonicalBatch` + Tally target model + `TallyImportResult`.
- The **S12 emit slice**, implemented and pure: `canonical_to_tally` mapper +
  `serialize_envelope` + `validate_tally_xml`, with golden + property tests.
- **Real-instance validation:** emitted XML imported into TallyPrime with zero errors and
  round-tripped faithfully (masters: 998/998 ledgers; a voucher: structure + §2.2 signs +
  amounts + dates identical on export). See `smoke_import/`.
- Stages **S01–S11 exist only as `contracts.py` boundary stubs** — no transformation logic.

**Phase 1 is complete.** These build sheets are the **design backlog for Phase 2+** —
the specs to implement S01–S11 and extend S12. Authoring them changes no code.

## 3. Cross-cutting decisions (apply to every sheet)

These are decided here so the sheets don't each re-litigate them. Verdict + rationale.

**X1 — Source knowledge lives in the adapter region S01–S05; the spine S06–S12 is
source-agnostic.**
- *Verdict:* everything that "knows Zoho" is confined to S01–S05. From `CanonicalBatch`
  (S06 output) onward, no stage may reference a source concept.
- *Rationale:* matches the canonical-model seam and the S01 framing (Zoho adapter). A Busy
  pipeline reuses S06–S12 unchanged.

**X2 — Inter-stage *contracts* are source-agnostic in shape; source specifics ride as
data, not as contract structure.**
- *Verdict:* the boundary types (e.g. `SourceRecord.fields`) are generic containers.
  Source column names appear only as *values/keys inside data*, never as named contract
  fields. The leak rule (S01 §6.2) generalizes: a field that exists only because Zoho
  exists is a leak; opaque data carrying Zoho strings is not.
- *Rationale:* lets one contract serve all sources; a new source needs new *data/profiles*,
  not new contract shapes.

**X3 — Per-source behavior is configuration (a "source profile"), not branching code,
wherever possible.**
- *Verdict:* field renames (S03), classification rules (S04), and ledger maps (S05) are
  expressed as **source-profile data** consumed by generic stage logic. Structural source
  knowledge that can't be data — unzip layout (S01), CSV parsing (S02 is generic anyway) —
  stays in the adapter implementation, dispatched by `source_system`.
- *Rationale:* concentrates the hallucination/leak risk into reviewable data tables and
  keeps stage code generic and testable. ⚠ *Judgment call — flagged for review.*

**X4 — Typed errors descend from a shared stage-error base** (`stage`, `code`, `message`,
`detail`) added to `contracts/errors.py` (per S01 D4). Every stage's fail-loud errors
subclass it. *Required contract change, separate step.*

**X5 — Tally is authoritative for voucher numbering** (per `ROUNDTRIP_FINDINGS.md`). The
pipeline assigns unique numbers for batch validity (§2.2 rule 8); Tally may override on
import, accepted. Shapes S09's scope.

**X6 — Money is `Decimal`, magnitude-positive at canonical (§5.1); sign is applied only by
the S12 mapper (§2.2 rule 5).** No `float` in any money path, any stage.

## 4. Stage status & sheet index

| Stage | Sheet | Region | Status |
|---|---|---|---|
| S01 ingest | `S01_INGEST.md` | adapter | Design locked (D1–D6); contract change pending |
| S02 parse | `S02_PARSE.md` | adapter | Design; owns referential-integrity (S01 D2) |
| S03 normalize | `S03_NORMALIZE.md` | adapter | Design |
| S04 classify | `S04_CLASSIFY.md` | adapter | Design |
| S05 map ledgers | `S05_MAP_LEDGERS.md` | adapter | Design |
| S06 canonicalize | `S06_CANONICALIZE.md` | **seam** | Design |
| S07 validate | `S07_VALIDATE.md` | spine | Design |
| S08 enrich | `S08_ENRICH.md` | spine | **Implemented** (bill allocations + party ledger; opt-in) |
| S09 number | `S09_NUMBER.md` | spine | **Implemented** (scoped by X5) |
| S10 reconcile | `S10_RECONCILE.md` | spine | **Implemented** (prior-import state; opt-in) |
| S11 review | `S11_REVIEW.md` | spine | **Implemented** (human-loop gate; out-of-band) |
| S12 emit | `S12_EMIT.md` | spine | **Implemented** (vouchers + masters + response parse) |

All 12 stages are implemented. The default pipeline runs S01→S07→S09→S12 (the validated
posting path); S08/S10 are opt-in on `run_pipeline_full`; S11 is a human gate used
out-of-band. The Phase-2 contract extensions (`docs/CONTRACT_EXTENSIONS_PHASE2.md`) are
accepted and applied.

## 5. Required contract changes already surfaced (separate reviewed step — NOT done)

Aggregated from the sheets, for the contract-review session:
1. **Shared stage-error base** in `contracts/errors.py` (X4 / S01 D4).
2. **Reshape S01 boundary** (role + immutable bytes + provenance + extra-artifacts record).
3. **S02 boundary** must carry artifact **role** + row provenance + referential-integrity
   outcome (current `ParsedRecordSet` lacks role).
4. **Canonical extension for S08** (bill allocations, GST detail, party ledger) — the
   round-trip showed customer ledgers default to bill-wise; posting bills will need it.
5. **S10/S11 carriers** for prior-import reconciliation state and review decisions.

None of these are made here. Each sheet flags its own.
