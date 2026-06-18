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


class TallyLedgerEntry(BaseModel):
    model_config = _FROZEN

    ledger_name: str = Field(min_length=1)
    is_deemed_positive: bool  # True => "Yes"
    amount: Decimal  # SIGNED, as it appears in XML

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
