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

    def test_tsv_auto_delimiter(self, runner, tmp_path):
        p = tmp_path / "data.tsv"
        p.write_text("a\tb\tc\n1\t2\t3\n4\t5\t6\n")
        result = runner.invoke(main, [str(p)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["variables"]) == 3
