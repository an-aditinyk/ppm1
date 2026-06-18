"""Tests for the command-line entry point."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from lxml import etree

from tallyimporter.cli import main


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


def test_cli_writes_both_files(tmp_path: Path) -> None:
    archive = tmp_path / "zoho.zip"
    archive.write_bytes(_zoho_zip())
    out = tmp_path / "out"
    rc = main([str(archive), "--company", "Co", "--date", "20260401", "--out", str(out)])
    assert rc == 0
    masters = out / "masters.xml"
    vouchers = out / "vouchers.xml"
    assert masters.exists() and vouchers.exists()
    assert etree.fromstring(masters.read_bytes()).findtext("HEADER/ID") == "All Masters"
    assert etree.fromstring(vouchers.read_bytes()).findtext("HEADER/ID") == "Vouchers"


def test_cli_enrich_adds_bill_allocations(tmp_path: Path) -> None:
    archive = tmp_path / "zoho.zip"
    archive.write_bytes(_zoho_zip())
    rc = main(
        [str(archive), "--company", "Co", "--date", "20260401", "--out", str(tmp_path), "--enrich"]
    )
    assert rc == 0
    root = etree.fromstring((tmp_path / "vouchers.xml").read_bytes())
    assert root.find(".//BILLALLOCATIONS.LIST") is not None


def test_cli_corrupt_archive_returns_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    rc = main([str(bad), "--company", "Co", "--date", "20260401", "--out", str(tmp_path)])
    assert rc == 1


def test_cli_missing_file_returns_2(tmp_path: Path) -> None:
    rc = main(
        [str(tmp_path / "nope.zip"), "--company", "Co", "--date", "20260401", "--out", str(tmp_path)]
    )
    assert rc == 2
