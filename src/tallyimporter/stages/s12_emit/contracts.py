"""S12 emit — boundary contracts.

Maps canonical → Tally model, serializes XML, and validates output. This is the
Phase 1 vertical slice; the mapper, serializer and validator live alongside.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from tallyimporter.contracts.canonical import CanonicalBatch
from tallyimporter.contracts.tally import TallyImportEnvelope

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class EmitRequest(BaseModel):
    model_config = _FROZEN

    batch: CanonicalBatch


class EmitResult(BaseModel):
    model_config = _FROZEN

    envelope: TallyImportEnvelope
    xml: bytes
