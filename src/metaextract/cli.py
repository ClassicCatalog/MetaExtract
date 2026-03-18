import json
import sys
from pathlib import Path

import rich_click as click

from metaextract.utils import SUFFIX_TO_FORMAT
from metaextract.stats import compute_all_stats
from metaextract.output import build_json_output, build_csv_output


@click.command()
@click.argument("input_file", type=click.Path(exists=True, dir_okay=False))
@click.option("-f", "--input-format",
              type=click.Choice(["csv", "spss", "sas", "stata", "excel", "parquet"]),
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
                "Use -f/--input-format to specify: csv, spss, sas, stata, excel, parquet."
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
    variables = compute_all_stats(df, variables, top_n=top_n, skip_stats=no_stats)

    # Build output
    if output_format == "json":
        data = build_json_output(file_meta, variables)
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
