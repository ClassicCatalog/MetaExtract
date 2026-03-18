import json
import math
import os
import pyreadstat
import numpy as np
import pandas as pd
import re

sav_path = "fake_data.sav"
csv_out = "test.csv"

df, meta = pyreadstat.read_sav(sav_path, apply_value_formats=False)

def infer_spss_type(var_name: str) -> str:
    # Prefer SPSS original format when available (e.g., A10 for string, F8.2 for numeric)
    fmt = None
    if hasattr(meta, "original_variable_types") and meta.original_variable_types:
        fmt = meta.original_variable_types.get(var_name)
    if fmt:
        fmt_str = str(fmt)
        if fmt_str.upper().startswith("A"):
            return "string"
        return "numeric"
    # Fallback to pandas dtype inference
    return "string" if pd.api.types.is_object_dtype(df[var_name].dtype) else "numeric"

def parse_spss_format(var_name: str):
    fmt = None
    if hasattr(meta, "original_variable_types") and meta.original_variable_types:
        fmt = meta.original_variable_types.get(var_name)
    if not fmt:
        return None, None
    fmt_str = str(fmt)
    # Example formats: A100, F8.2, N10, DATE10, etc.
    m = re.match(r"^[A-Za-z]+(\d+)(?:\.(\d+))?$", fmt_str)
    if not m:
        return None, None
    width = int(m.group(1)) if m.group(1) else None
    decimals = int(m.group(2)) if m.group(2) else None
    return width, decimals

def _format_value_labels(val_dict: dict) -> str:
    if not val_dict:
        return ""
    return "; ".join(f"{k}={v}" for k, v in val_dict.items())


