"""Tests for the Tally import-response parser (§2.3)."""

from __future__ import annotations

import pytest

from tallyimporter.contracts.errors import XmlContractError
from tallyimporter.stages.s12_emit.response import is_success, parse_import_result

_RESPONSE = (
    "<ENVELOPE><HEADER><VERSION>1</VERSION><STATUS>1</STATUS></HEADER>"
    "<BODY><DATA><IMPORTRESULT>"
    "<CREATED>2</CREATED><ALTERED>0</ALTERED><LASTVCHID>119</LASTVCHID>"
    "<LASTMID>0</LASTMID><COMBINED>0</COMBINED><IGNORED>0</IGNORED><ERRORS>0</ERRORS>"
    "</IMPORTRESULT></DATA></BODY></ENVELOPE>"
)


def test_parses_clean_utf8_response() -> None:
    r = parse_import_result(_RESPONSE.encode("utf-8"))
    assert r.created == 2
    assert r.last_vch_id == 119
    assert r.errors == 0
    assert is_success(r)


def test_parses_utf16_response() -> None:
    r = parse_import_result(_RESPONSE.encode("utf-16"))  # BOM-marked, like Tally
    assert r.created == 2
    assert r.last_vch_id == 119


def test_tolerates_leading_spaces_in_numbers() -> None:
    spaced = _RESPONSE.replace("<CREATED>2</CREATED>", "<CREATED>  2 </CREATED>")
    assert parse_import_result(spaced.encode("utf-8")).created == 2


def test_recovers_from_embedded_control_char() -> None:
    # Tally embeds &#4; in real exports; the recovering parser must cope.
    dirty = _RESPONSE.replace("<STATUS>1</STATUS>", "<STATUS>&#4; 1</STATUS>")
    r = parse_import_result(dirty.encode("utf-16"))
    assert r.created == 2


def test_is_success_false_on_errors_or_ignored() -> None:
    with_err = _RESPONSE.replace("<ERRORS>0</ERRORS>", "<ERRORS>3</ERRORS>")
    r = parse_import_result(with_err.encode("utf-8"))
    assert r.errors == 3
    assert not is_success(r)
    with_ign = _RESPONSE.replace("<IGNORED>0</IGNORED>", "<IGNORED>1</IGNORED>")
    assert not is_success(parse_import_result(with_ign.encode("utf-8")))


def test_rejects_wrong_root() -> None:
    with pytest.raises(XmlContractError):
        parse_import_result(b"<?xml version='1.0'?><NOPE/>")


def test_rejects_missing_importresult() -> None:
    bad = "<ENVELOPE><HEADER/><BODY><DATA/></BODY></ENVELOPE>"
    with pytest.raises(XmlContractError):
        parse_import_result(bad.encode("utf-8"))


def test_rejects_non_integer_field() -> None:
    bad = _RESPONSE.replace("<CREATED>2</CREATED>", "<CREATED>two</CREATED>")
    with pytest.raises(XmlContractError):
        parse_import_result(bad.encode("utf-8"))


def test_rejects_missing_field() -> None:
    bad = _RESPONSE.replace("<ERRORS>0</ERRORS>", "")
    with pytest.raises(XmlContractError):
        parse_import_result(bad.encode("utf-8"))


def test_rejects_garbage() -> None:
    with pytest.raises(XmlContractError):
        parse_import_result(b"not xml at all")
