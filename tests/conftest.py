import io
import pytest
import pandas as pd
import numpy as np


@pytest.fixture
def sample_df():
    return pd.DataFrame({
        "age": [25, 30, 45, np.nan, 35],
        "score": [1.1, 2.2, 3.3, 4.4, 5.5],
        "name": ["Alice", "Bob", "Charlie", "Diana", "Eve"],
        "active": [True, False, True, False, True],
        "created": pd.to_datetime(["2020-01-01", "2021-06-15", "2022-03-10", "2023-07-04", "2024-11-30"]),
    })


@pytest.fixture
def sample_variables():
    return [
        {
            "name": "age", "_raw_col_name": "age",
            "label": "Age in years", "type": "numeric",
            "format": None, "width": None, "decimals": None,
            "measure": "scale", "missing_values": None,
            "values": "", "_raw_value_labels": {},
            "stats": None,
        },
        {
            "name": "score", "_raw_col_name": "score",
            "label": None, "type": "numeric",
            "format": None, "width": None, "decimals": None,
            "measure": "scale", "missing_values": None,
            "values": "", "_raw_value_labels": {},
            "stats": None,
        },
        {
            "name": "name", "_raw_col_name": "name",
            "label": None, "type": "string",
            "format": None, "width": None, "decimals": None,
            "measure": None, "missing_values": None,
            "values": "", "_raw_value_labels": {},
            "stats": None,
        },
        {
            "name": "active", "_raw_col_name": "active",
            "label": None, "type": "boolean",
            "format": None, "width": None, "decimals": None,
            "measure": None, "missing_values": None,
            "values": "", "_raw_value_labels": {},
            "stats": None,
        },
        {
            "name": "created", "_raw_col_name": "created",
            "label": None, "type": "datetime",
            "format": None, "width": None, "decimals": None,
            "measure": None, "missing_values": None,
            "values": "", "_raw_value_labels": {},
            "stats": None,
        },
    ]


@pytest.fixture
def sample_file_meta():
    return {
        "source_file": "/tmp/sample.csv",
        "file_label": "",
        "file_encoding": "",
        "number_rows": 5,
        "number_columns": 5,
        "creation_time": "2024-01-01",
        "modification_time": "2024-01-02",
        "notes": [],
    }


@pytest.fixture
def sample_csv_path(tmp_path):
    p = tmp_path / "sample.csv"
    p.write_text("id,name,score\n1,Alice,95.5\n2,Bob,82.0\n3,Charlie,77.3\n")
    return p


@pytest.fixture
def sample_excel_path(tmp_path):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["id", "name", "score"])
    ws.append([1, "Alice", 95.5])
    ws.append([2, "Bob", 82.0])
    ws2 = wb.create_sheet("Sheet2")
    ws2.append(["x", "y"])
    ws2.append([10, 20])
    path = tmp_path / "sample.xlsx"
    wb.save(path)
    return path


@pytest.fixture
def sample_parquet_path(tmp_path):
    df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    path = tmp_path / "sample.parquet"
    df.to_parquet(path, index=False)
    return path
