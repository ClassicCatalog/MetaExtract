# Plan: metaextract CLI Tool

## Context
Refactor the existing hardcoded `extract.py` (SPSS-only, two output files) into a proper installable Python package (`metaextract`) that:
- Supports CSV, SPSS, SAS, Stata, Excel, Parquet
- Outputs a **single** unified file (JSON default, or flat CSV)
- Uses `rich-click` for a polished CLI
- Is packaged with `pyproject.toml` + `hatchling`, Python 3.12+
- Has a robust pytest test suite in `tests/`

## Project Structure
```
dataAnalyzer-CLASSIC/
├── src/
│   └── metaextract/
│       ├── __init__.py       ← exports main()
│       ├── cli.py            ← rich-click entry point
│       ├── readers.py        ← one reader per format, returns (df, file_meta, variables)
│       ├── stats.py          ← statistics computation (_compute_variable_stats, etc.)
│       ├── output.py         ← build_json_output, build_csv_output
│       └── utils.py          ← _safe, _format_value_labels, _labels_are_numeric, infer_pandas_type
├── tests/
│   ├── __init__.py
│   ├── conftest.py           ← shared fixtures (sample DataFrames, metadata dicts)
│   ├── data/                 ← small test fixture files
│   │   ├── sample.csv
│   │   ├── sample_no_header.csv
│   │   └── sample.tsv
│   ├── test_utils.py         ← _safe, _format_value_labels, infer_pandas_type
│   ├── test_stats.py         ← _is_categorical, _compute_freq, _compute_variable_stats
│   ├── test_readers.py       ← read_csv, read_excel, read_parquet (file-based)
│   ├── test_output.py        ← build_json_output, build_csv_output
│   └── test_cli.py           ← CliRunner integration tests
├── pyproject.toml
├── CLAUDE.md
├── AGENTS.md                 ← symlink to CLAUDE.md
└── venv/                     ← python3.12 -m venv venv
```

## pyproject.toml (exact)
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "metaextract"
version = "0.1.0"
description = "CLI metadata extraction tool for SPSS, SAS, Stata, CSV, Excel, and Parquet files"
requires-python = ">=3.12"
dependencies = [
    "rich-click",
    "pandas>=2.0",
    "pyreadstat",
    "openpyxl",
    "xlrd",
    "pyarrow",
    "numpy",
]

[project.scripts]
metaextract = "metaextract.cli:main"

[project.optional-dependencies]
dev = [
    "pytest",
    "pytest-cov",
]

[tool.hatch.build.targets.wheel]
packages = ["src/metaextract"]
```

## CLI Interface (`metaextract [OPTIONS] INPUT_FILE`)

| Option | Default | Notes |
|---|---|---|
| `-f, --input-format` | (inferred from suffix) | Force format: csv/spss/sas/stata/excel/parquet |
| `--output-format [json\|csv]` | `json` | Output format |
| `-o, --output PATH` | stdout | Output file path |
| `--delimiter TEXT` | `,` | CSV/TSV delimiter |
| `--quotechar TEXT` | `"` | CSV quote character |
| `--encoding TEXT` | `utf-8` | File encoding |
| `--no-header` | False | Flag: CSV has no header row → columns named col_0, col_1, … |
| `--sheet TEXT` | `0` | Excel sheet name or 0-based index |
| `--top-n INTEGER` | `20` | Number of top string values to include |
| `--no-stats` | False | Skip summary statistics computation |

**Format inference** from suffix (`SUFFIX_TO_FORMAT` dict in `utils.py`):
`.csv/.tsv` → csv, `.sav` → spss, `.sas7bdat` → sas, `.dta` → stata, `.xlsx/.xls` → excel, `.parquet` → parquet

TSV auto-delimiter: if suffix is `.tsv` and `--delimiter` not explicitly set, delimiter becomes `\t`.

## Source File Responsibilities

### `utils.py`
- `SUFFIX_TO_FORMAT` dict
- `_safe(val)` — numpy/pandas → JSON-safe Python
- `_format_value_labels(val_dict)` — "k=v; …" string
- `_labels_are_numeric(value_labels)` — bool
- `infer_pandas_type(dtype) -> str` — "boolean" | "datetime" | "numeric" | "string" (bool checked before numeric)
- `file_timestamps(path)` — returns (creation_time_str, modification_time_str); uses `st_birthtime` on macOS, `st_ctime` fallback on Linux

### `stats.py`
- `_is_categorical(var_type, measure, value_labels)` — priority: nominal/ordinal → True; scale+no labels → False; scale+numeric-only labels → False; scale+non-numeric labels → True; unknown → bool(value_labels)
- `_compute_freq(col, value_labels, non_null)` — snap to nearest label key, return freq dict
- `_compute_variable_stats(var, series, var_type, value_labels, measure, top_n=20)` — full stats; returns dict with `stat_type`, counts, and type-specific stats
- `compute_all_stats(df, variables, top_n, skip_stats)` — iterates variables, uses `_raw_col_name` for df access; booleans: force `measure="nominal"` + cast to int

### `readers.py`
Each reader returns `(df: pd.DataFrame, file_meta: dict, variables: list[dict])`.

