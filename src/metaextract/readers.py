import csv
import re

import pandas as pd
import pyreadstat

from metaextract.utils import _format_value_labels, infer_pandas_type, file_timestamps


def _trim_string_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Trim leading/trailing whitespace from string-like columns."""
    for col in df.columns:
        if pd.api.types.is_string_dtype(df[col].dtype) or pd.api.types.is_object_dtype(df[col].dtype):
            non_null = df[col].dropna()
            if non_null.empty:
                continue
            if non_null.map(lambda val: isinstance(val, str)).all():
                df[col] = df[col].str.strip()
    return df


def _infer_spss_type(var_name: str, meta) -> str:
    fmt = None
    if hasattr(meta, "original_variable_types") and meta.original_variable_types:
        fmt = meta.original_variable_types.get(var_name)
    if fmt:
        fmt_str = str(fmt)
        if fmt_str.upper().startswith("A"):
            return "string"
        return "numeric"
    readstat_type = str(getattr(meta, "readstat_variable_types", {}).get(var_name, "")).lower()
    if readstat_type in {"string", "str"}:
        return "string"
    if readstat_type in {"double", "float", "int", "integer"}:
        return "numeric"
    return "numeric"


def _parse_spss_format(var_name: str, meta):
    fmt = None
    if hasattr(meta, "original_variable_types") and meta.original_variable_types:
        fmt = meta.original_variable_types.get(var_name)
    if not fmt:
        return None, None
    fmt_str = str(fmt)
    m = re.match(r"^[A-Za-z]+(\d+)(?:\.(\d+))?$", fmt_str)
    if not m:
        return None, None
    width = int(m.group(1)) if m.group(1) else None
    decimals = int(m.group(2)) if m.group(2) else None
    return width, decimals


def _spss_like_variables(df: pd.DataFrame, meta, path: str) -> tuple[dict, list[dict]]:
    """Shared logic for SPSS/SAS/Stata readers."""
    creation_time, modification_time = file_timestamps(path)
    file_meta = {
        "source_file": str(path),
        "file_label": getattr(meta, "file_label", "") or "",
        "file_encoding": getattr(meta, "file_encoding", "") or "",
        "number_rows": meta.number_rows,
        "number_columns": meta.number_columns,
        "creation_time": str(getattr(meta, "creation_time", "") or creation_time),
        "modification_time": str(getattr(meta, "modification_time", "") or modification_time),
        "notes": meta.notes if meta.notes else [],
    }

    variables = []
    for var in meta.column_names:
        width, decimals = _parse_spss_format(var, meta)
        raw_fmt = None
        if hasattr(meta, "original_variable_types") and meta.original_variable_types:
            raw_fmt = meta.original_variable_types.get(var)
        value_labels = meta.variable_value_labels.get(var, {})
        variables.append({
            "name": var.lower(),
            "_raw_col_name": var,
            "label": (meta.column_labels[meta.column_names.index(var)]
                      if meta.column_labels else None),
            "type": _infer_spss_type(var, meta),
            "format": str(raw_fmt) if raw_fmt else None,
            "width": width,
            "decimals": decimals,
            "measure": meta.variable_measure.get(var),
            "missing_values": meta.missing_ranges.get(var),
            "values": _format_value_labels(value_labels),
            "_raw_value_labels": value_labels,
        })

    return file_meta, variables


def read_spss(path: str, encoding: str = "utf-8") -> tuple[pd.DataFrame, dict, list[dict]]:
    df, meta = pyreadstat.read_sav(path, apply_value_formats=False, encoding=encoding)
    df = _trim_string_columns(df)
    file_meta, variables = _spss_like_variables(df, meta, path)
    return df, file_meta, variables


def read_sas(path: str, encoding: str = "utf-8") -> tuple[pd.DataFrame, dict, list[dict]]:
    df, meta = pyreadstat.read_sas7bdat(path, encoding=encoding)
    df = _trim_string_columns(df)
    file_meta, variables = _spss_like_variables(df, meta, path)
    return df, file_meta, variables


def read_stata(path: str, encoding: str = "utf-8") -> tuple[pd.DataFrame, dict, list[dict]]:
    df, meta = pyreadstat.read_dta(path, encoding=encoding)
    df = _trim_string_columns(df)
    file_meta, variables = _spss_like_variables(df, meta, path)
    return df, file_meta, variables


def _generic_variables(df: pd.DataFrame, path: str, extra_meta: dict | None = None) -> tuple[dict, list[dict]]:
    creation_time, modification_time = file_timestamps(path)
    file_meta = {
        "source_file": str(path),
        "file_label": "",
        "file_encoding": "",
        "number_rows": len(df),
        "number_columns": len(df.columns),
        "creation_time": creation_time,
        "modification_time": modification_time,
        "notes": [],
    }
    if extra_meta:
        file_meta.update(extra_meta)

    variables = []
    for col in df.columns:
        variables.append({
            "name": str(col).lower(),
            "_raw_col_name": col,
            "label": None,
            "type": infer_pandas_type(df[col].dtype),
            "format": None,
            "width": None,
            "decimals": None,
            "measure": None,
            "missing_values": None,
            "values": None,
            "_raw_value_labels": {},
        })

    return file_meta, variables


def read_csv(
    path: str,
    delimiter: str = ",",
    quotechar: str = '"',
    encoding: str = "utf-8",
    no_header: bool = False,
) -> tuple[pd.DataFrame, dict, list[dict]]:
    header = None if no_header else 0
    df = pd.read_csv(
        path,
        delimiter=delimiter,
        quotechar=quotechar,
        encoding=encoding,
        header=header,
    )
    df = _trim_string_columns(df)
    if no_header:
        df.columns = [f"col_{i}" for i in range(len(df.columns))]
    file_meta, variables = _generic_variables(df, path)
    return df, file_meta, variables


def read_qualtrics_csv(
    path: str,
    delimiter: str = ",",
    quotechar: str = '"',
    encoding: str = "utf-8",
) -> tuple[pd.DataFrame, dict, list[dict]]:
    with open(path, newline="", encoding=encoding) as fh:
        reader = csv.reader(fh, delimiter=delimiter, quotechar=quotechar)
        try:
            column_names = next(reader)
            column_labels = next(reader)
        except StopIteration as exc:
            raise ValueError("Qualtrics CSV must include header and label rows.") from exc

    if len(column_names) != len(column_labels):
        raise ValueError("Qualtrics CSV header and label rows must have the same number of columns.")

    df = pd.read_csv(
        path,
        delimiter=delimiter,
        quotechar=quotechar,
        encoding=encoding,
        header=0,
        skiprows=[1],
    )
    df = _trim_string_columns(df)

    file_meta, variables = _generic_variables(
        df,
        path,
        extra_meta={
            "csv_mode": "qualtrics",
            "metadata_rows_skipped": 1,
        },
    )

    label_map = dict(zip(column_names, column_labels))
    for variable in variables:
        variable["label"] = label_map.get(variable["_raw_col_name"]) or None

    return df, file_meta, variables


def read_excel(
    path: str,
    sheet=0,
    encoding: str = "utf-8",
) -> tuple[pd.DataFrame, dict, list[dict]]:
    # Resolve sheet: int if digit string, else name
    if isinstance(sheet, str) and sheet.isdigit():
        sheet = int(sheet)
    df = pd.read_excel(path, sheet_name=sheet)
    df = _trim_string_columns(df)
    sheet_name = sheet if isinstance(sheet, str) else str(sheet)
    file_meta, variables = _generic_variables(df, path, extra_meta={"sheet_name": sheet_name})
    return df, file_meta, variables


def read_parquet(path: str) -> tuple[pd.DataFrame, dict, list[dict]]:
    df = pd.read_parquet(path)
    df = _trim_string_columns(df)
    file_meta, variables = _generic_variables(df, path)
    return df, file_meta, variables
