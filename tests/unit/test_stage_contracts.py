"""Smoke tests for the 12 stage boundary contracts.

Each stage declares typed input/output models referencing the spine. These tests
construct each model with valid data, confirming the boundary stubs are well-formed
and frozen.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError as PydanticValidationError

from tallyimporter.contracts.canonical import (
    CanonicalBatch,
    CanonicalLedgerEntry,
    CanonicalVoucher,
)
from tallyimporter.contracts.tally import TallyImportEnvelope, TallyLedgerEntry, TallyVoucher
from tallyimporter.stages.s01_ingest.contracts import IngestRequest, RawSourceDocument
from tallyimporter.stages.s02_parse.contracts import ParsedRecordSet, SourceRecord
from tallyimporter.stages.s03_normalize.contracts import (
    NormalizedRecord,
    NormalizedRecordSet,
)
from tallyimporter.stages.s04_classify.contracts import (
    ClassifiedRecord,
    ClassifiedRecordSet,
)
from tallyimporter.stages.s05_map_ledgers.contracts import (
    LedgerMapping,
    LedgerMappingTable,
)
from tallyimporter.stages.s06_canonicalize.contracts import CanonicalizeResult
from tallyimporter.stages.s07_validate.contracts import ValidationIssue, ValidationReport
from tallyimporter.stages.s08_enrich.contracts import EnrichedBatch
from tallyimporter.stages.s09_number.contracts import NumberedBatch
from tallyimporter.stages.s10_reconcile.contracts import ReconciliationResult
from tallyimporter.stages.s11_review.contracts import ReviewDecision, ReviewQueue
from tallyimporter.stages.s12_emit.contracts import EmitRequest, EmitResult


def _batch() -> CanonicalBatch:
    return CanonicalBatch(
        company_name="ACME Pvt Ltd",
        source_system="zoho",
        vouchers=(
            CanonicalVoucher(
                voucher_type="Payment",
                date=date(2008, 4, 2),
                voucher_number="1",
                narration=None,
                entries=(
                    CanonicalLedgerEntry(
                        ledger_name="Conveyance", is_debit=True, amount=Decimal("1")
                    ),
                    CanonicalLedgerEntry(ledger_name="Bank", is_debit=False, amount=Decimal("1")),
                ),
            ),
        ),
    )


def _envelope() -> TallyImportEnvelope:
    return TallyImportEnvelope(
        company_name="ACME Pvt Ltd",
        vouchers=(
            TallyVoucher(
                vch_type="Payment",
                date=date(2008, 4, 2),
                voucher_number="1",
                narration=None,
                entries=(
                    TallyLedgerEntry(
                        ledger_name="Conveyance",
                        is_deemed_positive=True,
                        amount=Decimal("-1"),
                    ),
                    TallyLedgerEntry(
                        ledger_name="Bank",
                        is_deemed_positive=False,
                        amount=Decimal("1"),
                    ),
                ),
            ),
        ),
    )


def test_s01_ingest() -> None:
    req = IngestRequest(source_system="zoho", location="/exports/jan.csv")
    doc = RawSourceDocument(source_system="zoho", filename="jan.csv", content=b"a,b\n1,2\n")
    assert req.source_system == "zoho"
    assert doc.content == b"a,b\n1,2\n"


def test_s02_parse() -> None:
    rec = SourceRecord(fields=(("date", "2026-01-01"), ("amount", "100")))
    rs = ParsedRecordSet(source_system="zoho", records=(rec,))
    assert rs.records[0].fields[0] == ("date", "2026-01-01")


def test_s03_normalize() -> None:
    rec = NormalizedRecord(fields=(("date", "20260101"),))
    rs = NormalizedRecordSet(source_system="zoho", records=(rec,))
    assert rs.records[0].fields == (("date", "20260101"),)


def test_s04_classify() -> None:
    rec = ClassifiedRecord(voucher_type="Payment", fields=(("k", "v"),), confidence=0.9)
    rs = ClassifiedRecordSet(source_system="zoho", records=(rec,))
    assert rs.records[0].voucher_type == "Payment"


def test_s04_classify_rejects_out_of_range_confidence() -> None:
    with pytest.raises(PydanticValidationError):
        ClassifiedRecord(voucher_type="Payment", fields=(), confidence=1.5)


def test_s05_map_ledgers() -> None:
    table = LedgerMappingTable(
        mappings=(LedgerMapping(source_name="Bank A/c", tally_name="Bank of India"),)
    )
    assert table.mappings[0].tally_name == "Bank of India"


def test_s06_canonicalize() -> None:
    result = CanonicalizeResult(batch=_batch())
    assert result.batch.company_name == "ACME Pvt Ltd"


def test_s07_validate() -> None:
    report = ValidationReport(
        batch=_batch(),
        issues=(ValidationIssue(voucher_number="1", message="low confidence", severity="warning"),),
    )
    assert report.issues[0].severity == "warning"


def test_s07_rejects_bad_severity() -> None:
    with pytest.raises(PydanticValidationError):
        ValidationIssue(voucher_number="1", message="x", severity="fatal")  # type: ignore[arg-type]


def test_s08_enrich() -> None:
    assert EnrichedBatch(batch=_batch()).batch.source_system == "zoho"


def test_s09_number() -> None:
    assert NumberedBatch(batch=_batch()).batch.vouchers[0].voucher_number == "1"


def test_s10_reconcile() -> None:
    result = ReconciliationResult(batch=_batch(), unmatched_voucher_numbers=("1",))
    assert result.unmatched_voucher_numbers == ("1",)


def test_s11_review() -> None:
    queue = ReviewQueue(batch=_batch(), pending_voucher_numbers=("1",))
    decision = ReviewDecision(voucher_number="1", approved=True)
    assert queue.pending_voucher_numbers == ("1",)
    assert decision.approved is True


def test_s12_emit() -> None:
    req = EmitRequest(batch=_batch())
    result = EmitResult(envelope=_envelope(), xml=b"<ENVELOPE/>")
    assert req.batch.company_name == "ACME Pvt Ltd"
    assert result.xml == b"<ENVELOPE/>"


def test_stage_contracts_are_frozen() -> None:
    req = IngestRequest(source_system="zoho", location="x")
    with pytest.raises(PydanticValidationError):
        req.location = "y"  # type: ignore[misc]


def test_stage_contracts_forbid_extra() -> None:
    with pytest.raises(PydanticValidationError):
        IngestRequest(source_system="zoho", location="x", extra="no")  # type: ignore[call-arg]
