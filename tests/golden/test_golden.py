"""Golden-file snapshot tests (§6.3).

Each canonical input fixture, run through the S12 vertical slice, must produce
byte-stable XML identical to its committed ``.xml`` snapshot. Set ``UPDATE_GOLDEN=1``
to intentionally regenerate the snapshots (``make update-golden``); CI compares
strictly.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tallyimporter.stages.s12_emit.mapper import canonical_to_tally
from tallyimporter.stages.s12_emit.serializer import serialize_envelope
from tallyimporter.stages.s12_emit.validator import validate_tally_xml
from tests.conftest import GOLDEN_EXPECTED, GOLDEN_INPUTS, load_canonical

_INPUTS = sorted(GOLDEN_INPUTS.glob("*.json"))


def _expected_path(input_path: Path) -> Path:
    return GOLDEN_EXPECTED / f"{input_path.stem}.xml"


def test_inputs_exist() -> None:
    assert len(_INPUTS) >= 3


@pytest.mark.parametrize("input_path", _INPUTS, ids=lambda p: p.stem)
def test_golden_matches(input_path: Path) -> None:
    batch = load_canonical(input_path)
    actual = serialize_envelope(canonical_to_tally(batch))
    expected_path = _expected_path(input_path)

    if os.environ.get("UPDATE_GOLDEN") == "1":
        expected_path.write_bytes(actual)

    assert expected_path.exists(), f"missing golden snapshot: {expected_path}"
    assert actual == expected_path.read_bytes()
    # The committed snapshot must itself satisfy the §2.2 contract.
    validate_tally_xml(actual)
