"""S11 review - boundary contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from tallyimporter.contracts.canonical import CanonicalBatch

_FROZEN = ConfigDict(frozen=True, extra="forbid")

Severity = Literal["error", "warning"]


class ReviewPolicy(BaseModel):
    model_config = _FROZEN

    confidence_floor: float = Field(default=1.0, ge=0.0, le=1.0)
    gate_on_severities: tuple[Severity, ...] = ("error",)


class ReviewItem(BaseModel):
    model_config = _FROZEN

    voucher_number: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ReviewQueue(BaseModel):
    model_config = _FROZEN

    batch: CanonicalBatch
    pending: tuple[ReviewItem, ...]


class ReviewDecision(BaseModel):
    model_config = _FROZEN

    voucher_number: str = Field(min_length=1)
    approved: bool
