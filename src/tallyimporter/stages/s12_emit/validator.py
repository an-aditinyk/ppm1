"""Structural validator for Tally import XML (§6.2 / §2.2).

Re-parses serialized output and asserts every hard rule of §2.2, raising
``XmlContractError`` on any violation. Negative cases are covered by tests.
"""

from __future__ import annotations

import re
from decimal import Decimal

from lxml import etree

from tallyimporter.contracts.errors import MoneyError, XmlContractError
from tallyimporter.core.money import parse_money

_DATE_RE = re.compile(r"^\d{8}$")
_REQUIRED_HEADER = {
    "VERSION": "1",
    "TALLYREQUEST": "Import",
    "TYPE": "Data",
    "ID": "Vouchers",
}
_LEDGER_SUBTAGS = ("LEDGERNAME", "ISDEEMEDPOSITIVE", "AMOUNT")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise XmlContractError(message)


def _parse(xml: bytes) -> etree._Element:
    try:
        return etree.fromstring(xml)
    except etree.XMLSyntaxError as exc:
        raise XmlContractError(f"not well-formed XML: {exc}") from exc


def _validate_header(header: etree._Element) -> None:
    for tag, expected in _REQUIRED_HEADER.items():
        actual = header.findtext(tag)
        _require(
            actual == expected,
            f"HEADER/{tag} must be {expected!r}, got {actual!r}",
        )


def _validate_amount(text: str | None) -> Decimal:
    try:
        return parse_money(text if text is not None else "")
    except MoneyError as exc:
        raise XmlContractError(f"invalid AMOUNT {text!r}: {exc}") from exc


def _validate_ledger_line(line: etree._Element) -> Decimal:
    for tag in _LEDGER_SUBTAGS:
        _require(
            line.find(tag) is not None,
            f"ALLLEDGERENTRIES.LIST missing required <{tag}>",
        )
    deemed = line.findtext("ISDEEMEDPOSITIVE")
    _require(
        deemed in ("Yes", "No"),
        f"ISDEEMEDPOSITIVE must be 'Yes' or 'No', got {deemed!r}",
    )
    amount = _validate_amount(line.findtext("AMOUNT"))
    if deemed == "Yes":
        _require(
            amount <= 0,
            f"ISDEEMEDPOSITIVE=Yes (debit) requires non-positive AMOUNT, got {amount}",
        )
    else:
        _require(
            amount >= 0,
            f"ISDEEMEDPOSITIVE=No (credit) requires non-negative AMOUNT, got {amount}",
        )
    return amount


def _validate_voucher(voucher: etree._Element) -> str:
    date_text = voucher.findtext("DATE")
    _require(
        date_text is not None and bool(_DATE_RE.match(date_text)),
        f"DATE must match YYYYMMDD, got {date_text!r}",
    )
    number = voucher.findtext("VOUCHERNUMBER")
    _require(
        number is not None and number != "",
        "VOUCHER missing VOUCHERNUMBER",
    )
    lines = voucher.findall("ALLLEDGERENTRIES.LIST")
    _require(len(lines) > 0, "VOUCHER has no ledger entries")
    total = sum((_validate_ledger_line(line) for line in lines), start=Decimal("0"))
    _require(
        total == Decimal("0"),
        f"voucher {number!r} signed AMOUNTs sum to {total}, expected 0",
    )
    assert number is not None  # narrowed by _require above
    return number


def validate_tally_xml(xml: bytes) -> None:
    """Validate Tally import XML against §2.2. Raises ``XmlContractError`` on any
    violation; returns ``None`` when valid."""
    root = _parse(xml)
    _require(root.tag == "ENVELOPE", f"root element must be ENVELOPE, got {root.tag!r}")

    children = [c.tag for c in root]
    _require(
        children == ["HEADER", "BODY"],
        f"ENVELOPE children must be [HEADER, BODY], got {children}",
    )
    _validate_header(root[0])

    body = root[1]
    body_children = [c.tag for c in body]
    _require(
        body_children == ["DESC", "DATA"],
        f"BODY children must be [DESC, DATA], got {body_children}",
    )

    numbers: list[str] = []
    for message in body.findall("DATA/TALLYMESSAGE"):
        for voucher in message.findall("VOUCHER"):
            numbers.append(_validate_voucher(voucher))

    duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
    _require(
        not duplicates,
        f"duplicate VOUCHERNUMBER values in batch: {duplicates}",
    )


def validate_masters_xml(xml: bytes) -> None:
    """Validate an 'All Masters' ledger-creation envelope. Raises ``XmlContractError``
    on any violation; returns ``None`` when valid."""
    root = _parse(xml)
    _require(root.tag == "ENVELOPE", f"root element must be ENVELOPE, got {root.tag!r}")
    children = [c.tag for c in root]
    _require(
        children == ["HEADER", "BODY"],
        f"ENVELOPE children must be [HEADER, BODY], got {children}",
    )
    header = root[0]
    _require(header.findtext("ID") == "All Masters", "masters HEADER/ID must be 'All Masters'")
    _require(
        header.findtext("TALLYREQUEST") == "Import", "masters HEADER/TALLYREQUEST must be Import"
    )

    names: list[str] = []
    ledgers = root.findall("BODY/DATA/TALLYMESSAGE/LEDGER")
    _require(len(ledgers) > 0, "masters envelope has no LEDGER elements")
    for led in ledgers:
        name = led.get("NAME")
        _require(name is not None and name != "", "LEDGER missing NAME attribute")
        _require(led.findtext("NAME.LIST/NAME") == name, f"LEDGER {name!r} NAME.LIST/NAME mismatch")
        parent = led.findtext("PARENT")
        _require(parent is not None and parent != "", f"LEDGER {name!r} missing PARENT")
        assert name is not None  # narrowed above
        names.append(name)

    duplicates = sorted({n for n in names if names.count(n) > 1})
    _require(not duplicates, f"duplicate ledger names: {duplicates}")
