from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError as PydanticValidationError

from tallyimporter.contracts.canonical import (
    CanonicalBatch,
    CanonicalLedgerEntry,
    CanonicalVoucher,
)


def _entry(name: str, is_debit: bool, amount: str) -> CanonicalLedgerEntry:
    return CanonicalLedgerEntry(ledger_name=name, is_debit=is_debit, amount=Decimal(amount))


def _payment_voucher() -> CanonicalVoucher:
    return CanonicalVoucher(
        voucher_type="Payment",
        date=date(2008, 4, 2),
        voucher_number="1",
        narration="Ch. No. Tested",
        entries=(
            _entry("Conveyance", True, "12000"),
            _entry("Bank of India", False, "12000"),
        ),
    )


class TestCanonicalLedgerEntry:
    def test_valid(self) -> None:
        e = _entry("Conveyance", True, "12000")
        assert e.amount == Decimal("12000")

    def test_is_frozen(self) -> None:
        e = _entry("Conveyance", True, "12000")
        with pytest.raises(PydanticValidationError):
            e.amount = Decimal("1")  # type: ignore[misc]

    def test_extra_forbidden(self) -> None:
        with pytest.raises(PydanticValidationError):
            CanonicalLedgerEntry(
                ledger_name="X",
                is_debit=True,
                amount=Decimal("1"),
                extra="no",  # type: ignore[call-arg]
            )

    def test_rejects_zero_amount(self) -> None:
        with pytest.raises(PydanticValidationError):
            _entry("X", True, "0")

    def test_rejects_negative_amount(self) -> None:
        with pytest.raises(PydanticValidationError):
            _entry("X", True, "-5")

    def test_rejects_float_amount(self) -> None:
        with pytest.raises(PydanticValidationError):
            CanonicalLedgerEntry(ledger_name="X", is_debit=True, amount=1.23)  # type: ignore[arg-type]


class TestCanonicalVoucher:
    def test_valid(self) -> None:
        v = _payment_voucher()
        assert v.confidence == 1.0
        assert len(v.entries) == 2

    def test_balanced_multi_line(self) -> None:
        v = CanonicalVoucher(
            voucher_type="Sales",
            date=date(2026, 1, 15),
            voucher_number="S-1",
            narration=None,
            entries=(
                _entry("Debtors", True, "118"),
                _entry("Sales", False, "100"),
                _entry("Output GST", False, "18"),
            ),
        )
        assert len(v.entries) == 3

    def test_rejects_unbalanced(self) -> None:
        with pytest.raises(PydanticValidationError):
            CanonicalVoucher(
                voucher_type="Payment",
                date=date(2008, 4, 2),
                voucher_number="1",
                narration=None,
                entries=(
                    _entry("Conveyance", True, "12000"),
                    _entry("Bank", False, "11999"),
                ),
            )

    def test_rejects_no_entries(self) -> None:
        with pytest.raises(PydanticValidationError):
            CanonicalVoucher(
                voucher_type="Payment",
                date=date(2008, 4, 2),
                voucher_number="1",
                narration=None,
                entries=(),
            )

    def test_rejects_confidence_above_one(self) -> None:
        with pytest.raises(PydanticValidationError):
            CanonicalVoucher(
                voucher_type="Payment",
                date=date(2008, 4, 2),
                voucher_number="1",
                narration=None,
                entries=(
                    _entry("Conveyance", True, "12000"),
                    _entry("Bank", False, "12000"),
                ),
                confidence=1.5,
            )

    def test_rejects_confidence_below_zero(self) -> None:
        with pytest.raises(PydanticValidationError):
            CanonicalVoucher(
                voucher_type="Payment",
                date=date(2008, 4, 2),
                voucher_number="1",
                narration=None,
                entries=(
                    _entry("Conveyance", True, "12000"),
                    _entry("Bank", False, "12000"),
                ),
                confidence=-0.1,
            )

    def test_is_frozen(self) -> None:
        v = _payment_voucher()
        with pytest.raises(PydanticValidationError):
            v.voucher_number = "2"  # type: ignore[misc]


class TestCanonicalBatch:
    def test_valid(self) -> None:
        b = CanonicalBatch(
            company_name="ACME Pvt Ltd",
            source_system="zoho",
            vouchers=(_payment_voucher(),),
        )
        assert b.company_name == "ACME Pvt Ltd"

    def test_rejects_duplicate_voucher_numbers(self) -> None:
        with pytest.raises(PydanticValidationError):
            CanonicalBatch(
                company_name="ACME Pvt Ltd",
                source_system="zoho",
                vouchers=(_payment_voucher(), _payment_voucher()),
            )

    def test_rejects_empty_batch(self) -> None:
        with pytest.raises(PydanticValidationError):
            CanonicalBatch(
                company_name="ACME Pvt Ltd",
                source_system="zoho",
                vouchers=(),
            )

    def test_is_frozen(self) -> None:
        b = CanonicalBatch(
            company_name="ACME Pvt Ltd",
            source_system="zoho",
            vouchers=(_payment_voucher(),),
        )
        with pytest.raises(PydanticValidationError):
            b.company_name = "Other"  # type: ignore[misc]
