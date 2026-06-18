"""Tests for the Zoho adapter pipeline (S01-S07, S09) and the orchestrator."""

from __future__ import annotations

import io
import zipfile
from datetime import date
from decimal import Decimal

import pytest
from lxml import etree

from tallyimporter.contracts.errors import (
    ClassifyError,
    IngestError,
    MapError,
    NormalizeError,
    ParseError,
    ValidationError,
)
from tallyimporter.contracts.source import (
    PARTY_SENTINEL,
    ArtifactRole,
    ClassifiedTxn,
    MappedTxn,
    SourceDataset,
    SourceTable,
)
from tallyimporter.pipeline import run_pipeline
from tallyimporter.profiles.zoho import ZOHO_PROFILE
from tallyimporter.stages.s01_ingest.ingest import ingest
from tallyimporter.stages.s02_parse.parse import parse
from tallyimporter.stages.s03_normalize.normalize import normalize
from tallyimporter.stages.s04_classify.classify import classify
from tallyimporter.stages.s05_map_ledgers.map_ledgers import map_ledgers
from tallyimporter.stages.s06_canonicalize.canonicalize import canonicalize
from tallyimporter.stages.s07_validate.validate import has_errors, validate
from tallyimporter.stages.s09_number.number import assign_numbers

DATE = date(2026, 4, 1)

_CONTACTS = "contact_id,contact_name,gst_no\nC1,Acme & Co,21ABCDE0001F1Z5\nC2,Globex,21ABCDE2Z5\n"
_INVOICES = "invoice_id,customer_id,total\nINV1,C1,1000\nINV2,C2,2500\n"
_RECEIPTS = "id,amount\nR1,1000\nR2,-300\n"  # R2 negative = reversal
_PAYMENTS = "id,amount\nP1,750\n"


