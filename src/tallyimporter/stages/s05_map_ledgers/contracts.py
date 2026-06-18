"""S05 map ledgers — boundary contracts.

Maps source account names to exact Tally ledger names through a single point.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class LedgerMapping(BaseModel):
    model_config = _FROZEN

    source_name: str = Field(min_length=1)
    tally_name: str = Field(min_length=1)


class LedgerMappingTable(BaseModel):
    model_config = _FROZEN

    mappings: tuple[LedgerMapping, ...]
