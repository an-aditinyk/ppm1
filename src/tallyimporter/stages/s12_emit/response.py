"""Parse a Tally import-response envelope (§2.3) into ``TallyImportResult``.

Tally writes responses/exports as **UTF-16** (BOM) and may embed control characters
(e.g. ``&#4;``) that break a strict XML parser — so this decodes by BOM and uses a
recovering parser (see smoke_import/ROUNDTRIP_FINDINGS.md). Our emitter stays UTF-8 and
is unaffected; this is the read side. Imports only ``contracts/``.
"""

from __future__ import annotations

from lxml import etree

from tallyimporter.contracts.errors import XmlContractError
from tallyimporter.contracts.tally import TallyImportResult


def _decode(raw: bytes) -> str:
    """Decode the response by BOM: UTF-16 if marked, else UTF-8 (BOM-tolerant)."""
    try:
        if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
            return raw.decode("utf-16")
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise XmlContractError(f"response is not decodable text: {exc}") from exc


def _int(tag: str, text: str | None) -> int:
    if text is None:
        raise XmlContractError(f"IMPORTRESULT missing <{tag}>")
    try:
        return int(text.strip())
    except ValueError as exc:
        raise XmlContractError(f"IMPORTRESULT/{tag} is not an integer: {text!r}") from exc


def parse_import_result(response: bytes) -> TallyImportResult:
    """Parse a Tally import-response envelope (§2.3). Raises ``XmlContractError`` on any
    malformed/missing field; returns a ``TallyImportResult`` otherwise."""
    text = _decode(response)
    parser = etree.XMLParser(recover=True, huge_tree=True)
    try:
        root = etree.fromstring(text.encode("utf-8"), parser)
    except etree.XMLSyntaxError as exc:
        raise XmlContractError(f"response is not well-formed XML: {exc}") from exc
    if root is None or root.tag != "ENVELOPE":
        got = None if root is None else root.tag
        raise XmlContractError(f"response root must be ENVELOPE, got {got!r}")

    r = root.find("BODY/DATA/IMPORTRESULT")
    if r is None:
        raise XmlContractError("response has no BODY/DATA/IMPORTRESULT")

    return TallyImportResult(
        created=_int("CREATED", r.findtext("CREATED")),
        altered=_int("ALTERED", r.findtext("ALTERED")),
        last_vch_id=_int("LASTVCHID", r.findtext("LASTVCHID")),
        last_m_id=_int("LASTMID", r.findtext("LASTMID")),
        combined=_int("COMBINED", r.findtext("COMBINED")),
        ignored=_int("IGNORED", r.findtext("IGNORED")),
        errors=_int("ERRORS", r.findtext("ERRORS")),
    )


def is_success(result: TallyImportResult) -> bool:
    """True if Tally reported no errors and nothing ignored."""
    return result.errors == 0 and result.ignored == 0
