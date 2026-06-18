"""S03 normalize — boundary contracts.

Normalizes encodings, dates, amounts and field names per source.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class NormalizedRecord(BaseModel):
    model_config = _FROZEN

    fields: tuple[tuple[str, str], ...]


class NormalizedRecordSet(BaseModel):
    model_config = _FROZEN

    source_system: str = Field(min_length=1)
    records: tuple[NormalizedRecord, ...]
