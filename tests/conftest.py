"""Shared test helpers."""

from __future__ import annotations

from pathlib import Path

from tallyimporter.contracts.canonical import CanonicalBatch

GOLDEN_DIR = Path(__file__).parent / "golden"
GOLDEN_INPUTS = GOLDEN_DIR / "inputs"
GOLDEN_EXPECTED = GOLDEN_DIR / "expected"


def load_canonical(path: Path) -> CanonicalBatch:
    """Load a canonical batch fixture from a JSON file."""
    return CanonicalBatch.model_validate_json(path.read_text(encoding="utf-8"))
