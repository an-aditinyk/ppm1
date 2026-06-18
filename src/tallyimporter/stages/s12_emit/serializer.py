"""Deterministic Tally import XML serializer (§6.1).

Builds the exact structure of §2.1 with ``lxml`` — never by string concatenation, so
all text is auto-escaped. Output is byte-stable: fixed element/attribute order, UTF-8,
XML declaration, pretty-printed. Amounts are rounded to 2dp (round-half-up) here, at
the serialization boundary only.
"""

from __future__ import annotations

from lxml import etree

from tallyimporter.contracts.tally import (
    TallyImportEnvelope,
    TallyLedgerEntry,
    TallyVoucher,
)
from tallyimporter.core.money import render_amount

_UDF_NSMAP = {"UDF": "TallyUDF"}
_DATE_FORMAT = "%Y%m%d"


def _sub(parent: etree._Element, tag: str, text: str) -> etree._Element:
    el = etree.SubElement(parent, tag)
    el.text = text
    return el


def _build_ledger_entry(parent: etree._Element, entry: TallyLedgerEntry) -> None:
    line = etree.SubElement(parent, "ALLLEDGERENTRIES.LIST")
    _sub(line, "LEDGERNAME", entry.ledger_name)
    _sub(line, "ISDEEMEDPOSITIVE", "Yes" if entry.is_deemed_positive else "No")
    _sub(line, "AMOUNT", render_amount(entry.amount))


def _build_voucher(data: etree._Element, voucher: TallyVoucher) -> None:
    message = etree.SubElement(data, "TALLYMESSAGE", nsmap=_UDF_NSMAP)
    # Attribute order is fixed: VCHTYPE then ACTION (matches §2.1).
    vch = etree.SubElement(message, "VOUCHER")
    vch.set("VCHTYPE", voucher.vch_type)
    vch.set("ACTION", voucher.action)
    _sub(vch, "DATE", voucher.date.strftime(_DATE_FORMAT))
    if voucher.narration is not None:
        _sub(vch, "NARRATION", voucher.narration)
    _sub(vch, "VOUCHERTYPENAME", voucher.vch_type)
    _sub(vch, "VOUCHERNUMBER", voucher.voucher_number)
    for entry in voucher.entries:
        _build_ledger_entry(vch, entry)


def serialize_envelope(env: TallyImportEnvelope) -> bytes:
    """Serialize a Tally import envelope to byte-stable UTF-8 XML."""
    envelope = etree.Element("ENVELOPE")

    header = etree.SubElement(envelope, "HEADER")
    _sub(header, "VERSION", "1")
    _sub(header, "TALLYREQUEST", "Import")
    _sub(header, "TYPE", "Data")
    _sub(header, "ID", "Vouchers")

    body = etree.SubElement(envelope, "BODY")
    desc = etree.SubElement(body, "DESC")
    static = etree.SubElement(desc, "STATICVARIABLES")
    _sub(static, "SVCURRENTCOMPANY", env.company_name)

    data = etree.SubElement(body, "DATA")
    for voucher in env.vouchers:
        _build_voucher(data, voucher)

    return etree.tostring(
        envelope,
        xml_declaration=True,
        encoding="UTF-8",
        pretty_print=True,
    )
