"""Command-line entry point: a source export ZIP -> TallyPrime import XML files.

The imperative shell for the pipeline: reads the archive, writes masters.xml and
vouchers.xml. Import masters first, then vouchers (see smoke_import/SMOKE_IMPORT.md).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from tallyimporter.contracts.errors import TallyImporterError
from tallyimporter.pipeline import run_pipeline_full


def _parse_date(value: str) -> date:
    if len(value) != 8 or not value.isdigit():
        raise argparse.ArgumentTypeError(f"date must be YYYYMMDD, got {value!r}")
    return date(int(value[:4]), int(value[4:6]), int(value[6:8]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tallyimporter",
        description="Convert a Zoho Books export ZIP into TallyPrime import XML "
        "(masters + vouchers).",
    )
    parser.add_argument("archive", type=Path, help="path to the Zoho export .zip")
    parser.add_argument(
        "--company", required=True, help="target Tally company name (SVCURRENTCOMPANY)"
    )
    parser.add_argument(
        "--date",
        required=True,
        type=_parse_date,
        help="posting date YYYYMMDD (the sample export carries no per-document dates)",
    )
    parser.add_argument("--out", type=Path, default=Path("."), help="output directory (default: .)")
    parser.add_argument(
        "--enrich",
        action="store_true",
        help="add bill-wise allocations to party entries (S08)",
    )
    args = parser.parse_args(argv)

    archive_path: Path = args.archive
    company: str = args.company
    posting_date: date = args.date
    out_dir: Path = args.out
    enrich: bool = args.enrich

    try:
        archive = archive_path.read_bytes()
    except OSError as exc:
        print(f"error: cannot read {archive_path}: {exc}", file=sys.stderr)
        return 2

    try:
        export = run_pipeline_full(
            archive, company_name=company, posting_date=posting_date, enrich=enrich
        )
    except TallyImporterError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    masters = out_dir / "masters.xml"
    vouchers = out_dir / "vouchers.xml"
    masters.write_bytes(export.masters_xml)
    vouchers.write_bytes(export.vouchers_xml)

    print(f"wrote {masters} ({len(export.masters_xml):,} bytes)")
    print(f"wrote {vouchers} ({len(export.vouchers_xml):,} bytes)")
    print("import masters.xml first, then vouchers.xml (see smoke_import/SMOKE_IMPORT.md).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
