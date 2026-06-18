"""S09 number — boundary contracts.

Assigns / verifies unique voucher numbers within the batch.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from tallyimporter.contracts.canonical import CanonicalBatch

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class NumberedBatch(BaseModel):
    model_config = _FROZEN

    batch: CanonicalBatch
