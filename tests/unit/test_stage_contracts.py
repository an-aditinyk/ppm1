"""Stage boundary contracts.

Adapter stages (S01-S06) declare their boundaries by re-exporting the shared spine
types from ``contracts/source.py`` (so stages never import one another). The remaining
spine stages (S07-S12) still define their own small result types. This module checks
both: that the re-exports are the shared types, and that the stub stage models are
well-formed and frozen.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError as PydanticValidationError

from tallyimporter.contracts import source as spine
from tallyimporter.contracts.canonical import (
    CanonicalBatch,
    CanonicalLedgerEntry,
    CanonicalVoucher,
)
from tallyimporter.contracts.tally import TallyImportEnvelope, TallyLedgerEntry, TallyVoucher
from tallyimporter.stages.s01_ingest import contracts as s01
from tallyimporter.stages.s02_parse import contracts as s02
from tallyimporter.stages.s03_normalize import contracts as s03
from tallyimporter.stages.s04_classify import contracts as s04
from tallyimporter.stages.s05_map_ledgers import contracts as s05
from tallyimporter.stages.s06_canonicalize import contracts as s06
from tallyimporter.stages.s07_validate.contracts import ValidationIssue, ValidationReport
from tallyimporter.stages.s08_enrich.contracts import EnrichedBatch
from tallyimporter.stages.s09_number.contracts import NumberedBatch
from tallyimporter.stages.s10_reconcile.contracts import ReconciliationResult
from tallyimporter.stages.s11_review.contracts import ReviewDecision, ReviewItem, ReviewQueue
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
                        ledger_name="Conveyance", is_deemed_positive=True, amount=Decimal("-1")
                    ),
                    TallyLedgerEntry(
                        ledger_name="Bank", is_deemed_positive=False, amount=Decimal("1")
                    ),
                ),
            ),
        ),
    )


# ── Adapter stages re-export the shared spine types (no per-stage duplicates) ────


def test_adapter_boundaries_are_shared_spine_types() -> None:
    assert s01.IngestRequest is spine.IngestRequest
    assert s01.IngestedArchive is spine.IngestedArchive
    assert s02.SourceDataset is spine.SourceDataset
    assert s03.SourceDataset is spine.SourceDataset
    assert s04.ClassifiedTxn is spine.ClassifiedTxn
    assert s05.MappedTxn is spine.MappedTxn
    assert s06.CanonicalBatch is CanonicalBatch


def test_ingest_request_is_frozen_and_forbids_extra() -> None:
    req = spine.IngestRequest(source_system="zoho", location="/exports/jan.zip")
    with pytest.raises(PydanticValidationError):
        req.location = "y"  # type: ignore[misc]
    with pytest.raises(PydanticValidationError):
        spine.IngestRequest(source_system="zoho", location="x", extra="no")  # type: ignore[call-arg]


# ── Remaining stub stage result types (S07-S12) ─────────────────────────────────


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
    queue = ReviewQueue(
        batch=_batch(), pending=(ReviewItem(voucher_number="1", reason="low confidence"),)
    )
    decision = ReviewDecision(voucher_number="1", approved=True)
    assert queue.pending[0].voucher_number == "1"
    assert decision.approved is True


def test_s12_emit() -> None:
    req = EmitRequest(batch=_batch())
    result = EmitResult(envelope=_envelope(), xml=b"<ENVELOPE/>")
    assert req.batch.company_name == "ACME Pvt Ltd"
    assert result.xml == b"<ENVELOPE/>"


def test_stub_stage_models_are_frozen() -> None:
    nb = NumberedBatch(batch=_batch())
    with pytest.raises(PydanticValidationError):
        nb.batch = _batch()  # type: ignore[misc]
