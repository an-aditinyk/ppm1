"""Typed boundary errors.

Every boundary in TallyImporter validates its input and raises one of these on
violation. Nothing is silently coerced or dropped.
"""

from __future__ import annotations


class TallyImporterError(Exception):
    """Base class for all typed boundary errors."""


class MoneyError(TallyImporterError):
    """Raised when a money value is not a valid finite Decimal-representable number."""


class BalanceError(TallyImporterError):
    """Raised when a voucher's entries do not net to zero."""


class ValidationError(TallyImporterError):
    """Raised when a model or document violates a structural/business rule."""


class XmlContractError(TallyImporterError):
    """Raised when generated/parsed Tally XML violates the §2 contract."""


class StageError(TallyImporterError):
    """Shared base for fail-loud errors raised by pipeline stages.

    Carries machine-inspectable context so the orchestrator/UI can report which
    stage failed and why without string-parsing the message.
    """

    stage: str = "unknown"

    def __init__(self, message: str, *, code: str, detail: dict[str, str] | None = None) -> None:
        super().__init__(f"[{self.stage}:{code}] {message}")
        self.code = code
        self.message = message
        self.detail: dict[str, str] = detail or {}


class IngestError(StageError):
    """S01 — archive could not be ingested (corrupt zip, missing/empty artifact, encoding)."""

    stage = "s01_ingest"


class ParseError(StageError):
    """S02 — records could not be parsed (malformed rows, dup ids, unjoinable refs)."""

    stage = "s02_parse"


class NormalizeError(StageError):
    """S03 — a value/field could not be normalized."""

    stage = "s03_normalize"


class ClassifyError(StageError):
    """S04 — a document could not be classified to a voucher type."""

    stage = "s04_classify"


class MapError(StageError):
    """S05 — a source account/party could not be mapped to a Tally ledger."""

    stage = "s05_map_ledgers"


class CanonicalizeError(StageError):
    """S06 — records could not be assembled into a canonical batch."""

    stage = "s06_canonicalize"


class EnrichError(StageError):
    """S08 — enrichment would violate an invariant (e.g. break a voucher's balance)."""

    stage = "s08_enrich"


class ReconcileError(StageError):
    """S10 — reconciliation could not be performed (e.g. ambiguous prior match)."""

    stage = "s10_reconcile"


class ReviewError(StageError):
    """S11 — a review decision was invalid (unknown/conflicting/none approved)."""

    stage = "s11_review"
