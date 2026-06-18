"""S11 review — boundary contracts.

Gates low-confidence vouchers for human review.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from tallyimporter.contracts.canonical import CanonicalBatch

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class ReviewDecision(BaseModel):
    model_config = _FROZEN

    voucher_number: str = Field(min_length=1)
    approved: bool


class ReviewQueue(BaseModel):
    model_config = _FROZEN

    batch: CanonicalBatch
    pending_voucher_numbers: tuple[str, ...]