def _zip(files: dict[str, str], *, raw: dict[str, bytes] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, text in files.items():
            zf.writestr(name, text)
        for name, data in (raw or {}).items():
            zf.writestr(name, data)
    return buf.getvalue()


def _valid_files() -> dict[str, str]:
    return {
        "Contacts.csv": _CONTACTS,
        "Sales_Invoices.csv": _INVOICES,
        "Customer_Payments.csv": _RECEIPTS,
        "Vendor_Payments.csv": _PAYMENTS,
    }


# ── End-to-end ───────────────────────────────────────────────────────────────────


def test_pipeline_end_to_end() -> None:
    xml = run_pipeline(_zip(_valid_files()), company_name="Test Co", posting_date=DATE)
    root = etree.fromstring(xml)
    vs = root.findall("BODY/DATA/TALLYMESSAGE/VOUCHER")
    assert len(vs) == 5  # 2 sales + 2 receipts + 1 payment
    types = sorted(v.get("VCHTYPE") for v in vs)
    assert types == ["Payment", "Receipt", "Receipt", "Sales", "Sales"]
    # sales invoice INV1 → Dr Acme & Co (escaped) / Cr Sales Account
    inv1 = next(v for v in vs if v.findtext("VOUCHERNUMBER") == "INV1")
    lines = inv1.findall("ALLLEDGERENTRIES.LIST")
    assert lines[0].findtext("LEDGERNAME") == "Acme & Co"
    assert lines[0].findtext("ISDEEMEDPOSITIVE") == "Yes"
    assert lines[0].findtext("AMOUNT") == "-1000.00"
    assert lines[1].findtext("LEDGERNAME") == "Sales Account"
    assert lines[1].findtext("AMOUNT") == "1000.00"


def test_pipeline_deterministic() -> None:
    z = _zip(_valid_files())
    assert run_pipeline(z, company_name="C", posting_date=DATE) == run_pipeline(
        z, company_name="C", posting_date=DATE
    )


def test_pipeline_blocks_on_validation_error() -> None:
    # FY that excludes the posting date → blocking error.
    with pytest.raises(ValidationError):
        run_pipeline(
            _zip(_valid_files()),
            company_name="C",
            posting_date=DATE,
            financial_year=(date(2024, 4, 1), date(2025, 3, 31)),
        )


# ── S01 ingest ───────────────────────────────────────────────────────────────────


def test_ingest_records_extras_and_excludes_projects() -> None:
    files = _valid_files()
    files["Projects.csv"] = "id,amount\nX,1\n"
    arch = ingest(_zip(files, raw={"random.txt": b"hi"}), ZOHO_PROFILE)
    assert "random.txt" in arch.extra_artifacts_seen
    assert "Projects.csv" in arch.extra_artifacts_seen  # excluded, not consumed
    roles = {a.role for a in arch.artifacts}
    assert ArtifactRole.SALES_INVOICES in roles
    assert ArtifactRole.SALES_ORDERS not in roles


def test_ingest_missing_required_fails() -> None:
    files = _valid_files()
    del files["Customer_Payments.csv"]
    with pytest.raises(IngestError) as e:
        ingest(_zip(files), ZOHO_PROFILE)
    assert e.value.code == "missing_required"


def test_ingest_empty_artifact_fails() -> None:
    files = _valid_files()
    files["Customer_Payments.csv"] = "   \n"
    with pytest.raises(IngestError) as e:
        ingest(_zip(files), ZOHO_PROFILE)
    assert e.value.code == "empty_artifact"


def test_ingest_bad_encoding_fails() -> None:
    files = _valid_files()
    del files["Vendor_Payments.csv"]
    bad = {"Vendor_Payments.csv": b"id,amount\n\xff\xfe\x80x,1\n"}
    with pytest.raises(IngestError) as e:
        ingest(_zip(files, raw=bad), ZOHO_PROFILE)
    assert e.value.code == "encoding"


def test_ingest_corrupt_zip_fails() -> None:
    with pytest.raises(IngestError) as e:
        ingest(b"not a zip", ZOHO_PROFILE)
    assert e.value.code == "corrupt_zip"


# ── S02 parse ────────────────────────────────────────────────────────────────────


def test_parse_duplicate_id_fails() -> None:
    files = _valid_files()
    files["Customer_Payments.csv"] = "id,amount\nR1,1\nR1,2\n"
    with pytest.raises(ParseError) as e:
        parse(ingest(_zip(files), ZOHO_PROFILE), ZOHO_PROFILE)
    assert e.value.code == "duplicate_id"


def test_parse_ragged_row_fails() -> None:
    files = _valid_files()
    files["Vendor_Payments.csv"] = "id,amount\nP1\n"
    with pytest.raises(ParseError) as e:
        parse(ingest(_zip(files), ZOHO_PROFILE), ZOHO_PROFILE)
    assert e.value.code == "ragged_row"


def test_parse_unjoinable_party_fails() -> None:
    files = _valid_files()
    files["Sales_Invoices.csv"] = "invoice_id,customer_id,total\nINV1,NOPE,1000\n"
    with pytest.raises(ParseError) as e:
        parse(ingest(_zip(files), ZOHO_PROFILE), ZOHO_PROFILE)
    assert e.value.code == "unjoinable_id"


def test_parse_missing_column_fails() -> None:
    files = _valid_files()
    files["Sales_Invoices.csv"] = "invoice_id,total\nINV1,1000\n"  # no customer_id
    with pytest.raises(ParseError):
        parse(ingest(_zip(files), ZOHO_PROFILE), ZOHO_PROFILE)


# ── S03 normalize ────────────────────────────────────────────────────────────────


def test_normalize_bad_amount_fails() -> None:
    files = _valid_files()
    files["Vendor_Payments.csv"] = "id,amount\nP1,notmoney\n"
    ds = parse(ingest(_zip(files), ZOHO_PROFILE), ZOHO_PROFILE)
    with pytest.raises(NormalizeError) as e:
        normalize(ds, ZOHO_PROFILE)
    assert e.value.code == "bad_amount"


def test_normalize_trims_and_canonicalizes_amount() -> None:
    ds = normalize(parse(ingest(_zip(_valid_files()), ZOHO_PROFILE), ZOHO_PROFILE), ZOHO_PROFILE)
    inv = next(t for t in ds.tables if t.role == ArtifactRole.SALES_INVOICES)
    total_idx = inv.headers.index("total")
    assert inv.rows[0][total_idx] == "1000"  # parsed via Decimal, no decimals added


# ── S04 classify ─────────────────────────────────────────────────────────────────


def test_classify_assigns_types_and_confidence() -> None:
    ds = normalize(parse(ingest(_zip(_valid_files()), ZOHO_PROFILE), ZOHO_PROFILE), ZOHO_PROFILE)
    txns = classify(ds, ZOHO_PROFILE)
    assert {t.voucher_type for t in txns} == {"Sales", "Receipt", "Payment"}
    assert all(t.confidence == 1.0 for t in txns)


def test_classify_empty_id_fails() -> None:
    files = _valid_files()
    files["Vendor_Payments.csv"] = "id,amount\n,750\n"
    ds = normalize(parse(ingest(_zip(files), ZOHO_PROFILE), ZOHO_PROFILE), ZOHO_PROFILE)
    with pytest.raises(ClassifyError) as e:
        classify(ds, ZOHO_PROFILE)
    assert e.value.code == "empty_id"


# ── S05 map ledgers ──────────────────────────────────────────────────────────────


def _empty_dataset() -> SourceDataset:
    table = SourceTable(
        role=ArtifactRole.CUSTOMERS, headers=("contact_id", "contact_name"), rows=()
    )
    return SourceDataset(source_system="zoho", tables=(table,))


def test_map_unmapped_party_fails() -> None:
    txn = ClassifiedTxn(
        role=ArtifactRole.SALES_INVOICES,
        voucher_type="Sales",
        confidence=1.0,
        voucher_number="INV1",
        amount=Decimal("100"),
        party_id="GHOST",
        debit_account=PARTY_SENTINEL,
        credit_account="Sales Account",
    )
    with pytest.raises(MapError) as e:
        map_ledgers((txn,), _empty_dataset(), ZOHO_PROFILE)
    assert e.value.code == "unmapped_party"


def test_map_missing_party_fails() -> None:
    txn = ClassifiedTxn(
        role=ArtifactRole.SALES_INVOICES,
        voucher_type="Sales",
        confidence=1.0,
        voucher_number="INV1",
        amount=Decimal("100"),
        party_id=None,
        debit_account=PARTY_SENTINEL,
        credit_account="Sales Account",
    )
    with pytest.raises(MapError) as e:
        map_ledgers((txn,), _empty_dataset(), ZOHO_PROFILE)
    assert e.value.code == "missing_party"


# ── S06 canonicalize ─────────────────────────────────────────────────────────────


def test_canonicalize_reversal_swaps_sides() -> None:
    txn = MappedTxn(
        voucher_type="Receipt",
        confidence=1.0,
        voucher_number="R2",
        amount=Decimal("-300"),
        debit_ledger="Bank Account",
        credit_ledger="Accounts Receivable",
    )
    batch = canonicalize((txn,), company_name="C", source_system="zoho", posting_date=DATE)
    entries = batch.vouchers[0].entries
    assert entries[0].ledger_name == "Accounts Receivable" and entries[0].is_debit
    assert entries[1].ledger_name == "Bank Account" and not entries[1].is_debit
    assert entries[0].amount == Decimal("300")


# ── S07 validate ─────────────────────────────────────────────────────────────────


def _small_batch() -> object:
    z = _zip(_valid_files())
    ds = normalize(parse(ingest(z, ZOHO_PROFILE), ZOHO_PROFILE), ZOHO_PROFILE)
    mapped = map_ledgers(classify(ds, ZOHO_PROFILE), ds, ZOHO_PROFILE)
    return canonicalize(mapped, company_name="C", source_system="zoho", posting_date=DATE)


def test_validate_reports_date_and_confidence() -> None:
    batch = _small_batch()
    from tallyimporter.contracts.canonical import CanonicalBatch

    assert isinstance(batch, CanonicalBatch)
    clean = validate(batch, financial_year=(date(2026, 4, 1), date(2027, 3, 31)))
    assert not has_errors(clean)
    bad = validate(batch, financial_year=(date(2020, 1, 1), date(2020, 12, 31)))
    assert has_errors(bad)
    warn = validate(batch, confidence_floor=1.1)
    assert warn.issues and all(i.severity == "warning" for i in warn.issues)


# ── S09 number ───────────────────────────────────────────────────────────────────


def test_assign_numbers_passes_unique_batch() -> None:
    from tallyimporter.contracts.canonical import CanonicalBatch

    batch = _small_batch()
    assert isinstance(batch, CanonicalBatch)
    numbered = assign_numbers(batch)
    nums = [v.voucher_number for v in numbered.batch.vouchers]
    assert len(nums) == len(set(nums))
