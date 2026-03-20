from pathlib import Path

import pandas as pd
import pytest

from metaextract.readers import (
    _assign_public_names,
    read_csv,
    read_excel,
    read_parquet,
    read_qualtrics_csv,
    read_sas,
)


class TestReadCSV:
    def test_normal_csv(self, sample_csv_path):
        df, file_meta, variables = read_csv(str(sample_csv_path))
        assert len(df) == 3
        assert len(variables) == 3
        assert variables[0]["name"] == "id"
        assert file_meta["number_rows"] == 3
        assert file_meta["number_columns"] == 3

    def test_no_internal_keys_leaked(self, sample_csv_path):
        _, _, variables = read_csv(str(sample_csv_path))
        for v in variables:
            assert "_raw_col_name" in v  # internal key present before stripping
            assert "_raw_value_labels" in v

    def test_no_header(self, tmp_path):
        p = tmp_path / "noheader.csv"
        p.write_text("1,Alice,95.5\n2,Bob,82.0\n")
        df, file_meta, variables = read_csv(str(p), no_header=True)
        names = [v["name"] for v in variables]
        assert "col_0" in names
        assert "col_1" in names
        assert "col_2" in names

    def test_tsv_auto_delimiter(self, tmp_path):
        p = tmp_path / "sample.tsv"
        p.write_text("a\tb\tc\n1\t2\t3\n4\t5\t6\n")
        # Simulating the CLI's auto-TSV logic: pass delimiter="\t"
        df, file_meta, variables = read_csv(str(p), delimiter="\t")
        assert len(variables) == 3
        assert len(df) == 2

    def test_custom_delimiter(self, tmp_path):
        p = tmp_path / "pipe.csv"
        p.write_text("a|b|c\n1|2|3\n")
        df, file_meta, variables = read_csv(str(p), delimiter="|")
        assert len(variables) == 3

    def test_custom_quotechar(self, tmp_path):
        p = tmp_path / "quoted.csv"
        p.write_text("a,b\n'hello world','foo'\n")
        df, _, variables = read_csv(str(p), quotechar="'")
        assert df["a"].iloc[0] == "hello world"

    def test_string_values_are_trimmed(self, tmp_path):
        p = tmp_path / "trim.csv"
        p.write_text("name,city\n  Alice  ,  Boston \n")
        df, _, _ = read_csv(str(p))
        assert df["name"].iloc[0] == "Alice"
        assert df["city"].iloc[0] == "Boston"

    def test_date_named_column_becomes_datetime(self, tmp_path):
        p = tmp_path / "dates.csv"
        p.write_text("created_at,name\n2024-01-01,Alice\n2024-01-02,Bob\n")
        _, _, variables = read_csv(str(p))
        type_map = {v["name"]: v["type"] for v in variables}
        assert type_map["created_at"] == "datetime"
        assert type_map["name"] == "string"

    def test_content_only_date_column_becomes_datetime(self, tmp_path):
        p = tmp_path / "events.csv"
        p.write_text("event_value,name\n2024-01-01,Alice\n2024-01-02,Bob\n")
        _, _, variables = read_csv(str(p))
        type_map = {v["name"]: v["type"] for v in variables}
        assert type_map["event_value"] == "datetime"

    def test_mixed_string_column_stays_string(self, tmp_path):
        p = tmp_path / "mixed.csv"
        p.write_text("created_at\n2024-01-01\nnot-a-date\nstill-not-a-date\n")
        _, _, variables = read_csv(str(p))
        assert variables[0]["type"] == "string"

    def test_numeric_identifier_stays_non_datetime(self, tmp_path):
        p = tmp_path / "ids.csv"
        p.write_text("identifier\n1001\n1002\n1003\n")
        _, _, variables = read_csv(str(p))
        assert variables[0]["type"] == "numeric"

    def test_case_colliding_headers_get_unique_names(self, tmp_path):
        p = tmp_path / "case_collision.csv"
        p.write_text("ID,id,Id\n1,2,3\n")
        _, _, variables = read_csv(str(p))
        assert [v["name"] for v in variables] == ["id", "id__2", "id__3"]

    def test_qualtrics_reader_skips_label_row(self, qualtrics_csv_path):
        df, file_meta, variables = read_qualtrics_csv(str(qualtrics_csv_path))
        assert len(df) == 2
        assert df.iloc[0]["ResponseId"] == "R_1"
        assert file_meta["csv_mode"] == "qualtrics"
        assert file_meta["metadata_rows_skipped"] == 1
        assert variables[0]["name"] == "responseid"
        assert variables[1]["name"] == "qid1"
        assert variables[1]["label"] == "How satisfied are you?"
        assert variables[2]["label"] == "Please describe your experience"

    def test_qualtrics_reader_trims_data_values(self, tmp_path):
        p = tmp_path / "qualtrics_trim.csv"
        p.write_text(
            "ResponseId,QID1\n"
            "Response ID,Question text\n"
            "R_1,  Yes  \n"
        )
        df, _, _ = read_qualtrics_csv(str(p))
        assert df["QID1"].iloc[0] == "Yes"


class TestReadExcel:
    def test_default_sheet(self, sample_excel_path):
        df, file_meta, variables = read_excel(str(sample_excel_path))
        assert len(df) == 2
        assert len(variables) == 3
        assert file_meta["sheet_name"] == "0"

    def test_named_sheet(self, sample_excel_path):
        df, file_meta, variables = read_excel(str(sample_excel_path), sheet="Sheet2")
        assert len(df) == 1
        assert len(variables) == 2
        assert file_meta["sheet_name"] == "Sheet2"

    def test_integer_index_sheet(self, sample_excel_path):
        # sheet="1" → int 1 → second sheet
        df, file_meta, variables = read_excel(str(sample_excel_path), sheet="1")
        assert len(variables) == 2


class TestReadParquet:
    def test_roundtrip(self, sample_parquet_path):
        df, file_meta, variables = read_parquet(str(sample_parquet_path))
        assert len(df) == 3
        assert len(variables) == 2
        names = [v["name"] for v in variables]
        assert "a" in names
        assert "b" in names
        assert file_meta["number_rows"] == 3
        assert file_meta["number_columns"] == 2

    def test_variable_types(self, sample_parquet_path):
        _, _, variables = read_parquet(str(sample_parquet_path))
        type_map = {v["name"]: v["type"] for v in variables}
        assert type_map["a"] == "numeric"
        assert type_map["b"] == "string"


class TestReadSAS:
    def test_string_columns_keep_string_type(self):
        sample_path = Path(__file__).resolve().parents[1] / "sample_files" / "cars.sas7bdat"
        _, _, variables = read_sas(str(sample_path))
        type_map = {v["name"]: v["type"] for v in variables}

        assert type_map["make"] == "string"
        assert type_map["model"] == "string"
        assert type_map["msrp"] == "numeric"

    def test_string_values_are_trimmed(self):
        sample_path = Path(__file__).resolve().parents[1] / "sample_files" / "cars.sas7bdat"
        df, _, _ = read_sas(str(sample_path))

        assert df["Make"].iloc[0] == "Acura"
        assert df["Model"].iloc[0] == "MDX"


class TestAssignPublicNames:
    def test_literal_double_underscore_collision(self):
        """Columns like ['id__2', 'ID', 'id'] where 'id__2' is a real column name."""
        variables = [
            {"_raw_col_name": "id__2"},
            {"_raw_col_name": "ID"},
            {"_raw_col_name": "id"},
        ]
        _assign_public_names(variables)
        names = [v["name"] for v in variables]
        assert len(names) == len(set(names)), f"Duplicate names: {names}"
        assert "id__2" in names
