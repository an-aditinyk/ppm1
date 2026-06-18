"""S07 — Validate: check a CanonicalBatch against business rules and return a typed
report (it reports; it does not raise on business findings). Imports only ``contracts/``
and ``core/``.
"""

from __future__ import annotations

from datetime import date

from tallyimporter.contracts.canonical import CanonicalBatch
from tallyimporter.stages.s07_validate.contracts import ValidationIssue, ValidationReport


def validate(
    batch: CanonicalBatch,
    *,
    financial_year: tuple[date, date] | None = None,
    confidence_floor: float = 0.0,
) -> ValidationReport:
    """Return a report of issues. `error` severity = must-block; `warning` = informational.

    Structural invariants (balance, unique numbers) are guaranteed by the canonical model
    and are not re-checked here (D-S07.4).
    """
    issues: list[ValidationIssue] = []
    for v in batch.vouchers:
        if financial_year is not None:
            start, end = financial_year
            if not (start <= v.date <= end):
                issues.append(
                    ValidationIssue(
                        voucher_number=v.voucher_number,
                        message=(
                            f"date {v.date:%Y%m%d} outside financial year "
                            f"{start:%Y%m%d}-{end:%Y%m%d}"
                        ),
                        severity="error",
                    )
                )
        if v.confidence < confidence_floor:
            issues.append(
                ValidationIssue(
                    voucher_number=v.voucher_number,
                    message=f"confidence {v.confidence} below floor {confidence_floor}",
                    severity="warning",
                )
            )
    return ValidationReport(batch=batch, issues=tuple(issues))


def has_errors(report: ValidationReport) -> bool:
    """True if any issue is an error (the orchestrator blocks on this)."""
    return any(i.severity == "error" for i in report.issues)
