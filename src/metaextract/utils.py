import math
import os

import numpy as np
import pandas as pd

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


def _safe(val):
    """Convert numpy/pandas types to JSON-safe Python types."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    if isinstance(val, np.integer):
        return int(val)
    if isinstance(val, np.floating):
        return round(float(val), 6)
    if isinstance(val, np.bool_):
        return bool(val)
    if isinstance(val, pd.Timestamp):
        return str(val)
    return val


def _format_value_labels(val_dict: dict) -> str:
    if not val_dict:
        return ""
    return "; ".join(f"{k}={v}" for k, v in val_dict.items())


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


def file_timestamps(path: str) -> tuple[str, str]:
    """Return (creation_time_str, modification_time_str) for a file path."""
    stat = os.stat(path)
    mtime = str(pd.Timestamp(stat.st_mtime, unit="s"))
    try:
        ctime = str(pd.Timestamp(stat.st_birthtime, unit="s"))
    except AttributeError:
        ctime = str(pd.Timestamp(stat.st_ctime, unit="s"))
    return ctime, mtime
