"""S01 ingest — boundary declaration.

The boundary types live in the shared spine (`contracts/source.py`) so stages never
import one another. This module re-exports the stage's input/output for clarity.
"""

from __future__ import annotations

from tallyimporter.contracts.source import IngestedArchive, IngestRequest

__all__ = ["IngestRequest", "IngestedArchive"]
