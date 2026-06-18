"""S07 validate — boundary contracts.

Validates canonical business rules and reports typed issues.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from tallyimporter.contracts.canonical import CanonicalBatch

_FROZEN = ConfigDict(frozen=True, extra="forbid")

Severity = Literal["error", "warning"]


class ValidationIssue(BaseModel):
    model_config = _FROZEN

    voucher_number: str = Field(min_length=1)
    message: str = Field(min_length=1)
    severity: Severity


class ValidationReport(BaseModel):
    model_config = _FROZEN

    batch: CanonicalBatch
    issues: tuple[ValidationIssue, ...]
