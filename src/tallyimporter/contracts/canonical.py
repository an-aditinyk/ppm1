"""Source-agnostic canonical model (frozen spine).

Every source system collapses into this shape before downstream processing. Amounts
are positive magnitudes; the debit/credit sign is derived later from ``is_debit``
(see PHASE_1_BUILD.md §5.1). This is the canonical *input* representation and is
deliberately distinct from the signed Tally ``AMOUNT`` of §2.2, which the mapper
derives. A raw negative/zero ``amount`` is malformed input and raises loudly here;
adapting signed source amounts into magnitude + ``is_debit`` is the ingest stage's
job, not the spine's.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tallyimporter.contracts.errors import MoneyError
from tallyimporter.core.money import parse_money

_FROZEN = ConfigDict(frozen=True, extra="forbid")


def _coerce_amount(value: object) -> Decimal:
    """Parse an amount, rejecting floats and non-finite values."""
    if isinstance(value, str | int | Decimal) and not isinstance(value, bool):
        try:
            return parse_money(value)
        except MoneyError as exc:
            raise ValueError(str(exc)) from exc
    raise ValueError(f"amount must be str/int/Decimal, not {type(value).__name__}")


PositiveAmount = Annotated[Decimal, Field(gt=0)]

BillKind = Literal["new", "against", "advance", "on_account"]


class BillAllocation(BaseModel):
    """A bill-wise allocation of a party ledger entry (§ Phase-2 enrichment). `amount`
    is a positive magnitude; allocations of an entry sum to the entry amount."""

    model_config = _FROZEN

    reference: str = Field(min_length=1)
    kind: BillKind
    amount: PositiveAmount

    @field_validator("amount", mode="before")
    @classmethod
    def _validate_amount(cls, value: object) -> Decimal:
        return _coerce_amount(value)


class CanonicalLedgerEntry(BaseModel):
    model_config = _FROZEN

    ledger_name: str = Field(min_length=1)
    is_debit: bool
    amount: PositiveAmount  # §5.1: ALWAYS positive magnitude; sign derived from is_debit
    bill_allocations: tuple[BillAllocation, ...] = ()

    @field_validator("amount", mode="before")
    @classmethod
    def _validate_amount(cls, value: object) -> Decimal:
        return _coerce_amount(value)

    @model_validator(mode="after")
    def _allocations_sum_to_amount(self) -> CanonicalLedgerEntry:
        if self.bill_allocations:
            total = sum((b.amount for b in self.bill_allocations), start=Decimal("0"))
            if total != self.amount:
                raise ValueError(
                    f"bill allocations sum to {total}, expected entry amount {self.amount}"
                )
        return self


class CanonicalVoucher(BaseModel):
    model_config = _FROZEN

    voucher_type: str = Field(min_length=1)
    date: date
    voucher_number: str = Field(min_length=1)
    narration: str | None
    entries: tuple[CanonicalLedgerEntry, ...]
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    party_ledger: str | None = None  # the principal party ledger, if any

    @field_validator("entries")
    @classmethod
    def _non_empty(
        cls, value: tuple[CanonicalLedgerEntry, ...]
    ) -> tuple[CanonicalLedgerEntry, ...]:
        if not value:
            raise ValueError("voucher must have at least one ledger entry")
        return value

    @model_validator(mode="after")
    def _party_ledger_in_entries(self) -> CanonicalVoucher:
        if self.party_ledger is not None:
            names = {e.ledger_name for e in self.entries}
            if self.party_ledger not in names:
                raise ValueError(
                    f"party_ledger {self.party_ledger!r} is not among the voucher's ledgers"
                )
        return self

    @model_validator(mode="after")
    def _balanced(self) -> CanonicalVoucher:
        debit = sum((e.amount for e in self.entries if e.is_debit), start=Decimal("0"))
        credit = sum((e.amount for e in self.entries if not e.is_debit), start=Decimal("0"))
        if debit != credit:
            raise ValueError(
                f"voucher {self.voucher_number!r} unbalanced: debit {debit} != credit {credit}"
            )
        return self


class CanonicalBatch(BaseModel):
    model_config = _FROZEN

    company_name: str = Field(min_length=1)
    source_system: str = Field(min_length=1)
    vouchers: tuple[CanonicalVoucher, ...]

    @field_validator("vouchers")
    @classmethod
    def _non_empty(cls, value: tuple[CanonicalVoucher, ...]) -> tuple[CanonicalVoucher, ...]:
        if not value:
            raise ValueError("batch must contain at least one voucher")
        return value

    @model_validator(mode="after")
    def _unique_voucher_numbers(self) -> CanonicalBatch:
        numbers = [v.voucher_number for v in self.vouchers]
        seen: set[str] = set()
        dupes: set[str] = set()
        for n in numbers:
            if n in seen:
                dupes.add(n)
            seen.add(n)
        if dupes:
            raise ValueError(f"duplicate voucher numbers in batch: {sorted(dupes)}")
        return self
