# S05 — Map Ledgers — Build Sheet

> **Status: DESIGN. Doc-only.** Inherits X1–X6 (`README.md`). No contract/code change here.

## 1. Single responsibility
Resolve every source account/party reference to an **exact Tally ledger name**, through a
**single mapping point** (§2.2 rule 9). One source name → one Tally ledger name.
**NOT this stage:** creating the double-entry (S06), deciding debit/credit (S06), emitting
ledger *masters* (S12/smoke kit), validating the batch (S07).

## 2. Position
`S04 classified records ─►` **S05 map ledgers** `─► records with Tally ledger names ─► S06`

## 3. Signatures (`s05_map_ledgers/contracts.py`)
```python
def map_ledgers(records: ClassifiedRecordSet, table: LedgerMappingTable) -> <MappedRecordSet>: ...
```
- `LedgerMapping(source_name, tally_name)` + `LedgerMappingTable(mappings)` — the single
  mapping point. Resolves party names (customers/suppliers) and the control accounts used in
  our validated run (`Sales Account`, `Bank Account`, `Accounts Receivable`,
  `Accounts Payable`) under their Tally predefined groups.

## 4. Decisions
- **D-S05.1 — one mapping point, table-driven (X3).** All name resolution flows through
  `LedgerMappingTable`; no ad-hoc renaming elsewhere. *Rationale:* §2.2 rule 9 (Tally matches
  ledgers by exact name) — one place to get names right and to later validate against a real
  Tally ledger list.
- **D-S05.2 — unmapped source name = fail loud, not pass-through.** *Rationale:* a silent
  pass-through produces a `LEDGERNAME` Tally rejects with "ledger does not exist" (we saw this
  failure mode in the smoke import). Names must be deliberate.
- **D-S05.3 — Phase 1 trusted canonical names as-is; S05 makes that routing explicit.** It
  does **not** create ledgers; master creation is separate (S12/masters, grounded by the
  round-trip: minimal `NAME.LIST/PARENT/ACTION`).

## 5. Fail-loud
| # | Condition | Behavior |
|---|---|---|
| M1 | Source name absent from the mapping table | Fail loud (name). |
| M2 | Mapping resolves to empty / whitespace Tally name | Fail loud. |
| M3 | Two source names collide onto one Tally ledger when they must differ (or vice-versa) per policy | Fail loud or record, per reviewed policy. |

## 6. Source-agnostic note
Output carries **Tally** ledger names (spine concept). The source→Tally table is data (X3);
a Busy run supplies its own table, same contract.

## 7. Contract gap
The **output type is unspecified** — there is no `MappedRecordSet` stub; only the mapping
*table* exists. A boundary carrying "records with resolved Tally ledger names + voucher type
+ confidence" is needed before S06. Flag as a required contract addition (separate step).

## 8. DoD + tests
- [ ] Pure; deterministic; single mapping point; imports only `contracts/`+`core/`.
- [ ] T: party + control-account names resolve to the expected Tally ledgers.
- [ ] T-M1: unmapped name → fail loud. T-M2: empty target → fail loud.
- [ ] `make check` green.