Variable dicts contain: `name` (lowercased), `label`, `type`, `format`, `width`, `decimals`, `measure`, `missing_values`, `values` (formatted string), plus internal keys `_raw_col_name`, `_raw_value_labels` (stripped before output).

- `read_spss(path, encoding)` — pyreadstat.read_sav, apply_value_formats=False; infer_spss_type/parse_spss_format (take `meta` as param, not global)
- `read_sas(path, encoding)` — pyreadstat.read_sas7bdat; same interface as SPSS
- `read_stata(path, encoding)` — pyreadstat.read_dta; same interface as SPSS
- `read_csv(path, delimiter, quotechar, encoding, no_header)` — `no_header=True` → `header=None` → rename to col_0, col_1…
- `read_excel(path, sheet, encoding)` — `int(sheet)` if digit string else name string; include `sheet_name` in file_meta
- `read_parquet(path)` — pandas.read_parquet

CSV/Excel/Parquet: `label`, `format`, `width`, `decimals`, `measure`, `missing_values` all `None`; `values=""`; type from `infer_pandas_type`.

### `output.py`
- `_build_dataset_summary(file_meta, variables, stats_computed)` — mirrors existing logic; adds `"stats_computed"` bool
- `build_json_output(file_meta, variables)` — strips `_` keys; merges `stats` into each variable dict; returns full dict
- `build_csv_output(file_meta, variables)` — one row per variable; scalar fields only; stat fields prefixed `stat_`; nested structures omitted

### `cli.py`
- `main()` — rich-click entry point; resolves format; dispatches to reader; calls `compute_all_stats`; calls output builder; writes to file or stdout with `json.dumps(..., default=str)`

### `__init__.py`
```python
from metaextract.cli import main
__all__ = ["main"]
```

## JSON Output Structure (unified, single file)
```json
{
  "source_file": "...",
  "file_label": "...",
  "file_encoding": "...",
  "number_rows": 123,
  "number_columns": 10,
  "creation_time": "...",
  "modification_time": "...",
  "notes": [],
  "dataset_summary": {
    "stats_computed": true,
    "total_variables": 10,
    "continuous_variable_count": 4,
    "categorical_variable_count": 3,
    "string_variable_count": 3,
    "overall_percent_missing": 1.2,
    ...
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
      "values": "",
      "stats": { "stat_type": "continuous", "mean": 42.3, "median": 41.0, ... }
    }
  ]
}
```

## Test Suite (`tests/`)

### `conftest.py` — shared fixtures
- `sample_df()` — DataFrame with int, float, string, bool, datetime columns
- `sample_variables()` — matching variables list as readers would produce
- `sample_file_meta()` — file_meta dict
- `sample_csv_path(tmp_path)` — writes `tests/data/sample.csv` to a temp path

### `test_utils.py`
- `_safe`: numpy int/float/bool, pandas Timestamp, None, NaN → correct Python types
- `_format_value_labels`: empty dict, populated dict → correct string
- `infer_pandas_type`: each dtype family → correct string; bool before numeric ordering

### `test_stats.py`
- `_is_categorical`: all 5 rule branches with matrix of (measure, value_labels) inputs
- `_compute_freq`: known col + labels → expected counts/percents
- `_compute_variable_stats`: continuous path (check mean/std/quartiles), categorical path (check value_frequencies), string path (check top_values/lengths), all-missing column (has_data=False), top_n override

### `test_readers.py`
- `read_csv`: normal CSV, TSV (auto-delimiter), --no-header (col_0 naming), custom delimiter, custom quotechar
- `read_excel`: first sheet default, named sheet, integer index sheet (use openpyxl to create fixture in conftest)
- `read_parquet`: roundtrip — write known df, read back, verify variables

### `test_output.py`
- `build_json_output`: internal `_` keys stripped, stats merged into variables, dataset_summary present
- `build_csv_output`: nested structures absent, stat_ prefix on stat fields, one row per variable
- `_build_dataset_summary`: stats_computed=True/False, counts of each stat_type

### `test_cli.py` (using `click.testing.CliRunner`)
- Default JSON output to stdout for sample CSV
- `--output-format csv` produces CSV text
- `-o FILE` writes to file
- `--no-stats` produces `"stats": null`
- `--no-header` produces `col_0`, `col_1` names
- Invalid file path → non-zero exit code
- Unknown suffix without `-f` → non-zero exit code with helpful message
- `--help` exits 0

## Key Edge Cases
- **Column name case**: `name` output is lowercased; `_raw_col_name` tracks original case for df access
- **Boolean stats**: force `measure="nominal"` + cast series to int
- **`--no-stats`**: `stats` key is `null`; `dataset_summary.stats_computed = false`
- **pyreadstat missing_ranges**: `json.dumps(..., default=str)` as catch-all
- **`st_birthtime`**: macOS-only; fall back to `st_ctime`

## Verification
```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Unit tests
pytest tests/ -v

# Smoke test against existing SPSS file
metaextract codebook.sav                          # JSON to stdout
metaextract codebook.sav -o out.json              # JSON to file
metaextract codebook.sav --output-format csv -o out.csv
metaextract codebook.sav --no-stats
metaextract --help
```