def _safe(val):
    """Convert numpy/pandas types to JSON-safe Python types."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return round(float(val), 6)
    if isinstance(val, (np.bool_,)):
        return bool(val)
    if isinstance(val, (pd.Timestamp,)):
        return str(val)
    return val


def _labels_are_numeric(value_labels: dict) -> bool:
    """Return True if every label text is a bare number (e.g. '1', '10', '-3.5')."""
    for label_text in value_labels.values():
        try:
            float(str(label_text).strip())
        except ValueError:
            return False
    return True


def _is_categorical(var_type: str, measure: str, value_labels: dict) -> bool:
    """Determine whether a variable should be treated as categorical.

    Rules (in priority order):
    1. SPSS nominal/ordinal → always categorical.
    2. SPSS scale + no value labels → continuous.
    3. SPSS scale + value labels with all-numeric text (e.g. '1'..'10') → continuous
       (these are rating-scale endpoint annotations, not category labels).
    4. SPSS scale + value labels with any non-numeric text → categorical
       (e.g. 'Female', 'Married', '< or = 9').
    5. measure unknown → presence of value labels decides.
    """
    if measure in ("nominal", "ordinal"):
        return True
    if measure == "scale":
        if not value_labels:
            return False
        return not _labels_are_numeric(value_labels)
    # measure unknown
    return bool(value_labels)


def _compute_freq(col: pd.Series, value_labels: dict, non_null: int) -> dict:
    """Snap values to nearest label key and compute frequency distribution."""
    label_keys = np.array(sorted(value_labels.keys()), dtype=float)
    snapped = col.dropna().apply(
        lambda x: label_keys[np.argmin(np.abs(label_keys - x))]
    )
    freq = {}
    for val in label_keys:
        count = int((snapped == val).sum())
        freq[str(val)] = {
            "label": value_labels[val],
            "count": count,
            "percent": round(count / non_null * 100, 2) if non_null > 0 else 0.0,
        }
    return freq


def _compute_variable_stats(var: str, series: pd.Series, var_type: str,
                            value_labels: dict, measure: str) -> dict:
    """Compute comprehensive summary statistics for a single variable."""
    total = len(series)
    non_null = int(series.count())
    n_missing = total - non_null
    pct_missing = round(n_missing / total * 100, 2) if total > 0 else 0.0
    n_unique = int(series.nunique())
    is_cat = _is_categorical(var_type, measure, value_labels)

    # stat_type drives which statistics are computed
    if var_type == "string":
        stat_type = "string"
    elif is_cat:
        stat_type = "categorical"
    else:
        stat_type = "continuous"

    stats = {
        "variable": var.lower(),
        "stat_type": stat_type,
        "spss_measure": measure or "",
        "total_count": total,
        "valid_count": non_null,
        "missing_count": n_missing,
        "percent_missing": pct_missing,
        "unique_count": n_unique,
    }

    if non_null == 0:
        stats["has_data"] = False
        return stats

    stats["has_data"] = True

    if stat_type == "continuous":
        col = pd.to_numeric(series, errors="coerce")
        valid = col.dropna()
        if len(valid) > 0:
            stats["mean"] = _safe(valid.mean())
            stats["median"] = _safe(valid.median())
            stats["std"] = _safe(valid.std())
            stats["variance"] = _safe(valid.var())
            stats["min"] = _safe(valid.min())
            stats["max"] = _safe(valid.max())
            stats["range"] = _safe(valid.max() - valid.min())
            stats["sum"] = _safe(valid.sum())

            # Quartiles and IQR
            q1 = _safe(valid.quantile(0.25))
            q3 = _safe(valid.quantile(0.75))
            stats["q1"] = q1
            stats["q3"] = q3
            stats["iqr"] = _safe(q3 - q1) if q1 is not None and q3 is not None else None
            stats["p5"] = _safe(valid.quantile(0.05))
            stats["p10"] = _safe(valid.quantile(0.10))
            stats["p90"] = _safe(valid.quantile(0.90))
            stats["p95"] = _safe(valid.quantile(0.95))

            # Shape statistics
            stats["skewness"] = _safe(valid.skew())
            stats["kurtosis"] = _safe(valid.kurtosis())

            # Standard error of the mean
            stats["sem"] = _safe(valid.sem())

            # Coefficient of variation
            if stats["mean"] and stats["mean"] != 0:
                stats["cv"] = _safe(valid.std() / abs(valid.mean()))

            # Mode (may be multiple; report first)
            mode_vals = valid.mode()
            if len(mode_vals) > 0:
                stats["mode"] = _safe(mode_vals.iloc[0])
                stats["mode_count"] = int((valid == mode_vals.iloc[0]).sum())

            # Include frequency distribution if value labels are defined
            if value_labels:
                stats["value_frequencies"] = _compute_freq(col, value_labels, non_null)

    elif stat_type == "categorical":
        col = pd.to_numeric(series, errors="coerce")
        if value_labels:
            stats["value_frequencies"] = _compute_freq(col, value_labels, non_null)
        else:
            # Ordinal/nominal without defined labels — frequency of raw values
            valid = col.dropna()
            value_counts = valid.value_counts().sort_index()
            stats["value_frequencies"] = {
                str(val): {
                    "count": int(cnt),
                    "percent": round(cnt / non_null * 100, 2),
                }
                for val, cnt in value_counts.items()
            }

    else:
        # String variable
        valid = series.dropna()
        if len(valid) > 0:
            lengths = valid.str.len()
            stats["min_length"] = _safe(lengths.min())
            stats["max_length"] = _safe(lengths.max())
            stats["mean_length"] = _safe(lengths.mean())

            # Mode
            mode_vals = valid.mode()
            if len(mode_vals) > 0:
                stats["mode"] = _safe(mode_vals.iloc[0])
                stats["mode_count"] = int((valid == mode_vals.iloc[0]).sum())

            # Top values by frequency (up to 20)
            top_n = 20
            value_counts = valid.value_counts().head(top_n)
            stats["top_values"] = [
                {
                    "value": _safe(val),
                    "count": int(cnt),
                    "percent": round(cnt / non_null * 100, 2),
                }
                for val, cnt in value_counts.items()
            ]

    return stats

rows = []
for var in meta.column_names:
    width, decimals = parse_spss_format(var)
    rows.append({
        "name": var.lower(),
        "label": (meta.column_labels[meta.column_names.index(var)]
                  if meta.column_labels else None),
        "type": infer_spss_type(var),
        "format": meta.original_variable_types.get(var),
        "width": width,
        "decimals": decimals,
        "measure": meta.variable_measure.get(var),
        "missing_values": meta.missing_ranges.get(var),
        "values": _format_value_labels(meta.variable_value_labels.get(var, {})),
    })

out = pd.DataFrame(rows)

# Improve: add true storage type (string vs numeric)
# meta.variable_storage_width is available in newer versions; if missing, ignore gracefully
if hasattr(meta, "variable_storage_width"):
    out["storage_width"] = out["name"].map(meta.variable_storage_width)

out.to_csv(csv_out, index=False)
print(f"Wrote {len(out)} variables to {csv_out}")

# Compute per-variable summary statistics
print("Computing summary statistics...")
variable_stats = []
for var in meta.column_names:
    var_type = infer_spss_type(var)
    value_labels = meta.variable_value_labels.get(var, {})
    measure = meta.variable_measure.get(var, "")
    stats = _compute_variable_stats(var, df[var], var_type, value_labels, measure)
    variable_stats.append(stats)

# Compute dataset-level summary statistics
vars_with_data = sum(1 for s in variable_stats if s.get("has_data"))
total_cells = meta.number_rows * meta.number_columns
total_non_null = sum(s["valid_count"] for s in variable_stats)
total_missing = sum(s["missing_count"] for s in variable_stats)

dataset_stats = {
    "total_variables": meta.number_columns,
    "variables_with_data": vars_with_data,
    "variables_empty": meta.number_columns - vars_with_data,
    "total_cells": total_cells,
    "total_non_null_cells": total_non_null,
    "total_missing_cells": total_missing,
    "overall_percent_missing": round(total_missing / total_cells * 100, 2) if total_cells > 0 else 0.0,
    "continuous_variable_count": sum(1 for s in variable_stats if s.get("stat_type") == "continuous"),
    "categorical_variable_count": sum(1 for s in variable_stats if s.get("stat_type") == "categorical"),
    "string_variable_count": sum(1 for s in variable_stats if s.get("stat_type") == "string"),
}

# Write companion file-level metadata
meta_out = os.path.splitext(csv_out)[0] + "_metadata.json"
file_metadata = {
    "source_file": sav_path,
    "file_label": meta.file_label or "",
    "file_encoding": getattr(meta, "file_encoding", ""),
    "number_rows": meta.number_rows,
    "number_columns": meta.number_columns,
    "creation_time": str(getattr(meta, "creation_time", "")),
    "modification_time": str(getattr(meta, "modification_time", "")),
    "notes": meta.notes if meta.notes else [],
    "dataset_summary": dataset_stats,
    "variable_statistics": variable_stats,
}
with open(meta_out, "w") as f:
    json.dump(file_metadata, f, indent=2)
print(f"Wrote file metadata with summary statistics to {meta_out}")
