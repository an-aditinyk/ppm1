"""Tests for ledger-masters emission (S12)."""

from __future__ import annotations

import io
import zipfile
from datetime import date
from decimal import Decimal

import pytest
from lxml import etree

from tallyimporter.contracts.canonical import (
    CanonicalBatch,
    CanonicalLedgerEntry,
    CanonicalVoucher,
)
from tallyimporter.contracts.errors import XmlContractError
from tallyimporter.pipeline import run_pipeline_full
from tallyimporter.stages.s12_emit.masters import masters_for_batch
from tallyimporter.stages.s12_emit.serializer import serialize_masters
from tallyimporter.stages.s12_emit.validator import validate_masters_xml

DATE = date(2026, 4, 1)
_GROUPS = (("Sales Account", "Sales Accounts"), ("Bank Account", "Bank Accounts"))


def _batch() -> CanonicalBatch:
    return CanonicalBatch(
        company_name="Test Co",
        source_system="zoho",
        vouchers=(
            CanonicalVoucher(
                voucher_type="Sales",
                date=DATE,
                voucher_number="INV1",
                narration=None,
                entries=(
                    CanonicalLedgerEntry(
                        ledger_name="Acme & Co", is_debit=True, amount=Decimal("100")
                    ),
                    CanonicalLedgerEntry(
                        ledger_name="Sales Account", is_debit=False, amount=Decimal("100")
                    ),
                ),
            ),
            CanonicalVoucher(
                voucher_type="Receipt",
                date=DATE,
                voucher_number="R1",
                narration=None,
                entries=(
                    CanonicalLedgerEntry(
                        ledger_name="Bank Account", is_debit=True, amount=Decimal("50")
                    ),
                    CanonicalLedgerEntry(
                        ledger_name="Acme & Co", is_debit=False, amount=Decimal("50")
                    ),
                ),
            ),
        ),
    )


def test_masters_for_batch_assigns_groups_and_dedupes() -> None:
    env = masters_for_batch(_batch(), group_of=_GROUPS, default_group="Sundry Debtors")
    by_name = {m.name: m.parent for m in env.ledgers}
    assert by_name == {
        "Acme & Co": "Sundry Debtors",  # default (party)
        "Sales Account": "Sales Accounts",
        "Bank Account": "Bank Accounts",
    }
    # first-seen order, each ledger once
    assert [m.name for m in env.ledgers] == ["Acme & Co", "Sales Account", "Bank Account"]


def test_serialize_masters_structure_and_validate() -> None:
    env = masters_for_batch(_batch(), group_of=_GROUPS)
    xml = serialize_masters(env)
    validate_masters_xml(xml)  # must not raise
    root = etree.fromstring(xml)
    assert root.findtext("HEADER/ID") == "All Masters"
    ledgers = root.findall("BODY/DATA/TALLYMESSAGE/LEDGER")
    assert len(ledgers) == 3
    first = ledgers[0]
    assert first.get("NAME") == "Acme & Co"
    assert first.get("ACTION") == "Create"
    assert first.findtext("NAME.LIST/NAME") == "Acme & Co"
    assert first.findtext("PARENT") == "Sundry Debtors"
    assert b"&amp;" in xml  # name escaped


def test_serialize_masters_deterministic() -> None:
    env = masters_for_batch(_batch(), group_of=_GROUPS)
    assert serialize_masters(env) == serialize_masters(env)


def test_validate_masters_rejects_bad() -> None:
    good = serialize_masters(masters_for_batch(_batch(), group_of=_GROUPS))
    with pytest.raises(XmlContractError):
        validate_masters_xml(good.replace(b"<ID>All Masters</ID>", b"<ID>Vouchers</ID>"))
    with pytest.raises(XmlContractError):
        validate_masters_xml(good.replace(b"<PARENT>Sales Accounts</PARENT>", b""))
    with pytest.raises(XmlContractError):
        validate_masters_xml(b"<?xml version='1.0'?><NOPE/>")


def _zoho_zip() -> bytes:
    files = {
        "Contacts.csv": "contact_id,contact_name,gst_no\nC1,Acme & Co,21A\n",
        "Sales_Invoices.csv": "invoice_id,customer_id,total\nINV1,C1,1000\n",
        "Customer_Payments.csv": "id,amount\nR1,500\n",
        "Vendor_Payments.csv": "id,amount\nP1,200\n",
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, text in files.items():
            zf.writestr(name, text)
    return buf.getvalue()


def test_run_pipeline_full_emits_both_files() -> None:
    export = run_pipeline_full(_zoho_zip(), company_name="Test Co", posting_date=DATE)
    validate_masters_xml(export.masters_xml)
    masters = etree.fromstring(export.masters_xml)
    names = {led.get("NAME") for led in masters.findall("BODY/DATA/TALLYMESSAGE/LEDGER")}
    # control accounts + the one customer ledger the vouchers reference
    assert {
        "Sales Account",
        "Bank Account",
        "Accounts Receivable",
        "Accounts Payable",
        "Acme & Co",
    } <= names
    groups = {
        led.get("NAME"): led.findtext("PARENT")
        for led in masters.findall("BODY/DATA/TALLYMESSAGE/LEDGER")
    }
    assert groups["Sales Account"] == "Sales Accounts"
    assert groups["Accounts Payable"] == "Sundry Creditors"
    assert groups["Acme & Co"] == "Sundry Debtors"
    # vouchers file is the §2.2 voucher envelope
    vouchers = etree.fromstring(export.vouchers_xml)
    assert vouchers.findtext("HEADER/ID") == "Vouchers"
