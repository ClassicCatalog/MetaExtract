import numpy as np
import pandas as pd
import pytest

from metaextract.stats import (
    _is_categorical,
    _compute_freq,
    _compute_variable_stats,
    _build_raw_frequency_stats,
    compute_all_stats,
)


class TestIsCategorical:
    def test_nominal_always_categorical(self):
        assert _is_categorical("numeric", "nominal", {}) is True
        assert _is_categorical("numeric", "nominal", {1: "Yes"}) is True

    def test_ordinal_always_categorical(self):
        assert _is_categorical("numeric", "ordinal", {}) is True
        assert _is_categorical("string", "ordinal", {1: "Low"}) is True

    def test_scale_no_labels_continuous(self):
        assert _is_categorical("numeric", "scale", {}) is False

    def test_scale_numeric_labels_continuous(self):
        # All-numeric label text → rating scale, treat as continuous
        assert _is_categorical("numeric", "scale", {1: "1", 10: "10"}) is False

    def test_scale_text_labels_categorical(self):
        assert _is_categorical("numeric", "scale", {1: "Yes", 2: "No"}) is True

    def test_unknown_measure_with_labels(self):
        assert _is_categorical("numeric", None, {1: "Male", 2: "Female"}) is True

    def test_unknown_measure_no_labels(self):
        assert _is_categorical("numeric", None, {}) is False

    def test_unknown_measure_empty_string(self):
        assert _is_categorical("numeric", "", {}) is False


class TestComputeFreq:
    def test_basic_frequency(self):
        col = pd.Series([1.0, 2.0, 1.0, 1.0, 2.0])
        labels = {1.0: "Yes", 2.0: "No"}
        result = _compute_freq(col, labels, non_null=5)
        assert result["1.0"]["count"] == 3
        assert result["2.0"]["count"] == 2
        assert result["1.0"]["label"] == "Yes"
        assert result["1.0"]["percent"] == 60.0

    def test_zero_count_key(self):
        col = pd.Series([1.0, 1.0])
        labels = {1.0: "Yes", 2.0: "No"}
        result = _compute_freq(col, labels, non_null=3)
        assert result["2.0"]["count"] == 0

    def test_out_of_domain_values_are_not_reassigned(self):
        col = pd.Series([1.0, 2.0, 999.0])
        labels = {1.0: "Low", 2.0: "High"}
        result = _compute_freq(col, labels, non_null=2)
        assert result["1.0"]["count"] == 1
        assert result["2.0"]["count"] == 1

    def test_frequency_is_limited_to_top_n(self):
        col = pd.Series([1, 1, 1, 2, 2, 3])
        labels = {1: "One", 2: "Two", 3: "Three"}
        result = _compute_freq(col, labels, non_null=6, top_n=2)
        assert list(result.keys()) == ["1", "2"]


