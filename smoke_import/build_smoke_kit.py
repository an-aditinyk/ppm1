"""Build the TallyPrime smoke-import kit.

Regenerates the deterministic Zoho->Tally run, extracts a 30-voucher slice spanning
every voucher type we emit (plus all available negative-amount reversal vouchers),
and emits a matching "All Masters" ledger-creation envelope for every ledger the
slice references.

This is a manual-QA aid (NOT part of src/). The slice is built through the exact
same mapper/serializer as production and is re-checked with validate_tally_xml. The
masters envelope is built here with lxml (auto-escaped); its LEDGER structure uses
only the minimal, documented Tally ledger-master tags (NAME.LIST/NAME, PARENT,
ACTION) — see SMOKE_IMPORT.md. Run:

    python smoke_import/build_smoke_kit.py

Override the posting date (must fall inside the test company's financial year):

    SMOKE_DATE=20250401 python smoke_import/build_smoke_kit.py
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from lxml import etree

from tallyimporter.contracts.canonical import (
    CanonicalBatch,
    CanonicalLedgerEntry,
    CanonicalVoucher,
)
from tallyimporter.stages.s12_emit.mapper import canonical_to_tally
from tallyimporter.stages.s12_emit.serializer import serialize_envelope
from tallyimporter.stages.s12_emit.validator import validate_tally_xml

ZOHO = Path("/tmp/zoho")
HERE = Path(__file__).resolve().parent
COMPANY = "Zoho Sample Co"

_d = os.environ.get("SMOKE_DATE", "20260401")
POST_DATE = date(int(_d[:4]), int(_d[4:6]), int(_d[6:8]))

# Ledger -> Tally primary group. These group names are Tally predefined (reserved)
# groups, not invented. Anything not listed (e.g. contact ledgers) is a debtor.
GROUP_OF = {
    "Sales Account": "Sales Accounts",
    "Bank Account": "Bank Accounts",
    "Accounts Receivable": "Sundry Debtors",
    "Accounts Payable": "Sundry Creditors",
}
DEFAULT_GROUP = "Sundry Debtors"


@dataclass(frozen=True)
class Built:
    voucher: CanonicalVoucher
    vtype: str
    is_reversal: bool


def _contacts() -> dict[str, str]:
    m: dict[str, str] = {}
    with open(ZOHO / "Contacts.csv", newline="") as f:
        for r in csv.DictReader(f):
            m[r["contact_id"]] = r["contact_name"]
    return m


def _voucher(
    vtype: str, num: str, dr: str, cr: str, amount: Decimal
) -> tuple[CanonicalVoucher, bool]:
    reversal = amount < 0
    if reversal:
        dr, cr = cr, dr
        amount = -amount
    v = CanonicalVoucher(
        voucher_type=vtype,
        date=POST_DATE,
        voucher_number=num,
        narration=None,
        entries=(
            CanonicalLedgerEntry(ledger_name=dr, is_debit=True, amount=amount),
            CanonicalLedgerEntry(ledger_name=cr, is_debit=False, amount=amount),
        ),
    )
    return v, reversal


def _build_all() -> list[Built]:
    cmap = _contacts()
    out: list[Built] = []
    with open(ZOHO / "Sales_Invoices.csv", newline="") as f:
        for r in csv.DictReader(f):
            cust = cmap.get(r["customer_id"], r["customer_id"])
            v, rev = _voucher(
                "Sales", r["invoice_id"], cust, "Sales Account", Decimal(r["total"])
            )
            out.append(Built(v, "Sales", rev))
    with open(ZOHO / "Customer_Payments.csv", newline="") as f:
        for r in csv.DictReader(f):
            v, rev = _voucher(
                "Receipt", r["id"], "Bank Account", "Accounts Receivable",
                Decimal(r["amount"]),
            )
            out.append(Built(v, "Receipt", rev))
    with open(ZOHO / "Vendor_Payments.csv", newline="") as f:
        for r in csv.DictReader(f):
            v, rev = _voucher(
                "Payment", r["id"], "Accounts Payable", "Bank Account",
                Decimal(r["amount"]),
            )
            out.append(Built(v, "Payment", rev))
    return out


def _select_slice(built: list[Built]) -> list[CanonicalVoucher]:
    # Up to 5 reversals, drawn across voucher types so the smoke test exercises
    # negative AMOUNT handling in more than one voucher type.
    rev_receipt = [b for b in built if b.is_reversal and b.vtype == "Receipt"][:3]
    rev_payment = [b for b in built if b.is_reversal and b.vtype == "Payment"][:2]
    reversals = rev_receipt + rev_payment
    # ~25 normals spanning all three voucher types (deterministic: first N of each).
    quota = {"Sales": 9, "Receipt": 8, "Payment": 8}
    normals: list[Built] = []
    for vtype, n in quota.items():
        normals += [b for b in built if b.vtype == vtype and not b.is_reversal][:n]
    chosen = normals + reversals
    assert len(chosen) == 30, f"expected 30 vouchers, got {len(chosen)}"
    return [b.voucher for b in chosen]


def _sub(parent: etree._Element, tag: str, text: str) -> None:
    etree.SubElement(parent, tag).text = text


def _build_masters(ledger_names: list[str]) -> bytes:
    env = etree.Element("ENVELOPE")
    header = etree.SubElement(env, "HEADER")
    _sub(header, "VERSION", "1")
    _sub(header, "TALLYREQUEST", "Import")
    _sub(header, "TYPE", "Data")
    _sub(header, "ID", "All Masters")  # §2.2 rule 2: masters use ID=All Masters
    body = etree.SubElement(env, "BODY")
    desc = etree.SubElement(body, "DESC")
    static = etree.SubElement(desc, "STATICVARIABLES")
    _sub(static, "SVCURRENTCOMPANY", COMPANY)
    data = etree.SubElement(body, "DATA")
    for name in ledger_names:
        msg = etree.SubElement(data, "TALLYMESSAGE", nsmap={"UDF": "TallyUDF"})
        ledger = etree.SubElement(msg, "LEDGER")
        ledger.set("NAME", name)
        ledger.set("ACTION", "Create")
        name_list = etree.SubElement(ledger, "NAME.LIST")
        _sub(name_list, "NAME", name)
        _sub(ledger, "PARENT", GROUP_OF.get(name, DEFAULT_GROUP))
    return etree.tostring(
        env, xml_declaration=True, encoding="UTF-8", pretty_print=True
    )


def main() -> None:
    built = _build_all()
    slice_vouchers = _select_slice(built)

    batch = CanonicalBatch(
        company_name=COMPANY, source_system="zoho", vouchers=tuple(slice_vouchers)
    )
    slice_xml = serialize_envelope(canonical_to_tally(batch))
    validate_tally_xml(slice_xml)  # gate: must pass our own validator
    (HERE / "vouchers_slice.xml").write_bytes(slice_xml)

    # Every distinct ledger the slice references, in first-seen order.
    seen: list[str] = []
    for v in canonical_to_tally(batch).vouchers:
        for e in v.entries:
            if e.ledger_name not in seen:
                seen.append(e.ledger_name)
    masters_xml = _build_masters(seen)
    etree.fromstring(masters_xml)  # well-formedness check
    (HERE / "masters.xml").write_bytes(masters_xml)

    # Report
    from collections import Counter

    types = Counter(b.vtype for b in built if b.voucher in set(slice_vouchers))
    rev = sum(1 for b in built if b.is_reversal and b.voucher in set(slice_vouchers))
    print(f"posting date:   {POST_DATE:%Y%m%d}")
    print(f"slice vouchers: {len(slice_vouchers)} (reversals: {rev})")
    print(f"by type:        {dict(types)}")
    print(f"ledgers:        {len(seen)} -> {seen[:6]}{' ...' if len(seen) > 6 else ''}")
    print(f"slice bytes:    {len(slice_xml):,}  (validate_tally_xml: OK)")
    print(f"masters bytes:  {len(masters_xml):,}")
    print(f"written:        {HERE / 'vouchers_slice.xml'}")
    print(f"                {HERE / 'masters.xml'}")


if __name__ == "__main__":
    main()
