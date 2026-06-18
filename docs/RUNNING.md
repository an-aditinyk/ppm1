# Running TallyImporter

TallyImporter converts a **Zoho Books export ZIP** into **TallyPrime import XML** —
a `masters.xml` (ledgers) and a `vouchers.xml`. Setup is shown for **conda** and for
plain **venv + pip** — use whichever your team prefers; everything after §2 is identical.

## Prerequisites

- **Python 3.12** — via conda, or from [python.org](https://www.python.org/downloads/)
  (Windows: tick *"Add Python to PATH"* in the installer).
- **git**, with access to the repository.
- **TallyPrime** on the machine that will import the XML (not needed just to generate it).

## 1. Get the code

```bash
git clone https://github.com/an-aditinyk/ppm1.git
cd ppm1
git checkout claude/modest-archimedes-t2lpto
```

## 2. Create the environment (Python 3.12) — pick ONE

The project requires **Python 3.12**. Run these from the repo root.

### Option A — conda

```bash
conda create -n tallyimporter python=3.12 -y
conda activate tallyimporter
```

### Option B — venv + pip (no conda)

```bash
# Windows (Command Prompt) — use the Python launcher to pick 3.12:
py -3.12 -m venv .venv
.venv\Scripts\activate

# Windows (PowerShell):
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1

# macOS / Linux:
python3.12 -m venv .venv
source .venv/bin/activate
```

After activation, `python --version` must print `3.12.x`.

## 3. Install the package

With the environment **active**, from the repo root:

```bash
pip install -e .          # runtime only
# or, to also run the tests / quality gate:
pip install -e ".[dev]"
```

This registers the `tallyimporter` command inside the environment.

> Notes
> - **Activate the environment in every new shell** before running
>   (`conda activate tallyimporter`, or re-run the venv `activate` script).
> - `lxml` and `pydantic` install as normal wheels. If your network blocks PyPI and
>   you're on conda, install them first with
>   `conda install -c conda-forge lxml "pydantic>=2.7"`, then `pip install -e . --no-deps`.

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
| `tallyimporter: command not found` | Activate the env first (`conda activate tallyimporter` or the venv `activate` script), then re-run `pip install -e .`. Or use `python -m tallyimporter ...`. |
| `ERROR ... requires Python >=3.12` | The env isn't 3.12: check `python --version`; recreate it with Python 3.12 (§2). |
| `error: missing required artifact(s): [...]` | The ZIP lacks a required file (see §4). |
| `error: input is not a valid ZIP archive` | Point at the actual `.zip`, not an extracted folder. |
| `Date is out of range` in Tally | The company's financial year doesn't include `--date`; set the FY or change `--date`. |
| `lxml` build/install fails | Upgrade pip (`python -m pip install -U pip`) so it fetches a prebuilt wheel; on conda, `conda install -c conda-forge lxml` then `pip install -e . --no-deps`. |

> First time you import output containing `PARTYLEDGERNAME` or bill allocations
> (`--enrich`), confirm a small batch in a **test company** first — TallyPrime
> acceptance is the real gate.
