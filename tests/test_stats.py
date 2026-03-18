import numpy as np
import pandas as pd
import pytest

from metaextract.stats import _is_categorical, _compute_freq, _compute_variable_stats


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
        result = _compute_freq(col, labels, non_null=2)
        assert result["2.0"]["count"] == 0

    def test_snapping(self):
        # Values slightly off from label keys should snap
        col = pd.Series([0.9, 2.1])
        labels = {1.0: "Low", 2.0: "High"}
        result = _compute_freq(col, labels, non_null=2)
        assert result["1.0"]["count"] == 1
        assert result["2.0"]["count"] == 1


class TestComputeVariableStats:
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
