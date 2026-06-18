"""S11 - Review: gate low-confidence / flagged vouchers for human approval.

Pure core: ``build_queue`` decides who needs review; ``apply_decisions`` returns the
approved-only batch. The human interaction is the imperative shell. A pending voucher
without an explicit approval is withheld (fail-safe). Imports only ``contracts/``.
"""

from __future__ import annotations

from tallyimporter.contracts.canonical import CanonicalBatch
from tallyimporter.contracts.errors import ReviewError
from tallyimporter.contracts.validation import ValidationReport
from tallyimporter.stages.s11_review.contracts import (
    ReviewDecision,
    ReviewItem,
    ReviewPolicy,
    ReviewQueue,
)


def build_queue(
    batch: CanonicalBatch, report: ValidationReport, *, policy: ReviewPolicy
) -> ReviewQueue:
    """Queue vouchers below the confidence floor or carrying a gated-severity issue."""
    gated = {i.voucher_number for i in report.issues if i.severity in policy.gate_on_severities}
    pending: list[ReviewItem] = []
    for v in batch.vouchers:
        reasons: list[str] = []
        if v.confidence < policy.confidence_floor:
            reasons.append(f"confidence {v.confidence} < floor {policy.confidence_floor}")
        if v.voucher_number in gated:
            reasons.append("validation issue")
        if reasons:
            pending.append(ReviewItem(voucher_number=v.voucher_number, reason="; ".join(reasons)))
    return ReviewQueue(batch=batch, pending=tuple(pending))


def apply_decisions(queue: ReviewQueue, decisions: tuple[ReviewDecision, ...]) -> CanonicalBatch:
    """Return the batch with pending vouchers kept only if explicitly approved."""
    pending_nums = {item.voucher_number for item in queue.pending}
    verdict: dict[str, bool] = {}
    for d in decisions:
        if d.voucher_number not in pending_nums:
            raise ReviewError(
                f"decision for non-pending voucher {d.voucher_number}",
                code="unknown_voucher",
                detail={"voucher": d.voucher_number},
            )
        if d.voucher_number in verdict and verdict[d.voucher_number] != d.approved:
            raise ReviewError(
                f"conflicting decisions for {d.voucher_number}",
                code="conflict",
                detail={"voucher": d.voucher_number},
            )
        verdict[d.voucher_number] = d.approved

    approved = {n for n, ok in verdict.items() if ok}
    kept = tuple(
        v
        for v in queue.batch.vouchers
        if v.voucher_number not in pending_nums or v.voucher_number in approved
    )
    if not kept:
        raise ReviewError("no vouchers remain after review", code="empty_after_review")
    return CanonicalBatch(
        company_name=queue.batch.company_name,
        source_system=queue.batch.source_system,
        vouchers=kept,
    )
