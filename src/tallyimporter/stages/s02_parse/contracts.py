"""S02 parse — boundary contracts.

Parses raw documents into ordered, source-shaped records.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class SourceRecord(BaseModel):
    model_config = _FROZEN

    # Ordered key/value pairs keep parsing deterministic and immutable.
    fields: tuple[tuple[str, str], ...]


class ParsedRecordSet(BaseModel):
    model_config = _FROZEN

    source_system: str = Field(min_length=1)
    records: tuple[SourceRecord, ...]
