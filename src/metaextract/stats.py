import numpy as np
import pandas as pd

from metaextract.utils import (
    _safe,
    _labels_are_numeric,
    DISCRETE_CARDINALITY_RATIO,
    DISCRETE_NAME_PREFIXES,
)


def _is_categorical(var_type: str, measure: str, value_labels: dict) -> bool:
    """Determine whether a variable should be treated as categorical.

    Rules (in priority order):
    1. nominal/ordinal → always categorical.
    2. scale + no value labels → continuous.
    3. scale + value labels with all-numeric text → continuous.
    4. scale + value labels with any non-numeric text → categorical.
    5. measure unknown → presence of value labels decides.
    """
    if measure in ("nominal", "ordinal"):
        return True
    if measure == "scale":
        if not value_labels:
            return False
        return not _labels_are_numeric(value_labels)
    return bool(value_labels)


def _is_discrete(name: str, n_unique: int, total: int, threshold: int) -> bool:
    """Detect numeric variables that are better reported as discrete (frequency-based).

    Signals (any one triggers discrete):
    1. Name prefix convention — is_, has_, flag_, ind_ imply coded categories.
    2. Absolute low cardinality — unique values <= threshold (default 10).
    3. Relative low cardinality — unique/total < 1%, catches ordinal scales in large datasets.
    """
    if any(name.lower().startswith(p) for p in DISCRETE_NAME_PREFIXES):
        return True
    if n_unique <= threshold:
        return True
    if total > 0 and n_unique / total < DISCRETE_CARDINALITY_RATIO:
        return True
    return False


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


def _compute_variable_stats(
    var: str,
    series: pd.Series,
    var_type: str,
    value_labels: dict,
    measure: str,
    top_n: int = 20,
    cardinality_threshold: int = 10,
) -> dict:
    """Compute comprehensive summary statistics for a single variable."""
    total = len(series)
    non_null = int(series.count())
    n_missing = total - non_null
    pct_missing = round(n_missing / total * 100, 2) if total > 0 else 0.0
    n_unique = int(series.nunique())
    is_cat = _is_categorical(var_type, measure, value_labels)

    if var_type == "datetime":
        stat_type = "datetime"
    elif var_type == "string":
        stat_type = "string"
    elif is_cat:
        stat_type = "categorical"
    elif measure != "scale" and _is_discrete(var, n_unique, total, cardinality_threshold):
        stat_type = "discrete"
    else:
        stat_type = "continuous"

    stats = {
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

    if stat_type == "datetime":
        valid = pd.to_datetime(series, errors="coerce").dropna()
        if len(valid) > 0:
            stats["min"] = _safe(valid.min())
            stats["max"] = _safe(valid.max())
            stats["mean"] = _safe(valid.mean())
            stats["median"] = _safe(valid.median())
            centered_seconds = (valid - valid.mean()).dt.total_seconds()
            stats["std_seconds"] = _safe(centered_seconds.std())

            mode_vals = valid.mode()
            if len(mode_vals) > 0:
                stats["mode"] = _safe(mode_vals.iloc[0])
                stats["mode_count"] = int((valid == mode_vals.iloc[0]).sum())

    elif stat_type == "continuous":
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

            q1 = _safe(valid.quantile(0.25))
            q3 = _safe(valid.quantile(0.75))
            stats["q1"] = q1
            stats["q3"] = q3
            stats["iqr"] = _safe(q3 - q1) if q1 is not None and q3 is not None else None
            stats["p5"] = _safe(valid.quantile(0.05))
            stats["p10"] = _safe(valid.quantile(0.10))
            stats["p90"] = _safe(valid.quantile(0.90))
            stats["p95"] = _safe(valid.quantile(0.95))

            stats["skewness"] = _safe(valid.skew())
            stats["kurtosis"] = _safe(valid.kurtosis())
            stats["sem"] = _safe(valid.sem())

            if stats.get("mean") and stats["mean"] != 0:
                stats["cv"] = _safe(valid.std() / abs(valid.mean()))

            mode_vals = valid.mode()
            if len(mode_vals) > 0:
                stats["mode"] = _safe(mode_vals.iloc[0])
                stats["mode_count"] = int((valid == mode_vals.iloc[0]).sum())

            if value_labels:
                stats["value_frequencies"] = _compute_freq(col, value_labels, non_null)

    elif stat_type == "categorical":
        col = pd.to_numeric(series, errors="coerce")
        if value_labels:
            stats["value_frequencies"] = _compute_freq(col, value_labels, non_null)
        else:
            valid = col.dropna()
            value_counts = valid.value_counts().sort_index()
            stats["value_frequencies"] = {
                str(val): {
                    "count": int(cnt),
                    "percent": round(cnt / non_null * 100, 2),
                }
                for val, cnt in value_counts.items()
            }

    elif stat_type == "discrete":
        col = pd.to_numeric(series, errors="coerce")
        valid = col.dropna()
        value_counts = valid.value_counts().sort_index()
        stats["value_frequencies"] = {
            str(val): {
                "count": int(cnt),
                "percent": round(cnt / non_null * 100, 2),
            }
            for val, cnt in value_counts.items()
        }
        stats["min"] = _safe(valid.min())
        stats["max"] = _safe(valid.max())

    else:  # string
        valid = series.dropna()
        if len(valid) > 0:
            lengths = valid.str.len()
            stats["min_length"] = _safe(lengths.min())
            stats["max_length"] = _safe(lengths.max())
            stats["mean_length"] = _safe(lengths.mean())

            mode_vals = valid.mode()
            if len(mode_vals) > 0:
                stats["mode"] = _safe(mode_vals.iloc[0])
                stats["mode_count"] = int((valid == mode_vals.iloc[0]).sum())

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


def compute_all_stats(
    df: pd.DataFrame,
    variables: list[dict],
    top_n: int,
    skip_stats: bool,
    cardinality_threshold: int = 10,
) -> list[dict]:
    """Compute stats for all variables; attaches result to each variable dict."""
    for var in variables:
        raw_name = var["_raw_col_name"]
        series = df[raw_name]
        var_type = var.get("type") or "string"
        value_labels = var.get("_raw_value_labels") or {}
        measure = var.get("measure") or ""

        # Booleans: treat as nominal categorical
        if pd.api.types.is_bool_dtype(series.dtype):
            measure = "nominal"
            series = series.map({True: 1, False: 0, None: None})

        if skip_stats:
            var["stats"] = None
        else:
            var["stats"] = _compute_variable_stats(
                var["name"], series, var_type, value_labels, measure,
                top_n=top_n, cardinality_threshold=cardinality_threshold,
            )
    return variables
