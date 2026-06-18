"""S08 enrich — boundary contracts.

Attaches confidence scoring and (later) bill allocations / GST detail.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from tallyimporter.contracts.canonical import CanonicalBatch

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class EnrichedBatch(BaseModel):
    model_config = _FROZEN

    batch: CanonicalBatch
