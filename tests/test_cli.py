import csv
import io
import json
import pytest
from click.testing import CliRunner

from metaextract.cli import main


@pytest.fixture
def runner():
    return CliRunner()


class TestCLIBasic:
    def test_json_to_stdout(self, runner, sample_csv_path):
        result = runner.invoke(main, [str(sample_csv_path)])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "variables" in data
        assert "dataset_summary" in data

    def test_output_format_csv(self, runner, sample_csv_path):
        result = runner.invoke(main, [str(sample_csv_path), "--output-format", "csv"])
        assert result.exit_code == 0, result.output
        reader = csv.DictReader(io.StringIO(result.output))
        rows = list(reader)
        assert len(rows) == 3  # 3 columns in sample CSV

    def test_output_to_file(self, runner, sample_csv_path, tmp_path):
        out_file = tmp_path / "out.json"
        result = runner.invoke(main, [str(sample_csv_path), "-o", str(out_file)])
        assert result.exit_code == 0, result.output
        assert out_file.exists()
        data = json.loads(out_file.read_text())
        assert "variables" in data

    def test_no_stats(self, runner, sample_csv_path):
        result = runner.invoke(main, [str(sample_csv_path), "--no-stats"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        for var in data["variables"]:
            assert var["stats"] is None

    def test_no_header(self, runner, tmp_path):
        p = tmp_path / "noheader.csv"
        p.write_text("1,Alice,95.5\n2,Bob,82.0\n")
        result = runner.invoke(main, [str(p), "--no-header"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        names = [v["name"] for v in data["variables"]]
        assert "col_0" in names
        assert "col_1" in names

    def test_help_exits_zero(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Usage" in result.output

    def test_invalid_file_path(self, runner):
        result = runner.invoke(main, ["/nonexistent/path/file.csv"])
        assert result.exit_code != 0

    def test_unknown_suffix_without_format(self, runner, tmp_path):
        p = tmp_path / "file.xyz"
        p.write_text("data")
        result = runner.invoke(main, [str(p)])
        assert result.exit_code != 0
        assert "format" in result.output.lower() or "suffix" in result.output.lower()

    def test_force_format_with_csv(self, runner, sample_csv_path):
        result = runner.invoke(main, [str(sample_csv_path), "-f", "csv"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "variables" in data

    def test_force_format_with_qualtrics(self, runner, qualtrics_csv_path):
        result = runner.invoke(main, [str(qualtrics_csv_path), "-f", "qualtrics", "--no-stats"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["csv_mode"] == "qualtrics"
        assert data["metadata_rows_skipped"] == 1
        assert data["variables"][1]["name"] == "qid1"
        assert data["variables"][1]["label"] == "How satisfied are you?"

    def test_tsv_auto_delimiter(self, runner, tmp_path):
        p = tmp_path / "data.tsv"
        p.write_text("a\tb\tc\n1\t2\t3\n4\t5\t6\n")
        result = runner.invoke(main, [str(p)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["variables"]) == 3


class TestCLIDataPreview:
    def test_head_two_rows(self, runner, sample_csv_path):
        result = runner.invoke(main, [str(sample_csv_path), "--head", "2"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "data_preview" in data
        assert "head" in data["data_preview"]
        assert "tail" not in data["data_preview"]
        assert len(data["data_preview"]["head"]) == 2

    def test_tail_one_row(self, runner, sample_csv_path):
        result = runner.invoke(main, [str(sample_csv_path), "--tail", "1"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "data_preview" in data
        assert "tail" in data["data_preview"]
        assert "head" not in data["data_preview"]
        assert len(data["data_preview"]["tail"]) == 1

    def test_head_and_tail(self, runner, sample_csv_path):
        result = runner.invoke(main, [str(sample_csv_path), "--head", "1", "--tail", "1"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "head" in data["data_preview"]
        assert "tail" in data["data_preview"]

    def test_head_exceeds_row_count(self, runner, sample_csv_path):
        # sample_csv_path has 3 rows; --head 100 should return all 3
        result = runner.invoke(main, [str(sample_csv_path), "--head", "100"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert len(data["data_preview"]["head"]) == 3

    def test_no_flags_no_preview(self, runner, sample_csv_path):
        result = runner.invoke(main, [str(sample_csv_path)])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "data_preview" not in data

    def test_csv_output_with_head_warns(self, runner, sample_csv_path):
        result = runner.invoke(main, [str(sample_csv_path), "--output-format", "csv", "--head", "2"])
        assert result.exit_code == 0
        # Warning goes to stderr; CliRunner mixes streams by default — check output contains warning
        assert "Warning" in result.output or "warning" in result.output.lower()

    def test_row_keys_are_lowercased(self, runner, tmp_path):
        p = tmp_path / "mixed.csv"
        p.write_text("ID,Name,Score\n1,Alice,95.5\n")
        result = runner.invoke(main, [str(p), "--head", "1"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        row = data["data_preview"]["head"][0]
        assert "id" in row
        assert "name" in row
        assert "score" in row

    def test_tail_zero_returns_empty(self, runner, sample_csv_path):
        result = runner.invoke(main, [str(sample_csv_path), "--tail", "0"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["data_preview"]["tail"] == []

    def test_detected_datetime_preview_is_iso8601(self, runner, tmp_path):
        p = tmp_path / "dates.csv"
        p.write_text(
            "created_at,name\n"
            "2024-01-01 10:15:00,Alice\n"
            "2024-01-02 08:30:00,Bob\n"
            ",Cara\n"
        )
        result = runner.invoke(main, [str(p), "--head", "2", "--no-stats"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        head = data["data_preview"]["head"]
        assert head[0]["created_at"] == "2024-01-01T10:15:00"
        assert head[1]["created_at"] == "2024-01-02T08:30:00"

    def test_negative_head_rejected(self, runner, sample_csv_path):
        result = runner.invoke(main, [str(sample_csv_path), "--head", "-1"])
        assert result.exit_code != 0

    def test_qualtrics_head_starts_with_first_response_row(self, runner, qualtrics_csv_path):
        result = runner.invoke(main, [str(qualtrics_csv_path), "-f", "qualtrics", "--head", "1", "--no-stats"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        row = data["data_preview"]["head"][0]
        assert row["responseid"] == "R_1"
        assert row["qid1"] == "Very satisfied"
        assert row["qid2"] == "Great service"


class TestCLIDataOnly:
    def test_head_only_returns_array(self, runner, sample_csv_path):
        result = runner.invoke(main, [str(sample_csv_path), "--head", "2", "--data-only"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 2

    def test_tail_only_returns_array(self, runner, sample_csv_path):
        result = runner.invoke(main, [str(sample_csv_path), "--tail", "1", "--data-only"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1

    def test_head_and_tail_returns_object(self, runner, sample_csv_path):
        result = runner.invoke(main, [str(sample_csv_path), "--head", "1", "--tail", "1", "--data-only"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert isinstance(data, dict)
        assert "head" in data and "tail" in data
        assert isinstance(data["head"], list)
        assert isinstance(data["tail"], list)

    def test_data_only_without_head_or_tail_errors(self, runner, sample_csv_path):
        result = runner.invoke(main, [str(sample_csv_path), "--data-only"])
        assert result.exit_code != 0

    def test_data_only_no_metadata_keys(self, runner, sample_csv_path):
        result = runner.invoke(main, [str(sample_csv_path), "--head", "2", "--data-only"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert not any(k in data for k in ("variables", "dataset_summary", "source_file"))

    def test_data_only_detected_datetime_is_iso8601(self, runner, tmp_path):
        p = tmp_path / "dates.csv"
        p.write_text("created_at\n2024-01-01 10:15:00\n2024-01-02 12:00:00\n")
        result = runner.invoke(main, [str(p), "--head", "1", "--data-only", "--no-stats"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data[0]["created_at"] == "2024-01-01T10:15:00"


class TestCLIQualtricsStats:
    def test_qualtrics_stats_do_not_include_label_row(self, runner, qualtrics_csv_path):
        result = runner.invoke(main, [str(qualtrics_csv_path), "-f", "qualtrics"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        qid1 = next(v for v in data["variables"] if v["name"] == "qid1")
        top_values = qid1["stats"]["top_values"]
        assert all(item["value"] != "How satisfied are you?" for item in top_values)
        assert {item["value"] for item in top_values} == {"Very satisfied", "Neutral"}
