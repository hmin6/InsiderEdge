import pandas as pd
import pytest

from app.ml.dataset import build_ml_dataset, split_temporally
from test_ml_dataset import dataset_inputs


def test_exact_strict_purge_boundaries():
    dates = ["2024-11-01", "2024-11-02", "2024-11-03", "2025-01-02", "2025-11-01", "2026-01-02"]
    ends = ["2025-01-01", "2025-01-02", "2025-01-03", "2025-02-20", "2026-01-02", "2026-02-20"]
    result = split_temporally(build_ml_dataset(*dataset_inputs(dates, ends)))
    assert result.partitions["train"].tolist() == ["event:0"]
    assert result.partitions["validation"].tolist() == ["event:3"]
    assert result.partitions["test"].tolist() == ["event:5"]
    assert result.summary.loc["train", "purged_count"] == 2
    assert result.summary.loc["validation", "purged_count"] == 1
    assert result.audit.loc["event:1", "exclusion_reasons"] == ["purged_outcome_overlap"]


def test_unavailable_labels_out_of_range_same_day_and_repeated_tickers():
    inputs = list(dataset_inputs(["2019-01-01", "2024-03-01", "2024-03-01", "2025-03-01", "2026-03-01"]))
    inputs[0].loc[2, "ticker"] = "DEF"
    inputs[2].loc[1, ["Y", "outcome_end"]] = [None, pd.NaT]
    inputs[2].loc[1, "label_status"] = "unavailable"
    result = split_temporally(build_ml_dataset(*inputs))
    assert result.audit.loc["event:1", "partition"] == result.audit.loc["event:2", "partition"] == "train"
    assert result.summary.loc["train", "unavailable_label_count"] == 1
    assert result.summary.loc["out_of_range", "out_of_range_count"] == 1
    assert len(result.audit) == 5


def test_chronological_boundaries_are_independent_of_labels_and_features():
    inputs = list(dataset_inputs(pd.date_range("2024-01-01", periods=20, freq="60D")))
    first = split_temporally(build_ml_dataset(*inputs), mode="chronological")
    assert [len(first.partitions[name]) for name in ("train", "validation", "test")] == [14, 3, 3]
    inputs[2]["Y"] = 1 - inputs[2]["Y"]
    inputs[1]["prior_return_5d"] = 1e8
    second = split_temporally(build_ml_dataset(*inputs), mode="chronological")
    assert first.boundaries == second.boundaries
    for name in first.partitions:
        assert first.partitions[name].equals(second.partitions[name])


def test_empty_validation_uses_configured_start_without_auto_fallback():
    inputs = dataset_inputs(["2024-12-01", "2026-02-01"], ["2025-01-01", "2026-03-20"])
    result = split_temporally(build_ml_dataset(*inputs))
    assert result.partitions["train"].empty and result.partitions["validation"].empty
    assert result.audit.loc["event:0", "exclusion_reasons"] == ["purged_outcome_overlap"]
    with pytest.raises(ValueError, match="three information dates"):
        split_temporally(build_ml_dataset(*inputs), mode="chronological")


def test_invalid_modes_and_boundaries():
    dataset = build_ml_dataset(*dataset_inputs())
    with pytest.raises(ValueError, match="mode"):
        split_temporally(dataset, mode="random")
    with pytest.raises(ValueError, match="strictly increasing"):
        split_temporally(dataset, boundaries={"train": "2025-01-01", "validation": "2024-01-01", "test": "2026-01-01", "end": "2027-01-01"})


def test_fallback_keeps_same_information_date_group_together():
    dates = ["2024-01-01"] * 8 + ["2024-06-01"] + ["2025-01-01"]
    inputs = list(dataset_inputs(dates))
    inputs[0]["ticker"] = [f"T{i}" for i in range(len(dates))]
    result = split_temporally(build_ml_dataset(*inputs), mode="chronological")
    assert result.audit.iloc[:8].partition.eq("train").all()
    assert result.audit.iloc[8].partition == "validation"
    assert result.audit.iloc[9].partition == "test"


def test_purge_uses_next_information_date_even_if_that_row_has_no_label():
    inputs = list(dataset_inputs(["2024-12-01", "2025-01-02", "2025-03-01", "2026-03-01"],
                                 ["2025-01-02", "2025-02-20", "2025-04-20", "2026-04-20"]))
    inputs[2].loc[1, "Y"] = None
    inputs[2].loc[1, "label_status"] = "unavailable"
    result = split_temporally(build_ml_dataset(*inputs))
    assert result.audit.loc["event:0", "exclusion_reasons"] == ["purged_outcome_overlap"]
    assert result.audit.loc["event:1", "exclusion_reasons"] == ["unavailable_label"]
