from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError as PydanticValidationError

from tallyimporter.contracts.errors import BalanceError
from tallyimporter.contracts.tally import (
    TallyImportEnvelope,
    TallyImportResult,
    TallyLedgerEntry,
    TallyVoucher,
)


def _voucher() -> TallyVoucher:
    return TallyVoucher(
        vch_type="Payment",
        date=date(2008, 4, 2),
        voucher_number="1",
        narration="Ch. No. Tested",
        entries=(
            TallyLedgerEntry(
                ledger_name="Conveyance",
                is_deemed_positive=True,
                amount=Decimal("-12000"),
            ),
            TallyLedgerEntry(
                ledger_name="Bank of India",
                is_deemed_positive=False,
                amount=Decimal("12000"),
            ),
        ),
    )


class TestTallyVoucher:
    def test_default_action_is_create(self) -> None:
        assert _voucher().action == "Create"

    def test_rejects_unbalanced_with_balance_error(self) -> None:
        with pytest.raises(BalanceError):
            TallyVoucher(
                vch_type="Payment",
                date=date(2008, 4, 2),
                voucher_number="1",
                narration=None,
                entries=(
                    TallyLedgerEntry(
                        ledger_name="Conveyance",
                        is_deemed_positive=True,
                        amount=Decimal("-12000"),
                    ),
                    TallyLedgerEntry(
                        ledger_name="Bank",
                        is_deemed_positive=False,
                        amount=Decimal("11999"),
                    ),
                ),
            )

    def test_rejects_invalid_action(self) -> None:
        with pytest.raises(PydanticValidationError):
            TallyVoucher(
                action="Frobnicate",  # type: ignore[arg-type]
                vch_type="Payment",
                date=date(2008, 4, 2),
                voucher_number="1",
                narration=None,
                entries=_voucher().entries,
            )

    def test_is_frozen(self) -> None:
        with pytest.raises(PydanticValidationError):
            _voucher().vch_type = "Receipt"  # type: ignore[misc]

    def test_extra_forbidden(self) -> None:
        with pytest.raises(PydanticValidationError):
            TallyLedgerEntry(
                ledger_name="X",
                is_deemed_positive=True,
                amount=Decimal("1"),
                extra="no",  # type: ignore[call-arg]
            )


class TestTallyImportEnvelope:
    def test_valid(self) -> None:
        env = TallyImportEnvelope(company_name="ACME Pvt Ltd", vouchers=(_voucher(),))
        assert env.company_name == "ACME Pvt Ltd"

    def test_is_frozen(self) -> None:
        env = TallyImportEnvelope(company_name="ACME Pvt Ltd", vouchers=(_voucher(),))
        with pytest.raises(PydanticValidationError):
            env.company_name = "Other"  # type: ignore[misc]


class TestTallyImportResult:
    def test_valid(self) -> None:
        r = TallyImportResult(
            created=2,
            altered=0,
            last_vch_id=119,
            last_m_id=0,
            combined=0,
            ignored=0,
            errors=0,
        )
        assert r.created == 2

    def test_is_frozen(self) -> None:
        r = TallyImportResult(
            created=2,
            altered=0,
            last_vch_id=119,
            last_m_id=0,
            combined=0,
            ignored=0,
            errors=0,
        )
        with pytest.raises(PydanticValidationError):
            r.created = 3  # type: ignore[misc]
