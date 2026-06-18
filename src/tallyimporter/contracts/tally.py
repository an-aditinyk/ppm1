"""Tally target model + import-result model (frozen spine).

Mirrors the verified Tally import XML contract (§2). Amounts here are *signed* as
they appear in the XML. The per-voucher zero-sum invariant is enforced loudly.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tallyimporter.contracts.errors import BalanceError, MoneyError
from tallyimporter.core.money import parse_money

_FROZEN = ConfigDict(frozen=True, extra="forbid")

Action = Literal["Create", "Alter", "Cancel", "Delete"]


def _coerce_signed(value: object) -> Decimal:
    if isinstance(value, str | int | Decimal) and not isinstance(value, bool):
        try:
            return parse_money(value)
        except MoneyError as exc:
            raise ValueError(str(exc)) from exc
    raise ValueError(f"amount must be str/int/Decimal, not {type(value).__name__}")


class TallyBillAllocation(BaseModel):
    model_config = _FROZEN

    name: str = Field(min_length=1)
    bill_type: str = Field(min_length=1)  # Tally BILLTYPE, e.g. "New Ref"
    amount: Decimal  # SIGNED, matches the parent entry's sign

    @field_validator("amount", mode="before")
    @classmethod
    def _validate_amount(cls, value: object) -> Decimal:
        return _coerce_signed(value)


class TallyLedgerEntry(BaseModel):
    model_config = _FROZEN

    ledger_name: str = Field(min_length=1)
    is_deemed_positive: bool  # True => "Yes"
    amount: Decimal  # SIGNED, as it appears in XML
    bill_allocations: tuple[TallyBillAllocation, ...] = ()

    @field_validator("amount", mode="before")
    @classmethod
    def _validate_amount(cls, value: object) -> Decimal:
        return _coerce_signed(value)


class TallyVoucher(BaseModel):
    model_config = _FROZEN

    action: Action = "Create"
    vch_type: str = Field(min_length=1)
    date: date
    voucher_number: str = Field(min_length=1)
    narration: str | None
    entries: tuple[TallyLedgerEntry, ...]
    party_ledger: str | None = None

    @field_validator("entries")
    @classmethod
    def _non_empty(cls, value: tuple[TallyLedgerEntry, ...]) -> tuple[TallyLedgerEntry, ...]:
        if not value:
            raise ValueError("voucher must have at least one ledger entry")
        return value

    @model_validator(mode="after")
    def _zero_sum(self) -> TallyVoucher:
        total = sum((e.amount for e in self.entries), start=Decimal("0"))
        if total != Decimal("0"):
            raise BalanceError(
                f"voucher {self.voucher_number!r} signed amounts sum to {total}, expected 0"
            )
        return self


class TallyImportEnvelope(BaseModel):
    model_config = _FROZEN

    company_name: str = Field(min_length=1)
    vouchers: tuple[TallyVoucher, ...]


class TallyLedgerMaster(BaseModel):
    """One ledger to create under a parent group. Minimal structure confirmed by a
    real TallyPrime round-trip (smoke_import/ROUNDTRIP_FINDINGS.md): NAME.LIST/NAME +
    PARENT + ACTION are sufficient; Tally auto-populates the rest."""

    model_config = _FROZEN

    name: str = Field(min_length=1)
    parent: str = Field(min_length=1)  # a Tally predefined group
    action: Action = "Create"


class TallyMastersEnvelope(BaseModel):
    """An "All Masters" import envelope creating ledgers (§2.2 rule 2: ID=All Masters)."""

    model_config = _FROZEN

    company_name: str = Field(min_length=1)
    ledgers: tuple[TallyLedgerMaster, ...]

    @field_validator("ledgers")
    @classmethod
    def _unique_non_empty(
        cls, value: tuple[TallyLedgerMaster, ...]
    ) -> tuple[TallyLedgerMaster, ...]:
        if not value:
            raise ValueError("masters envelope must contain at least one ledger")
        names = [m.name for m in value]
        if len(names) != len(set(names)):
            raise ValueError("duplicate ledger names in masters envelope")
        return value


class TallyExport(BaseModel):
    """The pair of import files a fresh Tally company needs: masters first, then
    vouchers. Both have already passed their structural validators."""

    model_config = _FROZEN

    masters_xml: bytes
    vouchers_xml: bytes


class TallyImportResult(BaseModel):
    """Response target (§2.3); the parser arrives in a later stage."""

    model_config = _FROZEN

    created: int
    altered: int
    last_vch_id: int
    last_m_id: int
    combined: int
    ignored: int
    errors: int
