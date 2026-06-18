from datetime import date
from decimal import Decimal

from lxml import etree

from tallyimporter.contracts.tally import (
    TallyImportEnvelope,
    TallyLedgerEntry,
    TallyVoucher,
)
from tallyimporter.stages.s12_emit.serializer import serialize_envelope


def _env(narration: str | None = "Ch. No. Tested") -> TallyImportEnvelope:
    return TallyImportEnvelope(
        company_name="ACME Pvt Ltd",
        vouchers=(
            TallyVoucher(
                vch_type="Payment",
                date=date(2008, 4, 2),
                voucher_number="1",
                narration=narration,
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
            ),
        ),
    )


def test_returns_bytes() -> None:
    assert isinstance(serialize_envelope(_env()), bytes)


def test_deterministic_byte_stable() -> None:
    assert serialize_envelope(_env()) == serialize_envelope(_env())


def test_has_xml_declaration_utf8() -> None:
    out = serialize_envelope(_env())
    assert out.startswith(b"<?xml")
    assert b"UTF-8" in out[:60]


def test_structure_header_and_order() -> None:
    root = etree.fromstring(serialize_envelope(_env()))
    assert root.tag == "ENVELOPE"
    assert [c.tag for c in root] == ["HEADER", "BODY"]
    header = root[0]
    assert header.findtext("VERSION") == "1"
    assert header.findtext("TALLYREQUEST") == "Import"
    assert header.findtext("TYPE") == "Data"
    assert header.findtext("ID") == "Vouchers"
    body = root[1]
    assert [c.tag for c in body] == ["DESC", "DATA"]


def test_static_company_name() -> None:
    root = etree.fromstring(serialize_envelope(_env()))
    assert root.find("BODY/DESC/STATICVARIABLES/SVCURRENTCOMPANY").text == "ACME Pvt Ltd"


def test_voucher_attributes_and_fields() -> None:
    root = etree.fromstring(serialize_envelope(_env()))
    voucher = root.find("BODY/DATA/TALLYMESSAGE/VOUCHER")
    assert voucher.get("VCHTYPE") == "Payment"
    assert voucher.get("ACTION") == "Create"
    assert voucher.findtext("DATE") == "20080402"
    assert voucher.findtext("NARRATION") == "Ch. No. Tested"
    assert voucher.findtext("VOUCHERTYPENAME") == "Payment"
    assert voucher.findtext("VOUCHERNUMBER") == "1"


def test_ledger_entries() -> None:
    root = etree.fromstring(serialize_envelope(_env()))
    lines = root.findall("BODY/DATA/TALLYMESSAGE/VOUCHER/ALLLEDGERENTRIES.LIST")
    assert len(lines) == 2
    assert lines[0].findtext("LEDGERNAME") == "Conveyance"
    assert lines[0].findtext("ISDEEMEDPOSITIVE") == "Yes"
    assert lines[0].findtext("AMOUNT") == "-12000.00"
    assert lines[1].findtext("ISDEEMEDPOSITIVE") == "No"
    assert lines[1].findtext("AMOUNT") == "12000.00"


def test_narration_omitted_when_none() -> None:
    root = etree.fromstring(serialize_envelope(_env(narration=None)))
    voucher = root.find("BODY/DATA/TALLYMESSAGE/VOUCHER")
    assert voucher.find("NARRATION") is None


def test_tallymessage_has_udf_namespace() -> None:
    out = serialize_envelope(_env())
    assert b'xmlns:UDF="TallyUDF"' in out


def test_xml_escaping_of_special_chars() -> None:
    env = TallyImportEnvelope(
        company_name='A & B <Co> "X"',
        vouchers=(
            TallyVoucher(
                vch_type="Payment",
                date=date(2008, 4, 2),
                voucher_number="1",
                narration="a & b < c > d",
                entries=(
                    TallyLedgerEntry(
                        ledger_name="L&<>",
                        is_deemed_positive=True,
                        amount=Decimal("-1"),
                    ),
                    TallyLedgerEntry(
                        ledger_name="R",
                        is_deemed_positive=False,
                        amount=Decimal("1"),
                    ),
                ),
            ),
        ),
    )
    out = serialize_envelope(env)
    assert b"&amp;" in out
    assert b"&lt;" in out
    assert b"&gt;" in out
    # Round-trips back to the original text.
    root = etree.fromstring(out)
    assert root.find("BODY/DESC/STATICVARIABLES/SVCURRENTCOMPANY").text == 'A & B <Co> "X"'
    assert (
        root.find("BODY/DATA/TALLYMESSAGE/VOUCHER/ALLLEDGERENTRIES.LIST/LEDGERNAME").text == "L&<>"
    )


def test_amount_rounding_half_up_at_boundary() -> None:
    env = TallyImportEnvelope(
        company_name="C",
        vouchers=(
            TallyVoucher(
                vch_type="Payment",
                date=date(2026, 1, 15),
                voucher_number="1",
                narration=None,
                entries=(
                    TallyLedgerEntry(
                        ledger_name="A",
                        is_deemed_positive=True,
                        amount=Decimal("-1.005"),
                    ),
                    TallyLedgerEntry(
                        ledger_name="B",
                        is_deemed_positive=False,
                        amount=Decimal("1.005"),
                    ),
                ),
            ),
        ),
    )
    root = etree.fromstring(serialize_envelope(env))
    amounts = [
        e.text for e in root.findall("BODY/DATA/TALLYMESSAGE/VOUCHER/ALLLEDGERENTRIES.LIST/AMOUNT")
    ]
    assert amounts == ["-1.01", "1.01"]


def test_one_tallymessage_per_voucher() -> None:
    env = TallyImportEnvelope(
        company_name="C",
        vouchers=(
            _env().vouchers[0],
            TallyVoucher(
                vch_type="Receipt",
                date=date(2026, 1, 16),
                voucher_number="2",
                narration=None,
                entries=(
                    TallyLedgerEntry(
                        ledger_name="Cash",
                        is_deemed_positive=True,
                        amount=Decimal("-50"),
                    ),
                    TallyLedgerEntry(
                        ledger_name="Sales",
                        is_deemed_positive=False,
                        amount=Decimal("50"),
                    ),
                ),
            ),
        ),
    )
    root = etree.fromstring(serialize_envelope(env))
    messages = root.findall("BODY/DATA/TALLYMESSAGE")
    assert len(messages) == 2
