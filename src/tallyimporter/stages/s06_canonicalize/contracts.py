"""S06 canonicalize — boundary contracts.

Assembles the source-agnostic ``CanonicalBatch`` from mapped, classified records.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from tallyimporter.contracts.canonical import CanonicalBatch

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class CanonicalizeResult(BaseModel):
    model_config = _FROZEN

    batch: CanonicalBatch
