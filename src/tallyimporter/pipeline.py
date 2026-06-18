"""End-to-end pipeline orchestrator (imperative shell).

Composes the stages S01→S12 into the product: a source export → verified Tally import
XML. This module is not a stage; it may import stages (stages may not import each other).
The pure stage functions do the work; this wires them and applies the
block-on-error policy.

S08 (enrich), S10 (reconcile) and S11 (review) are deferred per their build sheets and
are not in this path.
"""

from __future__ import annotations

from datetime import date

from tallyimporter.contracts.canonical import CanonicalBatch
from tallyimporter.contracts.errors import ValidationError
from tallyimporter.contracts.source import SourceProfile
from tallyimporter.contracts.tally import TallyExport
from tallyimporter.profiles.zoho import ZOHO_PROFILE
from tallyimporter.stages.s01_ingest.ingest import ingest
from tallyimporter.stages.s02_parse.parse import parse
from tallyimporter.stages.s03_normalize.normalize import normalize
from tallyimporter.stages.s04_classify.classify import classify
from tallyimporter.stages.s05_map_ledgers.map_ledgers import map_ledgers
from tallyimporter.stages.s06_canonicalize.canonicalize import canonicalize
from tallyimporter.stages.s07_validate.validate import has_errors, validate
from tallyimporter.stages.s09_number.number import assign_numbers
from tallyimporter.stages.s12_emit.mapper import canonical_to_tally
from tallyimporter.stages.s12_emit.masters import masters_for_batch
from tallyimporter.stages.s12_emit.serializer import serialize_envelope, serialize_masters
from tallyimporter.stages.s12_emit.validator import validate_masters_xml, validate_tally_xml


def _build_batch(
    archive: bytes,
    *,
    company_name: str,
    posting_date: date,
    profile: SourceProfile,
    financial_year: tuple[date, date] | None,
    confidence_floor: float,
) -> CanonicalBatch:
    """Run S01→S07/S09 and return the validated, numbered canonical batch."""
    archived = ingest(archive, profile)
    parsed = parse(archived, profile)
    normalized = normalize(parsed, profile)
    classified = classify(normalized, profile)
    mapped = map_ledgers(classified, normalized, profile)
    batch = canonicalize(
        mapped,
        company_name=company_name,
        source_system=profile.source_system,
        posting_date=posting_date,
    )

    report = validate(batch, financial_year=financial_year, confidence_floor=confidence_floor)
    if has_errors(report):
        blocking = [i for i in report.issues if i.severity == "error"]
        raise ValidationError(
            f"{len(blocking)} blocking validation error(s); first: {blocking[0].message}"
        )
    return assign_numbers(batch).batch


def _emit_vouchers(batch: CanonicalBatch) -> bytes:
    xml = serialize_envelope(canonical_to_tally(batch))
    validate_tally_xml(xml)
    return xml


def _emit_masters(batch: CanonicalBatch, profile: SourceProfile) -> bytes:
    env = masters_for_batch(
        batch,
        group_of=profile.ledger_groups,
        default_group=profile.default_ledger_group,
    )
    xml = serialize_masters(env)
    validate_masters_xml(xml)
    return xml


def run_pipeline(
    archive: bytes,
    *,
    company_name: str,
    posting_date: date,
    profile: SourceProfile = ZOHO_PROFILE,
    financial_year: tuple[date, date] | None = None,
    confidence_floor: float = 0.0,
) -> bytes:
    """Run a source export ZIP through to verified Tally **voucher** import XML bytes.

    Raises a typed stage error on any boundary violation, or ``ValidationError`` if S07
    reports a blocking (`error`) issue. The bytes have already passed ``validate_tally_xml``.
    """
    batch = _build_batch(
        archive,
        company_name=company_name,
        posting_date=posting_date,
        profile=profile,
        financial_year=financial_year,
        confidence_floor=confidence_floor,
    )
    return _emit_vouchers(batch)


def run_pipeline_full(
    archive: bytes,
    *,
    company_name: str,
    posting_date: date,
    profile: SourceProfile = ZOHO_PROFILE,
    financial_year: tuple[date, date] | None = None,
    confidence_floor: float = 0.0,
) -> TallyExport:
    """Run a source export ZIP to BOTH import files a fresh Tally company needs:
    ``masters_xml`` (import first) and ``vouchers_xml`` (import second). Both have
    passed their structural validators."""
    batch = _build_batch(
        archive,
        company_name=company_name,
        posting_date=posting_date,
        profile=profile,
        financial_year=financial_year,
        confidence_floor=confidence_floor,
    )
    return TallyExport(
        masters_xml=_emit_masters(batch, profile),
        vouchers_xml=_emit_vouchers(batch),
    )
