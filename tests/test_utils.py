import math
import numpy as np
import pandas as pd
import pytest

from metaextract.utils import _safe, _format_value_labels, infer_pandas_type


class TestSafe:
    def test_none(self):
        assert _safe(None) is None

    def test_nan(self):
        assert _safe(float("nan")) is None

    def test_numpy_int(self):
        val = _safe(np.int64(42))
        assert val == 42
        assert isinstance(val, int)

    def test_numpy_float(self):
        val = _safe(np.float64(3.14159))
        assert isinstance(val, float)
        assert abs(val - 3.14159) < 1e-4

    def test_numpy_bool(self):
        val = _safe(np.bool_(True))
        assert val is True
        assert isinstance(val, bool)

    def test_pandas_timestamp(self):
        ts = pd.Timestamp("2024-01-15")
        val = _safe(ts)
        assert isinstance(val, str)
        assert "2024-01-15" in val

    def test_regular_string(self):
        assert _safe("hello") == "hello"

    def test_regular_int(self):
        assert _safe(5) == 5

    def test_numpy_nan_float(self):
        assert _safe(np.float64("nan")) is None


class TestFormatValueLabels:
    def test_empty_dict(self):
        assert _format_value_labels({}) is None

    def test_populated_dict(self):
        result = _format_value_labels({1: "Yes", 2: "No"})
        assert result == {"1": "Yes", "2": "No"}

    def test_single_entry(self):
        result = _format_value_labels({0: "Male"})
        assert result == {"0": "Male"}


class TestInferPandasType:
    def test_bool(self):
        assert infer_pandas_type(pd.Series([True, False]).dtype) == "boolean"

    def test_int(self):
        assert infer_pandas_type(pd.Series([1, 2, 3]).dtype) == "numeric"

    def test_float(self):
        assert infer_pandas_type(pd.Series([1.0, 2.0]).dtype) == "numeric"

    def test_object(self):
        assert infer_pandas_type(pd.Series(["a", "b"]).dtype) == "string"

    def test_datetime(self):
        dtype = pd.to_datetime(["2020-01-01", "2021-01-01"]).dtype
        assert infer_pandas_type(dtype) == "datetime"

    def test_bool_before_numeric(self):
        # bool dtype must resolve to "boolean", not "numeric"
        import numpy as np
        bool_dtype = np.dtype("bool")
        assert infer_pandas_type(bool_dtype) == "boolean"
