# metaextract

CLI tool for extracting metadata and summary statistics from data files. Supports CSV, Qualtrics CSV, SPSS, SAS, Stata, Excel, and Parquet. Outputs a single unified JSON or flat CSV file.

## Installation

MetaExtract requires Python 3.12 or newer.

If you do not already have Python installed, download it from [python.org](https://www.python.org/downloads/) and install it before continuing.

Note: the examples below use Python 3.12. If your installed version is different, replace `3.12` in the commands with your installed version. For example, if you have Python 3.13, use `python3.13` or `py -3.13` instead.

### 1. Download the repository

You can download the project in either of these ways:

- Repository page: [ClassicCatalog/MetaExtract](https://github.com/ClassicCatalog/MetaExtract)
- Direct ZIP download: [main.zip](https://github.com/ClassicCatalog/MetaExtract/archive/refs/heads/main.zip)

If you download the ZIP file:

1. Download [main.zip](https://github.com/ClassicCatalog/MetaExtract/archive/refs/heads/main.zip).
2. Extract it.
3. Open the extracted `MetaExtract-main` folder.

### 2. Open a terminal in the project folder

You need to run the installation commands from inside the folder that contains `README.md` and `pyproject.toml`.

### 3. Create a virtual environment and install MetaExtract

#### macOS / Linux / WSL

Open Terminal and change into the project folder, then run:

```bash
python3.12 -m venv venv
source venv/bin/activate
python -m pip install -e ".[dev]"
```

#### Windows PowerShell

Open PowerShell in the project folder, then run:

```powershell
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

If PowerShell blocks the activation script, run this once in the same PowerShell window and then try again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

#### Windows Command Prompt

Open Command Prompt in the project folder, then run:

```bat
py -3.12 -m venv venv
venv\Scripts\activate.bat
python -m pip install -e ".[dev]"
```

### 4. Confirm that the installation worked

After installation, run:

```bash
metaextract --help
```

If that prints the help text, MetaExtract is installed and ready to use.

## Usage

```
metaextract [OPTIONS] INPUT_FILE
```

The format is inferred from the file suffix. Use `-f` to override.

| Option | Default | Description |
|---|---|---|
| `-f, --input-format` | (inferred) | Force format: `csv` `qualtrics` `spss` `sas` `stata` `excel` `parquet` |
| `--output-format [json\|csv]` | `json` | Output format |
| `-o, --output PATH` | stdout | Write output to file |
| `--delimiter TEXT` | `,` | CSV/TSV field delimiter |
| `--quotechar TEXT` | `"` | CSV quote character |
| `--encoding TEXT` | `utf-8` | File encoding |
| `--no-header` | off | CSV has no header row; columns named `col_0`, `col_1`, … |
| `--sheet TEXT` | `0` | Excel sheet name or 0-based index |
| `--top-n INTEGER` | `20` | Number of top string values to include in stats |
| `--no-stats` | off | Skip summary statistics |
| `--head INTEGER` | off | Include the first N rows of data in JSON output |
| `--tail INTEGER` | off | Include the last N rows of data in JSON output |
| `--data-only` | off | Output only the data rows; omits metadata (requires `--head`/`--tail`) |

TSV files (`.tsv`) automatically use `\t` as the delimiter.

### Examples

```bash
# JSON to stdout
metaextract codebook.sav

# JSON to file
metaextract codebook.sav -o out.json

# Flat CSV output
metaextract codebook.sav --output-format csv -o out.csv

# Skip statistics
metaextract codebook.sav --no-stats

# CSV with no header row
metaextract data.csv --no-header

# Force format, custom delimiter
metaextract data.txt -f csv --delimiter '|'

# Qualtrics CSV export
metaextract qualtrics_export.csv -f qualtrics

# Specific Excel sheet
metaextract report.xlsx --sheet "Summary"
```

When `-f qualtrics` is used, MetaExtract reads the first row as the Qualtrics field IDs, uses the second row as variable labels, and starts data rows from the third line of the file.

## Data Preview

`--head N` and `--tail N` append the first or last N rows of actual data to the JSON output under a `data_preview` key. Both flags can be used together.

```bash
# First 5 rows
metaextract data.csv --head 5

# Last 3 rows
metaextract data.csv --tail 3

# Both ends
metaextract data.csv --head 2 --tail 2

# Data rows only, no metadata
metaextract data.csv --head 5 --data-only
metaextract data.csv --tail 3 --data-only
metaextract data.csv --head 2 --tail 2 --data-only
```

The preview appears at the end of the JSON output:

```json
{
  "file_meta": {...},
  "dataset_summary": {...},
  "variables": [...],
  "data_preview": {
    "head": [
      {"id": 1, "name": "Alice", "score": 95.5},
      {"id": 2, "name": "Bob",   "score": 82.0}
    ],
    "tail": [
      {"id": 99, "name": "Zara", "score": 88.1}
    ]
  }
}
```

Row keys are always lowercased to match variable names in the `variables` list. If N exceeds the number of rows in the file, all rows are returned. `--head`/`--tail` are ignored when `--output-format csv` is used (a warning is printed to stderr).

Add `--data-only` to strip all metadata and return just the rows. With only `--head` or only `--tail`, the output is a flat JSON array. With both, it is `{"head": [...], "tail": [...]}`. `--data-only` requires at least one of `--head`/`--tail`.

## Output

All output is a single file (JSON default, or flat CSV with `--output-format csv`).

### JSON structure

```json
{
  "source_file": "codebook.sav",
  "file_label": "...",
  "file_encoding": "UTF-8",
  "number_rows": 2649,
  "number_columns": 305,
  "creation_time": "...",
  "modification_time": "...",
  "notes": [],
  "dataset_summary": {
    "stats_computed": true,
    "total_variables": 305,
    "continuous_variable_count": 120,
    "categorical_variable_count": 150,
    "string_variable_count": 35,
    "overall_percent_missing": 4.2
  },
  "variables": [
    {
      "name": "age",
      "label": "Age in years",
      "type": "numeric",
      "format": "F8.2",
      "width": 8,
      "decimals": 2,
      "measure": "scale",
      "missing_values": null,
      "values": {"1.0": "very slightly or not at all", "2.0": "a little", ...},
      "stats": {
        "stat_type": "continuous",
        "mean": 42.3,
        "median": 41.0,
        "std": 12.1,
        "min": 18.0,
        "max": 89.0,
        ...
      }
    }
  ]
}
```

### CSV structure

One row per variable. Scalar stat fields are prefixed `stat_`. Nested structures (e.g. `value_frequencies`) are omitted.

## Supported Formats

| Format | Extensions | Reader |
|---|---|---|
| CSV / TSV | `.csv`, `.tsv` | pandas |
| SPSS | `.sav` | pyreadstat |
| SAS | `.sas7bdat` | pyreadstat |
| Stata | `.dta` | pyreadstat |
| Excel | `.xlsx`, `.xls` | pandas + openpyxl/xlrd |
| Parquet | `.parquet` | pandas + pyarrow |

## Project Structure

```
src/metaextract/
  cli.py       — rich-click entry point
  readers.py   — one reader per format; each returns (df, file_meta, variables)
  stats.py     — _is_categorical, _compute_freq, _compute_variable_stats, compute_all_stats
  output.py    — build_json_output, build_csv_output
  utils.py     — SUFFIX_TO_FORMAT, _safe, infer_pandas_type, file_timestamps
tests/
  conftest.py  — shared fixtures
  data/        — CSV, TSV fixture files
  test_utils.py, test_stats.py, test_readers.py, test_output.py, test_cli.py
```

## Testing

```bash
pytest tests/ -v
```

Coverage runs automatically (configured in `pyproject.toml`). The text summary prints after every test run. To view it again without re-running tests:

```bash
coverage report
```

To view an HTML report:

```bash
pytest tests/ --cov-report=html && open htmlcov/index.html
```

Current coverage: **82% overall** (67 tests).

| Module | Coverage | Notes |
|---|---|---|
| `stats.py` | 99% | |
| `output.py` | 97% | |
| `utils.py` | 95% | `st_birthtime` fallback (non-macOS only) |
| `cli.py` | 76% | SPSS/SAS/Stata branches, file output path |
| `readers.py` | 47% | SPSS, SAS, Stata readers require binary fixture files |
