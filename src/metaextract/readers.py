import csv
import re
from collections import Counter

import numpy as np
import pandas as pd
import pyreadstat

from metaextract.utils import (
    _format_value_labels,
    detect_datetime_series,
    file_timestamps,
    infer_pandas_type,
)

IDENTIFIER_NAME_TOKENS = {
    "id",
    "ids",
    "identifier",
    "identifiers",
    "code",
    "codes",
}


def _assign_public_names(variables: list[dict]) -> list[dict]:
    """Assign unique lowercased public names while preserving raw column names."""
    name_counts = Counter()
    assigned_names = set()

    for variable in variables:
        base_name = str(variable["_raw_col_name"]).lower()
        name_counts[base_name] += 1
        candidate = base_name

        if name_counts[base_name] > 1:
            candidate = f"{base_name}__{name_counts[base_name]}"

        while candidate in assigned_names:
            name_counts[base_name] += 1
            candidate = f"{base_name}__{name_counts[base_name]}"

        variable["name"] = candidate
        assigned_names.add(candidate)

    return variables


def _trim_string_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Trim leading/trailing whitespace from string-like columns."""
    for col in df.columns:
        if pd.api.types.is_string_dtype(df[col].dtype) or pd.api.types.is_object_dtype(df[col].dtype):
            try:
                df[col] = df[col].str.strip()
            except AttributeError:
                pass
    return df


def _coerce_datetime_like_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Parse string/object columns that confidently look like datetimes.

    Note: mutates *df* in-place (columns are overwritten with parsed datetime series).
    """
    for col in df.columns:
        parsed = detect_datetime_series(df[col], str(col))
        if parsed is not None:
            df[col] = parsed
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


def _normalize_measure(measure: str | None) -> str | None:
    if measure in (None, "", "unknown"):
        return None
    return str(measure)


def _looks_like_identifier(var_name: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(var_name).lower()).strip("_")
    parts = [part for part in normalized.split("_") if part]
    return any(part in IDENTIFIER_NAME_TOKENS for part in parts)


def _stringify_observed_value(value) -> str | None:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, (float, np.floating)):
        return np.format_float_positional(float(value), trim="-")
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    return str(value)


def _infer_width(series: pd.Series) -> int | None:
    observed = []
    for value in series.tolist():
        text = _stringify_observed_value(value)
        if text is not None:
            observed.append(text)
    if not observed:
        return None
    return max(len(text) for text in observed)


def _infer_decimals(series: pd.Series, var_type: str) -> int | None:
    if var_type != "numeric":
        return None

    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return None

    max_decimals = 0
    for value in numeric:
        rendered = np.format_float_positional(float(value), trim="-")
        if "." in rendered:
            max_decimals = max(max_decimals, len(rendered.split(".")[-1]))
    return max_decimals


def _infer_measure(
    var_name: str,
    series: pd.Series,
    var_type: str,
    measure: str | None,
    *,
    infer_string_nominal: bool = False,
) -> str | None:
    normalized_measure = _normalize_measure(measure)
    if normalized_measure:
        return normalized_measure

    if var_type == "string":
        return "nominal" if infer_string_nominal else None
    if var_type == "boolean":
        return "nominal"
    if var_type == "datetime":
        return "scale"
    if var_type != "numeric":
        return None

    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if _looks_like_identifier(var_name):
        return "nominal"
    if numeric.empty:
        return "scale"

    unique_values = set(numeric.unique().tolist())
    if unique_values.issubset({0, 1}):
        return "nominal"
    return "scale"


def _resolve_width(
    series: pd.Series,
    meta,
    var_name: str,
) -> int | None:
    width, _ = _parse_spss_format(var_name, meta)
    if width is not None:
        return width

    display_width = getattr(meta, "variable_display_width", {}).get(var_name)
    if display_width and display_width > 0:
        return int(display_width)

    storage_width = getattr(meta, "variable_storage_width", {}).get(var_name)
    if storage_width and storage_width > 0:
        return int(storage_width)

    return _infer_width(series)


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
        raw_fmt = None
        if hasattr(meta, "original_variable_types") and meta.original_variable_types:
            raw_fmt = meta.original_variable_types.get(var)
        var_type = _infer_spss_type(var, meta)
        width = _resolve_width(df[var], meta, var)
        _, decimals = _parse_spss_format(var, meta)
        if decimals is None:
            decimals = _infer_decimals(df[var], var_type)
        value_labels = meta.variable_value_labels.get(var, {})
        variables.append({
            "name": str(var).lower(),
            "_raw_col_name": var,
            "label": (meta.column_labels[meta.column_names.index(var)]
                      if meta.column_labels else None),
            "type": var_type,
            "format": str(raw_fmt) if raw_fmt else None,
            "width": width,
            "decimals": decimals,
            "measure": _infer_measure(
                var,
                df[var],
                var_type,
                meta.variable_measure.get(var),
                infer_string_nominal=True,
            ),
            "missing_values": meta.missing_ranges.get(var),
            "values": _format_value_labels(value_labels),
            "_raw_value_labels": value_labels,
        })

    _assign_public_names(variables)
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
        var_type = infer_pandas_type(df[col].dtype)
        variables.append({
            "name": str(col).lower(),
            "_raw_col_name": col,
            "label": None,
            "type": var_type,
            "format": None,
            "width": _infer_width(df[col]),
            "decimals": _infer_decimals(df[col], var_type),
            "measure": _infer_measure(col, df[col], var_type, None),
            "missing_values": None,
            "values": None,
            "_raw_value_labels": {},
        })

    _assign_public_names(variables)
    return file_meta, variables


def read_csv(
    path: str,
    delimiter: str = ",",
    quotechar: str = '"',
    encoding: str = "utf-8",
    no_header: bool = False,
    nrows: int | None = None,
) -> tuple[pd.DataFrame, dict, list[dict]]:
    header = None if no_header else 0
    df = pd.read_csv(
        path,
        delimiter=delimiter,
        quotechar=quotechar,
        encoding=encoding,
        header=header,
        nrows=nrows,
    )
    df = _trim_string_columns(df)
    df = _coerce_datetime_like_columns(df)
    if no_header:
        df.columns = [f"col_{i}" for i in range(len(df.columns))]
    file_meta, variables = _generic_variables(df, path)
    return df, file_meta, variables


def read_qualtrics_csv(
    path: str,
    delimiter: str = ",",
    quotechar: str = '"',
    encoding: str = "utf-8",
    nrows: int | None = None,
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
        nrows=nrows,
    )
    df = _trim_string_columns(df)
    df = _coerce_datetime_like_columns(df)

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
    df = _coerce_datetime_like_columns(df)
    sheet_name = sheet if isinstance(sheet, str) else str(sheet)
    file_meta, variables = _generic_variables(df, path, extra_meta={"sheet_name": sheet_name})
    return df, file_meta, variables


def read_parquet(path: str) -> tuple[pd.DataFrame, dict, list[dict]]:
    df = pd.read_parquet(path)
    df = _trim_string_columns(df)
    df = _coerce_datetime_like_columns(df)
    file_meta, variables = _generic_variables(df, path)
    return df, file_meta, variables
