"""S04 classify — boundary contracts.

Determines a Tally voucher type per normalized record, with explicit confidence.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class ClassifiedRecord(BaseModel):
    model_config = _FROZEN

    voucher_type: str = Field(min_length=1)
    fields: tuple[tuple[str, str], ...]
    confidence: float = Field(ge=0.0, le=1.0)


class ClassifiedRecordSet(BaseModel):
    model_config = _FROZEN

    source_system: str = Field(min_length=1)
    records: tuple[ClassifiedRecord, ...]
