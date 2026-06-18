from datetime import date
from decimal import Decimal

import pytest

from tallyimporter.contracts.errors import XmlContractError
from tallyimporter.contracts.tally import (
    TallyImportEnvelope,
    TallyLedgerEntry,
    TallyVoucher,
)
from tallyimporter.stages.s12_emit.serializer import serialize_envelope
from tallyimporter.stages.s12_emit.validator import validate_tally_xml


def _entry(name: str, pos: bool, amt: str) -> TallyLedgerEntry:
    return TallyLedgerEntry(ledger_name=name, is_deemed_positive=pos, amount=Decimal(amt))


def _good_env() -> TallyImportEnvelope:
    return TallyImportEnvelope(
        company_name="ACME Pvt Ltd",
        vouchers=(
            TallyVoucher(
                vch_type="Payment",
                date=date(2008, 4, 2),
                voucher_number="1",
                narration="ok",
                entries=(
                    _entry("Conveyance", True, "-12000"),
                    _entry("Bank of India", False, "12000"),
                ),
            ),
            TallyVoucher(
                vch_type="Receipt",
                date=date(2026, 1, 16),
                voucher_number="2",
                narration=None,
                entries=(
                    _entry("Cash", True, "-50"),
                    _entry("Sales", False, "50"),
                ),
            ),
        ),
    )


def test_accepts_valid_xml() -> None:
    validate_tally_xml(serialize_envelope(_good_env()))


def test_rejects_wrong_root() -> None:
    with pytest.raises(XmlContractError):
        validate_tally_xml(b"<?xml version='1.0'?><NOPE/>")


def test_rejects_not_xml() -> None:
    with pytest.raises(XmlContractError):
        validate_tally_xml(b"this is not xml")


def test_rejects_bad_header_values() -> None:
    xml = serialize_envelope(_good_env()).replace(b"<ID>Vouchers</ID>", b"<ID>Bad</ID>")
    with pytest.raises(XmlContractError):
        validate_tally_xml(xml)


def test_rejects_bad_date_format() -> None:
    xml = serialize_envelope(_good_env()).replace(
        b"<DATE>20080402</DATE>", b"<DATE>2008-04-02</DATE>"
    )
    with pytest.raises(XmlContractError):
        validate_tally_xml(xml)


def test_rejects_missing_ledger_subtag() -> None:
    xml = serialize_envelope(_good_env()).replace(b"<ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>", b"")
    with pytest.raises(XmlContractError):
        validate_tally_xml(xml)


def test_rejects_sign_inconsistency_positive_yes_must_be_negative() -> None:
    # ISDEEMEDPOSITIVE=Yes but AMOUNT positive -> inconsistent.
    xml = serialize_envelope(_good_env()).replace(
        b"<AMOUNT>-12000.00</AMOUNT>", b"<AMOUNT>12000.00</AMOUNT>"
    )
    with pytest.raises(XmlContractError):
        validate_tally_xml(xml)


def test_rejects_unbalanced_voucher() -> None:
    xml = serialize_envelope(_good_env()).replace(
        b"<AMOUNT>12000.00</AMOUNT>", b"<AMOUNT>11999.00</AMOUNT>"
    )
    with pytest.raises(XmlContractError):
        validate_tally_xml(xml)


def test_rejects_duplicate_voucher_number() -> None:
    xml = serialize_envelope(_good_env()).replace(
        b"<VOUCHERNUMBER>2</VOUCHERNUMBER>", b"<VOUCHERNUMBER>1</VOUCHERNUMBER>"
    )
    with pytest.raises(XmlContractError):
        validate_tally_xml(xml)


def test_rejects_body_child_order() -> None:
    # Swap so DATA precedes DESC.
    bad = (
        b"<?xml version='1.0' encoding='UTF-8'?>\n"
        b"<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST>"
        b"<TYPE>Data</TYPE><ID>Vouchers</ID></HEADER>"
        b"<BODY><DATA/><DESC/></BODY></ENVELOPE>"
    )
    with pytest.raises(XmlContractError):
        validate_tally_xml(bad)


def test_rejects_bad_isdeemedpositive_value() -> None:
    xml = serialize_envelope(_good_env()).replace(
        b"<ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>",
        b"<ISDEEMEDPOSITIVE>Maybe</ISDEEMEDPOSITIVE>",
    )
    with pytest.raises(XmlContractError):
        validate_tally_xml(xml)


def test_rejects_non_numeric_amount() -> None:
    xml = serialize_envelope(_good_env()).replace(
        b"<AMOUNT>-12000.00</AMOUNT>", b"<AMOUNT>abc</AMOUNT>"
    )
    with pytest.raises(XmlContractError):
        validate_tally_xml(xml)
