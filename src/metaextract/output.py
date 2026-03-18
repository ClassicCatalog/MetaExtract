import csv
import io
import json

from metaextract.utils import _safe


def _build_dataset_summary(
    file_meta: dict,
    variables: list[dict],
    stats_computed: bool,
) -> dict:
    variable_stats = [v.get("stats") or {} for v in variables]
    vars_with_data = sum(1 for s in variable_stats if s.get("has_data"))
    total_cells = file_meta["number_rows"] * file_meta["number_columns"]
    total_non_null = sum(s.get("valid_count", 0) for s in variable_stats)
    total_missing = sum(s.get("missing_count", 0) for s in variable_stats)

    return {
        "stats_computed": stats_computed,
        "total_variables": file_meta["number_columns"],
        "variables_with_data": vars_with_data,
        "variables_empty": file_meta["number_columns"] - vars_with_data,
        "total_cells": total_cells,
        "total_non_null_cells": total_non_null,
        "total_missing_cells": total_missing,
        "overall_percent_missing": (
            round(total_missing / total_cells * 100, 2) if total_cells > 0 else 0.0
        ),
        "continuous_variable_count": sum(
            1 for s in variable_stats if s.get("stat_type") == "continuous"
        ),
        "categorical_variable_count": sum(
            1 for s in variable_stats if s.get("stat_type") == "categorical"
        ),
        "string_variable_count": sum(
            1 for s in variable_stats if s.get("stat_type") == "string"
        ),
    }


def build_json_output(
    file_meta: dict,
    variables: list[dict],
    head_rows: list[dict] | None = None,
    tail_rows: list[dict] | None = None,
) -> dict:
    """Build the unified JSON output dict."""
    stats_computed = any(v.get("stats") is not None for v in variables)

    dataset_summary = _build_dataset_summary(file_meta, variables, stats_computed)

    var_list = []
    for v in variables:
        var_dict = {k: val for k, val in v.items() if not k.startswith("_")}
        stats = var_dict.pop("stats", None)
        var_dict["stats"] = stats
        var_list.append(var_dict)

    result = {**file_meta, "dataset_summary": dataset_summary, "variables": var_list}

    if head_rows is not None or tail_rows is not None:
        data_preview = {}
        if head_rows is not None:
            data_preview["head"] = head_rows
        if tail_rows is not None:
            data_preview["tail"] = tail_rows
        result["data_preview"] = data_preview

    return result


def build_csv_output(file_meta: dict, variables: list[dict]) -> str:
    """Build a flat CSV string — one row per variable, no nested structures."""
    SCALAR_STAT_FIELDS = [
        "stat_type", "spss_measure", "total_count", "valid_count", "missing_count",
        "percent_missing", "unique_count", "has_data", "mean", "median", "std",
        "variance", "min", "max", "range", "sum", "q1", "q3", "iqr", "p5", "p10",
        "p90", "p95", "skewness", "kurtosis", "sem", "cv", "mode", "mode_count",
        "min_length", "max_length", "mean_length",
    ]

    var_fields = ["name", "label", "type", "format", "width", "decimals",
                  "measure", "missing_values", "values"]

    fieldnames = var_fields + [f"stat_{f}" for f in SCALAR_STAT_FIELDS]

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()

    for v in variables:
        row = {f: _safe(v.get(f)) for f in var_fields}
        if isinstance(row.get("values"), dict):
            row["values"] = json.dumps(row["values"])
        stats = v.get("stats") or {}
        for f in SCALAR_STAT_FIELDS:
            row[f"stat_{f}"] = _safe(stats.get(f))
        writer.writerow(row)

    return buf.getvalue()
