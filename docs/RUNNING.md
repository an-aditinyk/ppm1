# Running TallyImporter (conda)

TallyImporter converts a **Zoho Books export ZIP** into **TallyPrime import XML** —
a `masters.xml` (ledgers) and a `vouchers.xml`. This guide uses **conda**.

## Prerequisites

- **conda** (Miniconda or Anaconda).
- **git**, with access to the repository.
- **TallyPrime** on the machine that will import the XML (not needed just to generate it).

## 1. Get the code

```bash
git clone https://github.com/an-aditinyk/ppm1.git
cd ppm1
git checkout claude/modest-archimedes-t2lpto
```

## 2. Create the conda environment (Python 3.12)

The project requires **Python 3.12**.

```bash
conda create -n tallyimporter python=3.12 -y
conda activate tallyimporter
```

## 3. Install the package

From the repo root, with the env active:

```bash
pip install -e .          # runtime only
# or, to also run the tests / quality gate:
pip install -e ".[dev]"
```

`pip install -e .` registers the `tallyimporter` command inside the env.

> Notes
> - `pip` (inside the conda env) is the supported installer; `lxml` and `pydantic`
>   install as normal wheels. If your network blocks PyPI, install them from
>   conda-forge first: `conda install -c conda-forge lxml "pydantic>=2.7"`, then
>   `pip install -e . --no-deps`.
> - Always `conda activate tallyimporter` before running, in every new shell.

## 4. Run it

> **Put the whole command on one line.** Line-continuation characters differ by shell:
> none needed if it's one line. (`^` continues a line in cmd, `` ` `` in PowerShell,
> `\` in bash — do **not** mix them up. A stray `\` in cmd becomes a bad argument.)

**Windows — Command Prompt (cmd.exe):**

```bat
tallyimporter D:\tally-datasets\zoho_books.zip --company "PPM Global.Ltd" --date 20260401 --out .\out
```

**Windows — PowerShell:**

```powershell
tallyimporter D:\tally-datasets\zoho_books.zip --company "PPM Global.Ltd" --date 20260401 --out .\out
```

**macOS / Linux (bash/zsh):**

```bash
tallyimporter /path/to/Zoho_books_data.zip --company "Your Tally Company" --date 20260401 --out ./out
```

If `tallyimporter` isn't found, use `python -m tallyimporter ...` with the same arguments.

Writes two files into the `--out` directory:
- `masters.xml` — the ledgers; **import first**
- `vouchers.xml` — the vouchers; **import second**

| Option | Meaning |
|--------|---------|
| `archive` (positional) | path to the Zoho export `.zip` |
| `--company` | target Tally company name (written as `SVCURRENTCOMPANY`) **required** |
| `--date YYYYMMDD` | posting date for all vouchers — **required** (the sample export carries no per-document dates) |
| `--out DIR` | output directory (default: current directory) |
| `--enrich` | also add bill-wise allocations to party (customer) entries |

Exit codes: `0` success · `1` a pipeline/validation error (message on stderr) · `2` the input file could not be read.

### Required files in the export

The export ZIP must contain at least: `Contacts.csv`, `Sales_Invoices.csv`,
`Customer_Payments.csv`, `Vendor_Payments.csv`. Other Zoho files are optional (consumed
if present, recorded if unrecognized); `Projects.csv` / `Time_Entries.csv` are ignored.

## 5. Import into TallyPrime

1. Open/activate the **target company** in TallyPrime (its financial year must include
   your `--date`, e.g. FY 2026–27 for `20260401`).
2. **Gateway of Tally → Import → Masters** → select `out/masters.xml`.
3. **Gateway of Tally → Import → Vouchers** → select `out/vouchers.xml`.
4. Check the `Tally.imp` log for `Errors 0`.

The complete runbook — prerequisites, what a clean log looks like, and failure
signatures — is in **`smoke_import/SMOKE_IMPORT.md`**.

## 6. Use as a library (optional)

```python
from datetime import date
from tallyimporter.pipeline import run_pipeline_full

with open("Zoho_books_data.zip", "rb") as f:
    export = run_pipeline_full(f.read(), company_name="Your Co", posting_date=date(2026, 4, 1))

open("masters.xml", "wb").write(export.masters_xml)
open("vouchers.xml", "wb").write(export.vouchers_xml)
```

`run_pipeline_full(...)` also accepts `enrich=True` and `prior=<PriorImportState>` (skip
already-imported vouchers). For vouchers only, use `run_pipeline(...) -> bytes`.

## 7. Run the tests / quality gate (optional)

With the `[dev]` extras installed:

```bash
make check      # ruff + mypy (strict) + import-linter + pytest (~96% coverage)
# or simply:
pytest
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `tallyimporter: command not found` | `conda activate tallyimporter`, then re-run `pip install -e .`. |
| `ERROR ... requires Python >=3.12` | The env isn't 3.12: `python --version`; recreate with `python=3.12`. |
| `error: missing required artifact(s): [...]` | The ZIP lacks a required file (see §4). |
| `error: input is not a valid ZIP archive` | Point at the actual `.zip`, not an extracted folder. |
| `Date is out of range` in Tally | The company's financial year doesn't include `--date`; set the FY or change `--date`. |
| `lxml` build/install fails | `conda install -c conda-forge lxml`, then `pip install -e . --no-deps`. |

> First time you import output containing `PARTYLEDGERNAME` or bill allocations
> (`--enrich`), confirm a small batch in a **test company** first — TallyPrime
> acceptance is the real gate.
