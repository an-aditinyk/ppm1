"""Tests for Phase 2: enrich (S08), reconcile (S10), review (S11), and the canonical/
Tally extensions (bill allocations + party ledger)."""

from __future__ import annotations

import io
import zipfile
from datetime import date
from decimal import Decimal

import pytest
from lxml import etree
from pydantic import ValidationError as PydValidationError

from tallyimporter.contracts.canonical import (
    BillAllocation,
    CanonicalBatch,
    CanonicalLedgerEntry,
    CanonicalVoucher,
)
from tallyimporter.contracts.errors import (
    ReconcileError,
    ReviewError,
    ValidationError,
    XmlContractError,
)
from tallyimporter.pipeline import run_pipeline_full
from tallyimporter.stages.s07_validate.contracts import ValidationIssue, ValidationReport
from tallyimporter.stages.s08_enrich.enrich import enrich
from tallyimporter.stages.s10_reconcile.contracts import (
    ImportedVoucherRef,
    PriorImportState,
)
from tallyimporter.stages.s10_reconcile.reconcile import reconcile
from tallyimporter.stages.s11_review.contracts import (
    ReviewDecision,
    ReviewPolicy,
)
from tallyimporter.stages.s11_review.review import apply_decisions, build_queue
from tallyimporter.stages.s12_emit.mapper import canonical_to_tally
from tallyimporter.stages.s12_emit.serializer import serialize_envelope
from tallyimporter.stages.s12_emit.validator import validate_tally_xml

DATE = date(2026, 4, 1)


def _sales(number: str = "INV1", *, confidence: float = 1.0) -> CanonicalVoucher:
    return CanonicalVoucher(
        voucher_type="Sales",
        date=DATE,
        voucher_number=number,
        narration=None,
        confidence=confidence,
        party_ledger="Acme & Co",
        entries=(
            CanonicalLedgerEntry(ledger_name="Acme & Co", is_debit=True, amount=Decimal("100")),
            CanonicalLedgerEntry(
                ledger_name="Sales Account", is_debit=False, amount=Decimal("100")
            ),
        ),
    )


def _batch(*vouchers: CanonicalVoucher) -> CanonicalBatch:
    return CanonicalBatch(company_name="Co", source_system="zoho", vouchers=vouchers or (_sales(),))


# ── Canonical / Tally extension validators ───────────────────────────────────────


def test_bill_allocations_must_sum_to_entry_amount() -> None:
    with pytest.raises(PydValidationError):
        CanonicalLedgerEntry(
            ledger_name="X",
            is_debit=True,
            amount=Decimal("100"),
            bill_allocations=(BillAllocation(reference="b", kind="new", amount=Decimal("60")),),
        )


def test_party_ledger_must_be_among_entries() -> None:
    with pytest.raises(PydValidationError):
        CanonicalVoucher(
            voucher_type="Sales",
            date=DATE,
            voucher_number="1",
            narration=None,
            party_ledger="Ghost",
            entries=_sales().entries,
        )


# ── S08 enrich ───────────────────────────────────────────────────────────────────


def test_enrich_adds_bill_allocation_to_party_entry() -> None:
    out = enrich(_batch(_sales("INV1")))
    party = out.batch.vouchers[0].entries[0]
    assert party.ledger_name == "Acme & Co"
    assert len(party.bill_allocations) == 1
    alloc = party.bill_allocations[0]
    assert alloc.reference == "INV1" and alloc.kind == "new" and alloc.amount == Decimal("100")


def test_enrich_skips_vouchers_without_party() -> None:
    receipt = CanonicalVoucher(
        voucher_type="Receipt",
        date=DATE,
        voucher_number="R1",
        narration=None,
        entries=(
            CanonicalLedgerEntry(ledger_name="Bank", is_debit=True, amount=Decimal("5")),
            CanonicalLedgerEntry(ledger_name="AR", is_debit=False, amount=Decimal("5")),
        ),
    )
    out = enrich(_batch(receipt))
    assert all(not e.bill_allocations for e in out.batch.vouchers[0].entries)


def test_enriched_voucher_serializes_and_validates() -> None:
    env = canonical_to_tally(enrich(_batch(_sales("INV1"))).batch)
    xml = serialize_envelope(env)
    validate_tally_xml(xml)  # must not raise
    root = etree.fromstring(xml)
    assert root.findtext("BODY/DATA/TALLYMESSAGE/VOUCHER/PARTYLEDGERNAME") == "Acme & Co"
    bill = root.find("BODY/DATA/TALLYMESSAGE/VOUCHER/ALLLEDGERENTRIES.LIST/BILLALLOCATIONS.LIST")
    assert bill is not None
    assert bill.findtext("NAME") == "INV1"
    assert bill.findtext("BILLTYPE") == "New Ref"
    assert bill.findtext("AMOUNT") == "-100.00"  # debit side -> negative


def test_validator_rejects_tampered_bill_allocation_sum() -> None:
    xml = serialize_envelope(canonical_to_tally(enrich(_batch(_sales("INV1"))).batch))
    root = etree.fromstring(xml)
    bill_amount = root.find(".//BILLALLOCATIONS.LIST/AMOUNT")
    assert bill_amount is not None
    bill_amount.text = "-60.00"  # no longer equals the entry AMOUNT
    with pytest.raises(XmlContractError):
        validate_tally_xml(etree.tostring(root))


# ── S10 reconcile ────────────────────────────────────────────────────────────────


def _prior(*refs: ImportedVoucherRef) -> PriorImportState:
    return PriorImportState(imported=refs)


