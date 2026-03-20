import csv
import io
import pytest

from metaextract.output import build_json_output, build_csv_output, _build_dataset_summary


@pytest.fixture
def variables_with_stats(sample_variables, sample_df):
    """Variables list with computed stats attached."""
    from metaextract.stats import compute_all_stats
    import copy
    vars_copy = copy.deepcopy(sample_variables)
    return compute_all_stats(sample_df, vars_copy, top_n=20, skip_stats=False)


@pytest.fixture
def variables_no_stats(sample_variables):
    import copy
    return copy.deepcopy(sample_variables)


class TestBuildJsonOutput:
    def test_internal_keys_stripped(self, sample_file_meta, variables_with_stats):
        result = build_json_output(sample_file_meta, variables_with_stats)
        for var in result["variables"]:
            assert not any(k.startswith("_") for k in var.keys())

    def test_stats_merged_into_variables(self, sample_file_meta, variables_with_stats):
        result = build_json_output(sample_file_meta, variables_with_stats)
        for var in result["variables"]:
            assert "stats" in var

    def test_dataset_summary_present(self, sample_file_meta, variables_with_stats):
        result = build_json_output(sample_file_meta, variables_with_stats)
        assert "dataset_summary" in result
        assert "total_variables" in result["dataset_summary"]

    def test_variables_list_present(self, sample_file_meta, variables_with_stats):
        result = build_json_output(sample_file_meta, variables_with_stats)
        assert "variables" in result
        assert len(result["variables"]) == 5

    def test_source_file_in_output(self, sample_file_meta, variables_with_stats):
        result = build_json_output(sample_file_meta, variables_with_stats)
        assert result["source_file"] == "/tmp/sample.csv"

    def test_spss_measure_not_emitted_in_json_stats(self, sample_file_meta, variables_with_stats):
        result = build_json_output(sample_file_meta, variables_with_stats)
        for var in result["variables"]:
            stats = var.get("stats")
            if stats is not None:
                assert "spss_measure" not in stats


class TestBuildCSVOutput:
    def test_no_nested_structures(self, sample_file_meta, variables_with_stats):
        text = build_csv_output(sample_file_meta, variables_with_stats)
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            # No cell should contain a dict or list (would appear as '{' or '[')
            for val in row.values():
                assert not (isinstance(val, str) and val.startswith("{"))
                assert not (isinstance(val, str) and val.startswith("["))

    def test_stat_prefix_on_stat_fields(self, sample_file_meta, variables_with_stats):
        text = build_csv_output(sample_file_meta, variables_with_stats)
        reader = csv.DictReader(io.StringIO(text))
        fieldnames = reader.fieldnames
        stat_fields = [f for f in fieldnames if f.startswith("stat_")]
        assert len(stat_fields) > 0
        assert "stat_spss_measure" not in fieldnames

    def test_one_row_per_variable(self, sample_file_meta, variables_with_stats):
        text = build_csv_output(sample_file_meta, variables_with_stats)
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        assert len(rows) == 5

    def test_tab_cr_lf_prefixed_cells_are_escaped(self, sample_file_meta):
        variables = [{
            "name": "\ttab_start",
            "label": "\rcarriage",
            "type": "string",
            "format": None,
            "width": None,
            "decimals": None,
            "measure": None,
            "missing_values": "\nnewline",
            "values": None,
            "stats": None,
        }]
        text = build_csv_output(sample_file_meta, variables)
        row = next(csv.DictReader(io.StringIO(text)))
        assert row["name"] == "'\ttab_start"
        assert row["label"] == "'\rcarriage"
        assert row["missing_values"] == "'\nnewline"

    def test_formula_like_cells_are_escaped(self, sample_file_meta):
        variables = [{
            "name": "=SUM(1,1)",
            "label": "+cmd",
            "type": "string",
            "format": None,
            "width": None,
            "decimals": None,
            "measure": None,
            "missing_values": "@missing",
            "values": {"@x": "-danger"},
            "stats": None,
        }]
        text = build_csv_output(sample_file_meta, variables)
        row = next(csv.DictReader(io.StringIO(text)))
        assert row["name"] == "'=SUM(1,1)"
        assert row["label"] == "'+cmd"
        assert row["missing_values"] == "'@missing"


class TestBuildJsonOutputDataPreview:
    def test_no_preview_by_default(self, sample_file_meta, variables_with_stats):
        result = build_json_output(sample_file_meta, variables_with_stats)
        assert "data_preview" not in result

    def test_head_only(self, sample_file_meta, variables_with_stats):
        rows = [{"age": 25, "score": 1.1}]
        result = build_json_output(sample_file_meta, variables_with_stats, head_rows=rows)
        assert "data_preview" in result
        assert "head" in result["data_preview"]
        assert "tail" not in result["data_preview"]
        assert result["data_preview"]["head"] == rows

    def test_tail_only(self, sample_file_meta, variables_with_stats):
        rows = [{"age": 35, "score": 5.5}]
        result = build_json_output(sample_file_meta, variables_with_stats, tail_rows=rows)
        assert "data_preview" in result
        assert "tail" in result["data_preview"]
        assert "head" not in result["data_preview"]

    def test_both_head_and_tail(self, sample_file_meta, variables_with_stats):
        head = [{"age": 25}]
        tail = [{"age": 35}]
        result = build_json_output(sample_file_meta, variables_with_stats, head_rows=head, tail_rows=tail)
        assert "head" in result["data_preview"]
        assert "tail" in result["data_preview"]

    def test_empty_head_rows(self, sample_file_meta, variables_with_stats):
        result = build_json_output(sample_file_meta, variables_with_stats, head_rows=[])
        assert "data_preview" in result
        assert result["data_preview"]["head"] == []


class TestBuildDatasetSummary:
    def test_stats_computed_true(self, sample_file_meta, variables_with_stats):
        summary = _build_dataset_summary(sample_file_meta, variables_with_stats, stats_computed=True)
        assert summary["stats_computed"] is True

    def test_stats_computed_false(self, sample_file_meta, variables_no_stats):
        summary = _build_dataset_summary(sample_file_meta, variables_no_stats, stats_computed=False)
        assert summary["stats_computed"] is False

    def test_counts_by_stat_type(self, sample_file_meta, variables_with_stats):
        summary = _build_dataset_summary(sample_file_meta, variables_with_stats, stats_computed=True)
        total = (
            summary["continuous_variable_count"]
            + summary["datetime_variable_count"]
            + summary["categorical_variable_count"]
            + summary["string_variable_count"]
        )
        # At least some categories should be populated
        assert total >= 0
        assert summary["total_variables"] == 5
        assert summary["datetime_variable_count"] == 1
