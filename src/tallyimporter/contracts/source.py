"""Shared source-adapter contracts (frozen spine).

Inter-stage data-transfer types for the adapter region S01-S05 live here, in
`contracts/`, not in any stage package — stages may import `contracts/` and `core/`
but never each other (import-linter). All types are source-agnostic in *shape*:
source specifics ride as data (column names, profile tables), never as named fields.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class ArtifactRole(StrEnum):
    """Accounting role of a source artifact — named after accounting reality, not after
    any one source's file names. Adapters map their own files to these roles."""

    CUSTOMERS = "customers"
    SUPPLIERS = "suppliers"
    ITEMS = "items"
    SALES_INVOICES = "sales_invoices"
    SALES_INVOICE_LINES = "sales_invoice_lines"
    CUSTOMER_RECEIPTS = "customer_receipts"
    BILLS = "bills"
    BILL_LINES = "bill_lines"
    SUPPLIER_PAYMENTS = "supplier_payments"
    CREDIT_NOTES = "credit_notes"
    JOURNALS = "journals"
    BANK_TRANSACTIONS = "bank_transactions"
    TAX_TRANSACTIONS = "tax_transactions"
    SALES_ORDERS = "sales_orders"
    PURCHASE_ORDERS = "purchase_orders"
    INVENTORY_MOVEMENTS = "inventory_movements"
    INVENTORY_ADJUSTMENTS = "inventory_adjustments"


# ── S01 ingest input / output ────────────────────────────────────────────────────


class IngestRequest(BaseModel):
    """Imperative-shell input for S01: where to read a source export from."""

    model_config = _FROZEN

    source_system: str = Field(min_length=1)
    location: str = Field(min_length=1)


class RawArtifact(BaseModel):
    model_config = _FROZEN

    role: ArtifactRole
    content: bytes
    encoding: str = Field(default="utf-8", min_length=1)
    # Provenance only — downstream MUST NOT branch on it (S01 D3).
    source_name: str | None = None


class IngestedArchive(BaseModel):
    model_config = _FROZEN

    source_system: str = Field(min_length=1)
    artifacts: tuple[RawArtifact, ...]
    # Recognized-but-unexpected entries: recorded, not consumed (S01 D5).
    extra_artifacts_seen: tuple[str, ...] = ()


# ── S02 parse / S03 normalize output ─────────────────────────────────────────────


class SourceTable(BaseModel):
    """One artifact parsed to a header + rows. After S02 the headers are the source's
    own column names; after S03 they are canonical names (per the source profile)."""

    model_config = _FROZEN

    role: ArtifactRole
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


class SourceDataset(BaseModel):
    model_config = _FROZEN

    source_system: str = Field(min_length=1)
    tables: tuple[SourceTable, ...]


# ── Source profile (X3): per-source behavior as data, not code ───────────────────


class TransactionTemplate(BaseModel):
    """How to turn one transaction artifact's rows into a balanced voucher.

    `debit_account` / `credit_account` name the fixed contra ledgers; the sentinel
    ``"$PARTY"`` means "the party ledger resolved for this row". A negative source
    amount swaps the two sides (input adaptation, §5.1).
    """

    model_config = _FROZEN

    role: ArtifactRole
    voucher_type: str = Field(min_length=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    id_column: str = Field(min_length=1)
    amount_column: str = Field(min_length=1)
    party_column: str | None = None
    party_role: ArtifactRole | None = None
    debit_account: str = Field(min_length=1)
    credit_account: str = Field(min_length=1)


class PartyTable(BaseModel):
    """How to read a party (customer/supplier) artifact: which columns hold id and name."""

    model_config = _FROZEN

    role: ArtifactRole
    id_column: str = Field(min_length=1)
    name_column: str = Field(min_length=1)


class SourceProfile(BaseModel):
    """The complete per-source adapter configuration (the Zoho profile is one value).

    - `file_roles`: source artifact name → role (S01 dispatch table).
    - `required_roles`: roles whose absence fails ingest (S01 D5).
    - `parties` / `transactions`: how S03-S06 interpret each role's rows.
    - `ledger_overrides`: source account name → Tally ledger name (S05 single map point).
    """

    model_config = _FROZEN

    source_system: str = Field(min_length=1)
    file_roles: tuple[tuple[str, ArtifactRole], ...]
    required_roles: tuple[ArtifactRole, ...]
    parties: tuple[PartyTable, ...]
    transactions: tuple[TransactionTemplate, ...]
    ledger_overrides: tuple[tuple[str, str], ...] = ()
    # Ledger-master creation: control account name -> Tally parent group; everything
    # else (e.g. party ledgers) falls back to `default_ledger_group`.
    ledger_groups: tuple[tuple[str, str], ...] = ()
    default_ledger_group: str = "Sundry Debtors"


# ── S04 classify / S05 map-ledgers output ────────────────────────────────────────

# Sentinel in a template's debit/credit account meaning "the party ledger for this row".
PARTY_SENTINEL = "$PARTY"


class ClassifiedTxn(BaseModel):
    """One transaction row classified to a voucher type (S04 output). `amount` is the
    *signed* source amount; the debit/credit accounts may still carry PARTY_SENTINEL."""

    model_config = _FROZEN

    role: ArtifactRole
    voucher_type: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    voucher_number: str = Field(min_length=1)
    amount: Decimal
    party_id: str | None
    debit_account: str = Field(min_length=1)
    credit_account: str = Field(min_length=1)


class MappedTxn(BaseModel):
    """A classified transaction with both sides resolved to concrete Tally ledger
    names (S05 output). `amount` is still the signed source amount; sign is applied at
    canonicalization (S06)."""

    model_config = _FROZEN

    voucher_type: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    voucher_number: str = Field(min_length=1)
    amount: Decimal
    debit_ledger: str = Field(min_length=1)
    credit_ledger: str = Field(min_length=1)