def test_reconcile_splits_matched_and_unmatched() -> None:
    batch = _batch(_sales("INV1"), _sales("INV2"))
    prior = _prior(
        ImportedVoucherRef(voucher_number="INV1", voucher_type="Sales", date=DATE, amount="100")
    )
    rec = reconcile(batch, prior=prior)
    assert rec.matched_voucher_numbers == ("INV1",)
    assert rec.unmatched_voucher_numbers == ("INV2",)


def test_reconcile_rejects_ambiguous_prior() -> None:
    dup = ImportedVoucherRef(voucher_number="INV1", voucher_type="Sales", date=DATE, amount="100")
    with pytest.raises(ReconcileError):
        reconcile(_batch(_sales("INV1")), prior=_prior(dup, dup))


# ── S11 review ───────────────────────────────────────────────────────────────────


def test_build_queue_flags_low_confidence_and_issues() -> None:
    batch = _batch(_sales("INV1", confidence=0.5), _sales("INV2", confidence=1.0))
    report = ValidationReport(
        batch=batch,
        issues=(ValidationIssue(voucher_number="INV2", message="bad", severity="error"),),
    )
    queue = build_queue(batch, report, policy=ReviewPolicy(confidence_floor=0.8))
    pending = {i.voucher_number for i in queue.pending}
    assert pending == {"INV1", "INV2"}  # INV1 low-confidence, INV2 gated error


def test_apply_decisions_keeps_approved_withholds_rest() -> None:
    batch = _batch(_sales("INV1", confidence=0.5), _sales("INV2", confidence=0.5))
    report = ValidationReport(batch=batch, issues=())
    queue = build_queue(batch, report, policy=ReviewPolicy(confidence_floor=0.8))
    kept = apply_decisions(queue, (ReviewDecision(voucher_number="INV1", approved=True),))
    assert [v.voucher_number for v in kept.vouchers] == ["INV1"]  # INV2 withheld


def test_apply_decisions_rejects_unknown_and_conflict() -> None:
    batch = _batch(_sales("INV1", confidence=0.5))
    queue = build_queue(
        batch, ValidationReport(batch=batch, issues=()), policy=ReviewPolicy(confidence_floor=0.8)
    )
    with pytest.raises(ReviewError):
        apply_decisions(queue, (ReviewDecision(voucher_number="GHOST", approved=True),))
    with pytest.raises(ReviewError):
        apply_decisions(
            queue,
            (
                ReviewDecision(voucher_number="INV1", approved=True),
                ReviewDecision(voucher_number="INV1", approved=False),
            ),
        )


def test_apply_decisions_empty_after_review_fails() -> None:
    batch = _batch(_sales("INV1", confidence=0.5))
    queue = build_queue(
        batch, ValidationReport(batch=batch, issues=()), policy=ReviewPolicy(confidence_floor=0.8)
    )
    with pytest.raises(ReviewError):
        apply_decisions(queue, ())  # nothing approved -> nothing remains


# ── Pipeline wiring (opt-in) ─────────────────────────────────────────────────────


def _zoho_zip() -> bytes:
    files = {
        "Contacts.csv": "contact_id,contact_name,gst_no\nC1,Acme & Co,21A\nC2,Beta,21B\n",
        "Sales_Invoices.csv": "invoice_id,customer_id,total\nINV1,C1,1000\nINV2,C2,2000\n",
        "Customer_Payments.csv": "id,amount\nR1,500\n",
        "Vendor_Payments.csv": "id,amount\nP1,200\n",
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, text in files.items():
            zf.writestr(name, text)
    return buf.getvalue()


def test_full_default_sets_party_ledger_on_sales() -> None:
    export = run_pipeline_full(_zoho_zip(), company_name="Co", posting_date=DATE)
    root = etree.fromstring(export.vouchers_xml)
    sales = [
        v for v in root.findall("BODY/DATA/TALLYMESSAGE/VOUCHER") if v.get("VCHTYPE") == "Sales"
    ]
    assert all(v.findtext("PARTYLEDGERNAME") for v in sales)
    # default: no bill allocations
    assert root.find(".//BILLALLOCATIONS.LIST") is None


def test_full_enrich_adds_bill_allocations() -> None:
    export = run_pipeline_full(_zoho_zip(), company_name="Co", posting_date=DATE, enrich=True)
    validate_tally_xml(export.vouchers_xml)
    root = etree.fromstring(export.vouchers_xml)
    assert root.find(".//BILLALLOCATIONS.LIST") is not None


def test_full_prior_drops_already_imported() -> None:
    prior = PriorImportState(
        imported=(
            ImportedVoucherRef(
                voucher_number="INV1", voucher_type="Sales", date=DATE, amount="1000"
            ),
        )
    )
    export = run_pipeline_full(_zoho_zip(), company_name="Co", posting_date=DATE, prior=prior)
    root = etree.fromstring(export.vouchers_xml)
    numbers = {v.findtext("VOUCHERNUMBER") for v in root.findall("BODY/DATA/TALLYMESSAGE/VOUCHER")}
    assert "INV1" not in numbers and "INV2" in numbers


def test_full_prior_dropping_everything_fails() -> None:
    prior = PriorImportState(
        imported=tuple(
            ImportedVoucherRef(voucher_number=n, voucher_type=t, date=DATE, amount="0")
            for n, t in (("INV1", "Sales"), ("INV2", "Sales"), ("R1", "Receipt"), ("P1", "Payment"))
        )
    )
    with pytest.raises(ValidationError):
        run_pipeline_full(_zoho_zip(), company_name="Co", posting_date=DATE, prior=prior)
