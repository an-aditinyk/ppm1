"""S01 ingest — boundary contracts.

Reads raw source artifacts into typed payloads. Transformation logic arrives in a
later phase; Phase 1 declares the typed boundary only.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class IngestRequest(BaseModel):
    model_config = _FROZEN

    source_system: str = Field(min_length=1)
    location: str = Field(min_length=1)


class RawSourceDocument(BaseModel):
    model_config = _FROZEN

    source_system: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    content: bytes
