# metaextract

CLI metadata extraction tool for data files (CSV, SPSS, SAS, Stata, Excel, Parquet).

Python Version: 3.12 +
Virtual Environment: venv

## Setup

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

## Usage

```bash
metaextract <input_file> [OPTIONS]
```

Key options:
- `-f, --input-format` — force format (csv/spss/sas/stata/excel/parquet)
- `--output-format [json|csv]` — output format (default: json)
- `-o, --output PATH` — write to file (default: stdout)
- `--delimiter TEXT` — CSV delimiter (default: `,`; TSV auto-detects `\t`)
- `--no-header` — CSV without header row (columns named col_0, col_1, …)
- `--sheet TEXT` — Excel sheet name or 0-based index
- `--top-n INTEGER` — top string values to include (default: 20)
- `--no-stats` — skip statistics

## Testing

```bash
pytest tests/ -v
pytest tests/ -v --cov=src/metaextract
```

## Project Structure

```
src/metaextract/
  cli.py       — rich-click entry point
  readers.py   — one reader per format
  stats.py     — statistics computation
  output.py    — JSON and CSV output builders
  utils.py     — shared helpers and constants
tests/
  conftest.py  — shared fixtures
  data/        — small test fixture files
  test_*.py    — unit and integration tests
```

## Architecture Notes

- Each reader returns `(df, file_meta, variables)` where `variables` is a list of dicts
- Variable dicts include `_raw_col_name` and `_raw_value_labels` for internal use; these are stripped from output
- `name` field is always lowercased; `_raw_col_name` preserves original case for DataFrame access
- Booleans are treated as nominal categorical (cast to int) for statistics
- `json.dumps(..., default=str)` catches any remaining non-serializable types (e.g., pyreadstat missing_ranges)
