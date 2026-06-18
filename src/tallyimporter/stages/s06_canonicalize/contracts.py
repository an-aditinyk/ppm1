"""S06 canonicalize — boundary declaration.

Input is `MappedTxn` (shared spine); output is the frozen `CanonicalBatch` — the
source-agnostic seam.
"""

from __future__ import annotations

from tallyimporter.contracts.canonical import CanonicalBatch
from tallyimporter.contracts.source import MappedTxn

__all__ = ["CanonicalBatch", "MappedTxn"]
