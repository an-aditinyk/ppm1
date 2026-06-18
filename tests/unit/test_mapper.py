from datetime import date
from decimal import Decimal

import pytest

from tallyimporter.contracts.canonical import (
    CanonicalBatch,
    CanonicalLedgerEntry,
    CanonicalVoucher,
)
from tallyimporter.stages.s12_emit.mapper import canonical_to_tally


def _batch() -> CanonicalBatch:
    return CanonicalBatch(
        company_name="ACME Pvt Ltd",
        source_system="zoho",
        vouchers=(
            CanonicalVoucher(
                voucher_type="Payment",
                date=date(2008, 4, 2),
                voucher_number="1",
                narration="Ch. No. Tested",
                entries=(
                    CanonicalLedgerEntry(
                        ledger_name="Conveyance",
                        is_debit=True,
                        amount=Decimal("12000"),
                    ),
                    CanonicalLedgerEntry(
                        ledger_name="Bank of India",
                        is_debit=False,
                        amount=Decimal("12000"),
                    ),
                ),
            ),
        ),
    )


def test_maps_company_and_voucher_count() -> None:
    env = canonical_to_tally(_batch())
    assert env.company_name == "ACME Pvt Ltd"
    assert len(env.vouchers) == 1


def test_sign_rule_debit_negative_positive_yes() -> None:
    env = canonical_to_tally(_batch())
    debit = env.vouchers[0].entries[0]
    assert debit.ledger_name == "Conveyance"
    assert debit.is_deemed_positive is True
    assert debit.amount == Decimal("-12000")


def test_sign_rule_credit_positive_positive_no() -> None:
    env = canonical_to_tally(_batch())
    credit = env.vouchers[0].entries[1]
    assert credit.ledger_name == "Bank of India"
    assert credit.is_deemed_positive is False
    assert credit.amount == Decimal("12000")


def test_voucher_type_carried_to_vch_type() -> None:
    env = canonical_to_tally(_batch())
    assert env.vouchers[0].vch_type == "Payment"
    assert env.vouchers[0].action == "Create"


def test_order_preserved() -> None:
    env = canonical_to_tally(_batch())
    names = [e.ledger_name for e in env.vouchers[0].entries]
    assert names == ["Conveyance", "Bank of India"]


def test_signed_amounts_net_to_zero() -> None:
    env = canonical_to_tally(_batch())
    total = sum((e.amount for e in env.vouchers[0].entries), start=Decimal("0"))
    assert total == Decimal("0")


def test_narration_passthrough_none() -> None:
    batch = _batch()
    v = batch.vouchers[0]
    rebuilt = CanonicalVoucher(
        voucher_type=v.voucher_type,
        date=v.date,
        voucher_number=v.voucher_number,
        narration=None,
        entries=v.entries,
    )
    env = canonical_to_tally(
        CanonicalBatch(
            company_name=batch.company_name,
            source_system=batch.source_system,
            vouchers=(rebuilt,),
        )
    )
    assert env.vouchers[0].narration is None


def test_mapper_is_pure_does_not_mutate_input() -> None:
    batch = _batch()
    before = batch.model_dump()
    canonical_to_tally(batch)
    assert batch.model_dump() == before


def test_balance_error_cannot_arise_from_balanced_canonical() -> None:
    # A balanced canonical voucher always nets to zero after sign mapping.
    env = canonical_to_tally(_batch())
    for v in env.vouchers:
        assert sum((e.amount for e in v.entries), start=Decimal("0")) == Decimal("0")


def test_empty_safe_pure_function_returns_envelope_type() -> None:
    from tallyimporter.contracts.tally import TallyImportEnvelope

    assert isinstance(canonical_to_tally(_batch()), TallyImportEnvelope)


def test_balance_error_raised_for_constructed_unbalanced(monkeypatch: pytest.MonkeyPatch) -> None:
    # If a single entry slips through unbalanced, TallyVoucher raises BalanceError.
    from tallyimporter.contracts.errors import BalanceError
    from tallyimporter.contracts.tally import TallyLedgerEntry, TallyVoucher

    with pytest.raises(BalanceError):
        TallyVoucher(
            vch_type="Payment",
            date=date(2008, 4, 2),
            voucher_number="1",
            narration=None,
            entries=(
                TallyLedgerEntry(ledger_name="X", is_deemed_positive=True, amount=Decimal("-1")),
            ),
        )