class TestComputeVariableStats:
    def test_datetime_stats(self):
        series = pd.to_datetime(pd.Series([
            "2024-01-01",
            "2024-01-02",
            "2024-01-03",
            "2024-01-03",
        ]))
        stats = _compute_variable_stats("created_at", series, "datetime", {}, None)
        assert stats["stat_type"] == "datetime"
        assert stats["min"] == "2024-01-01T00:00:00"
        assert stats["max"] == "2024-01-03T00:00:00"
        assert stats["mean"] == "2024-01-02T06:00:00"
        assert stats["median"] == "2024-01-02T12:00:00"
        assert stats["mode"] == "2024-01-03T00:00:00"
        assert stats["mode_count"] == 2
        assert stats["std_seconds"] == pytest.approx(82721.702118)
        assert "q1" not in stats

    def test_continuous_stats(self):
        series = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        stats = _compute_variable_stats("val", series, "numeric", {}, "scale")
        assert stats["stat_type"] == "continuous"
        assert stats["mean"] == 30.0
        assert stats["min"] == 10.0
        assert stats["max"] == 50.0
        assert "std" in stats
        assert "q1" in stats
        assert stats["has_data"] is True

    def test_categorical_path(self):
        series = pd.Series([1.0, 2.0, 1.0, 2.0])
        labels = {1.0: "Yes", 2.0: "No"}
        stats = _compute_variable_stats("cat", series, "numeric", labels, "nominal")
        assert stats["stat_type"] == "categorical"
        assert "value_frequencies" in stats

    def test_nominal_string_path_uses_categorical_stats(self):
        series = pd.Series(["F", "M", "F"])
        stats = _compute_variable_stats("gender", series, "string", {}, "nominal")
        assert stats["stat_type"] == "categorical"
        assert stats["value_frequencies"]["F"]["count"] == 2
        assert "top_values" not in stats

    def test_string_path(self):
        series = pd.Series(["apple", "banana", "apple", "cherry"])
        stats = _compute_variable_stats("fruit", series, "string", {}, None, top_n=20)
        assert stats["stat_type"] == "string"
        assert "top_values" in stats
        assert "min_length" in stats
        assert len(stats["top_values"]) <= 20

    def test_all_missing(self):
        series = pd.Series([np.nan, np.nan, np.nan])
        stats = _compute_variable_stats("empty", series, "numeric", {}, "scale")
        assert stats["has_data"] is False

    def test_top_n_override(self):
        series = pd.Series([f"val_{i}" for i in range(50)])
        stats = _compute_variable_stats("v", series, "string", {}, None, top_n=5)
        assert len(stats["top_values"]) <= 5

    def test_missing_counts(self):
        series = pd.Series([1.0, np.nan, 3.0, np.nan])
        stats = _compute_variable_stats("x", series, "numeric", {}, "scale")
        assert stats["missing_count"] == 2
        assert stats["valid_count"] == 2


class TestBuildRawFrequencyStats:
    def test_empty_series(self):
        series = pd.Series([], dtype="float64")
        result = _build_raw_frequency_stats(series, non_null=0)
        assert result == {}

    def test_nonzero_series_with_zero_non_null(self):
        series = pd.Series([1.0, 2.0])
        result = _build_raw_frequency_stats(series, non_null=0)
        for val in result.values():
            assert val["percent"] == 0.0

    def test_limits_to_top_n(self):
        series = pd.Series(["a", "a", "a", "b", "b", "c"])
        result = _build_raw_frequency_stats(series, non_null=6, top_n=2)
        assert list(result.keys()) == ["a", "b"]


class TestCVEdgeCases:
    def test_cv_absent_when_mean_is_zero(self):
        series = pd.Series([-1.0, 1.0])
        stats = _compute_variable_stats("x", series, "numeric", {}, "scale")
        assert "cv" not in stats

    def test_cv_present_when_mean_nonzero(self):
        series = pd.Series([10.0, 20.0, 30.0])
        stats = _compute_variable_stats("x", series, "numeric", {}, "scale")
        assert "cv" in stats
        assert stats["cv"] is not None


class TestNullableBooleanDtype:
    def test_nullable_boolean_dtype(self):
        arr = pd.array([True, False, None, True], dtype="boolean")
        series = pd.Series(arr)
        df = pd.DataFrame({"is_active": series})
        variables = [{
            "name": "is_active", "_raw_col_name": "is_active",
            "label": None, "type": "boolean",
            "format": None, "width": None, "decimals": None,
            "measure": None, "missing_values": None,
            "values": None, "_raw_value_labels": {},
            "stats": None,
        }]
        result = compute_all_stats(df, variables, top_n=20, skip_stats=False)
        stats = result[0]["stats"]
        assert stats["missing_count"] == 1
        assert stats["valid_count"] == 3


class TestDiscreteStats:
    def test_name_prefix_triggers_discrete(self):
        series = pd.Series([0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1] * 10)
        stats = _compute_variable_stats("is_active", series, "numeric", {}, None)
        assert stats["stat_type"] == "discrete"

    def test_low_cardinality_triggers_discrete(self):
        series = pd.Series([1, 2, 3, 1, 2, 3, 1, 2, 3])
        stats = _compute_variable_stats("code", series, "numeric", {}, None)
        assert stats["stat_type"] == "discrete"

    def test_discrete_value_frequencies_respect_top_n(self):
        series = pd.Series([1] * 5 + [2] * 4 + [3] * 3 + [4] * 2)
        stats = _compute_variable_stats("code", series, "numeric", {}, None, top_n=3)
        assert list(stats["value_frequencies"].keys()) == ["1", "2", "3"]
