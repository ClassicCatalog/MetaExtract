import json
import sys
from pathlib import Path

import pandas as pd
import rich_click as click

from metaextract.utils import SUFFIX_TO_FORMAT, _safe
from metaextract.stats import compute_all_stats
from metaextract.output import build_json_output, build_csv_output


def _slice_to_rows(slice_df, col_name_map):
    rows = []
    for _, row in slice_df.iterrows():
        rows.append({
            col_name_map[col]: None if val is pd.NaT else _safe(val)
            for col, val in row.items()
        })
    return rows


@click.command()
@click.argument("input_file", type=click.Path(exists=True, dir_okay=False))
@click.option("-f", "--input-format",
              type=click.Choice(["csv", "qualtrics", "spss", "sas", "stata", "excel", "parquet"]),
              default=None, help="Force input format (default: inferred from suffix).")
@click.option("--output-format", type=click.Choice(["json", "csv"]), default="json",
              show_default=True, help="Output format.")
@click.option("-o", "--output", "output_path", default=None,
              type=click.Path(dir_okay=False), help="Output file path (default: stdout).")
@click.option("--delimiter", default=",", show_default=True,
              help="CSV/TSV field delimiter.")
@click.option("--quotechar", default='"', show_default=True,
              help="CSV quote character.")
@click.option("--encoding", default="utf-8", show_default=True,
              help="File encoding.")
@click.option("--no-header", is_flag=True, default=False,
              help="CSV has no header row; columns named col_0, col_1, …")
@click.option("--sheet", default="0", show_default=True,
              help="Excel sheet name or 0-based index.")
@click.option("--top-n", default=20, show_default=True,
              help="Number of top string values to include.")
@click.option("--no-stats", is_flag=True, default=False,
              help="Skip summary statistics computation.")
@click.option("--cardinality-threshold", default=10, show_default=True,
              help="Numeric variables with this many or fewer unique values are reported as discrete.")
@click.option("--head", "head", default=None, type=click.IntRange(min=0),
              help="Include the first N rows of data in JSON output.")
@click.option("--tail", "tail", default=None, type=click.IntRange(min=0),
              help="Include the last N rows of data in JSON output.")
@click.option("--data-only", is_flag=True, default=False,
              help="Output only the data rows (requires --head and/or --tail).")
def main(
    input_file,
    input_format,
    output_format,
    output_path,
    delimiter,
    quotechar,
    encoding,
    no_header,
    sheet,
    top_n,
    no_stats,
    cardinality_threshold,
    head,
    tail,
    data_only,
):
    """Extract metadata and statistics from data files.

    Supports CSV, SPSS (.sav), SAS (.sas7bdat), Stata (.dta), Excel, and Parquet.
    """
    path = Path(input_file)
    suffix = path.suffix.lower()

    # Resolve format
    if input_format is None:
        fmt = SUFFIX_TO_FORMAT.get(suffix)
        if fmt is None:
            raise click.UsageError(
                f"Cannot infer format from suffix '{suffix}'. "
                "Use -f/--input-format to specify: csv, qualtrics, spss, sas, stata, excel, parquet."
            )
    else:
        fmt = input_format

    # TSV auto-delimiter
    if suffix == ".tsv" and delimiter == ",":
        delimiter = "\t"

    # Dispatch to reader
    try:
        if fmt == "spss":
            from metaextract.readers import read_spss
            df, file_meta, variables = read_spss(str(path), encoding=encoding)
        elif fmt == "sas":
            from metaextract.readers import read_sas
            df, file_meta, variables = read_sas(str(path), encoding=encoding)
        elif fmt == "stata":
            from metaextract.readers import read_stata
            df, file_meta, variables = read_stata(str(path), encoding=encoding)
        elif fmt == "csv":
            from metaextract.readers import read_csv
            df, file_meta, variables = read_csv(
                str(path), delimiter=delimiter, quotechar=quotechar,
                encoding=encoding, no_header=no_header,
            )
        elif fmt == "qualtrics":
            from metaextract.readers import read_qualtrics_csv
            df, file_meta, variables = read_qualtrics_csv(
                str(path), delimiter=delimiter, quotechar=quotechar, encoding=encoding,
            )
        elif fmt == "excel":
            from metaextract.readers import read_excel
            df, file_meta, variables = read_excel(str(path), sheet=sheet, encoding=encoding)
        elif fmt == "parquet":
            from metaextract.readers import read_parquet
            df, file_meta, variables = read_parquet(str(path))
        else:
            raise click.UsageError(f"Unsupported format: {fmt}")
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    # Compute stats
    variables = compute_all_stats(
        df, variables, top_n=top_n, skip_stats=no_stats,
        cardinality_threshold=cardinality_threshold,
    )

    # Validate --data-only
    if data_only and head is None and tail is None:
        raise click.UsageError("--data-only requires --head and/or --tail.")

    # Build data preview rows
    if output_format == "csv" and (head is not None or tail is not None):
        click.echo("Warning: --head/--tail is not supported for CSV output and will be ignored.", err=True)

    col_name_map = {v["_raw_col_name"]: v["name"] for v in variables}
    head_rows = _slice_to_rows(df.head(head), col_name_map) if head is not None else None
    tail_rows = _slice_to_rows(df.tail(tail), col_name_map) if tail is not None else None

    # Build output
    if output_format == "json":
        if data_only:
            if head_rows is not None and tail_rows is not None:
                data = {"head": head_rows, "tail": tail_rows}
            elif head_rows is not None:
                data = head_rows
            else:
                data = tail_rows
        else:
            data = build_json_output(file_meta, variables, head_rows=head_rows, tail_rows=tail_rows)
        text = json.dumps(data, indent=2, default=str)
    else:
        text = build_csv_output(file_meta, variables)

    # Write output
    if output_path:
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
