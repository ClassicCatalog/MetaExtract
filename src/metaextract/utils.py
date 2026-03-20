import math
import os
import re

import numpy as np
import pandas as pd

LOW_CARDINALITY_THRESHOLD = 10  # numeric vars with <= this many unique values → discrete
DISCRETE_CARDINALITY_RATIO = 0.01  # unique/total < 1% also signals discrete
DISCRETE_NAME_PREFIXES = ("is_", "has_", "flag_", "ind_")  # naming conventions → discrete

SUFFIX_TO_FORMAT = {
    ".csv": "csv",
    ".tsv": "csv",
    ".sav": "spss",
    ".sas7bdat": "sas",
    ".dta": "stata",
    ".xlsx": "excel",
    ".xls": "excel",
    ".parquet": "parquet",
}

DATETIME_NAME_TOKENS = (
    "date",
    "datetime",
    "time",
    "timestamp",
    "dt",
    "dob",
    "created",
    "updated",
    "modified",
)

DATETIME_MIN_NON_NULL = 2
DATETIME_HIGH_PARSE_RATE = 0.80
DATETIME_NAME_ASSISTED_PARSE_RATE = 0.50
NUMERIC_STRING_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?$")


def _safe(val):
    """Convert numpy/pandas types to JSON-safe Python types."""
    if val is None or val is pd.NaT:
        return None
    if isinstance(val, (float, np.floating)) and math.isnan(val):
        return None
    if isinstance(val, np.integer):
        return int(val)
    if isinstance(val, np.floating):
        return round(float(val), 6)
    if isinstance(val, np.bool_):
        return bool(val)
    if isinstance(val, (pd.Timestamp, np.datetime64)):
        return to_iso8601(val)
    return val


def _format_value_labels(val_dict: dict) -> dict | None:
    if not val_dict:
        return None
    return {str(k): v for k, v in val_dict.items()}


def _labels_are_numeric(value_labels: dict) -> bool:
    """Return True if every label text is a bare number (e.g. '1', '10', '-3.5')."""
    for label_text in value_labels.values():
        try:
            float(str(label_text).strip())
        except ValueError:
            return False
    return True


def infer_pandas_type(dtype) -> str:
    """Map a pandas dtype to a simplified type string."""
    if pd.api.types.is_bool_dtype(dtype):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "datetime"
    if pd.api.types.is_numeric_dtype(dtype):
        return "numeric"
    return "string"


def to_iso8601(val):
    """Convert datetime-like values to ISO-8601 strings."""
    if val is None or val is pd.NaT:
        return None
    ts = pd.Timestamp(val)
    if pd.isna(ts):
        return None
    return ts.isoformat()


def looks_like_datetime_name(name: str) -> bool:
    """Return True when a column name strongly suggests temporal data."""
    normalized = re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")
    if not normalized:
        return False
    parts = [part for part in normalized.split("_") if part]
    if any(part in DATETIME_NAME_TOKENS for part in parts):
        return True
    return any(token in normalized for token in DATETIME_NAME_TOKENS if len(token) > 2)


def detect_datetime_series(series: pd.Series, col_name: str) -> pd.Series | None:
    """Heuristically detect date/time columns and return parsed values when found."""
    if not (
        pd.api.types.is_string_dtype(series.dtype)
        or pd.api.types.is_object_dtype(series.dtype)
    ):
        return None

    non_null = series.dropna()
    if len(non_null) < DATETIME_MIN_NON_NULL:
        return None
    if not non_null.map(lambda val: isinstance(val, str)).all():
        return None

    has_datetime_name = looks_like_datetime_name(col_name)
    if not has_datetime_name and non_null.map(lambda val: bool(NUMERIC_STRING_RE.fullmatch(val))).all():
        return None

    try:
        parsed = pd.to_datetime(non_null, errors="coerce", format="mixed")
    except TypeError:
        parsed = pd.to_datetime(non_null, errors="coerce")
    parse_rate = float(parsed.notna().mean())
    if parse_rate >= DATETIME_HIGH_PARSE_RATE:
        try:
            result = pd.to_datetime(series, errors="coerce", format="mixed")
        except TypeError:
            result = pd.to_datetime(series, errors="coerce")
        return result

    if has_datetime_name and parse_rate >= DATETIME_NAME_ASSISTED_PARSE_RATE:
        try:
            result = pd.to_datetime(series, errors="coerce", format="mixed")
        except TypeError:
            result = pd.to_datetime(series, errors="coerce")
        return result

    return None


def file_timestamps(path: str) -> tuple[str, str]:
    """Return (creation_time_str, modification_time_str) for a file path."""
    stat = os.stat(path)
    mtime = to_iso8601(pd.Timestamp(stat.st_mtime, unit="s"))
    try:
        ctime = to_iso8601(pd.Timestamp(stat.st_birthtime, unit="s"))
    except AttributeError:
        ctime = to_iso8601(pd.Timestamp(stat.st_ctime, unit="s"))
    return ctime, mtime
