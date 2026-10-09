from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.ml.dataset import FEATURE_COLUMNS, FEATURE_GROUPS, build_ml_dataset, build_outperformance_labels


def label_fixture():
    sessions = pd.bdate_range("2024-01-02", periods=35)
    events = pd.DataFrame([{"research_event_id": "ABC:event", "ticker": "ABC", "information_date": sessions[0], "public_event_day": sessions[1]}])
    prices = pd.DataFrame([{"ticker": ticker, "date": day, "analysis_price": value}
                           for ticker, values in (("ABC", [100.] + [110.] * 29 + [132.] * 5), ("SPY", [100.] * 35))
                           for day, value in zip(sessions, values)])
    return events, prices, sessions


def dataset_inputs(dates=("2024-03-01",), endpoints=None):
    events = pd.DataFrame([{"research_event_id": f"event:{i}", "ticker": "ABC", "information_date": pd.Timestamp(day),
                            "public_event_day": pd.Timestamp(day) + pd.Timedelta(days=1)} for i, day in enumerate(dates)])
    features, labels, provenance = [], [], []
    for i, event in events.iterrows():
        identity = event.research_event_id
        features.append({"research_event_id": identity, **{name: 1. for name in FEATURE_COLUMNS}, "sector": "Technology", "role_bucket": "Director"})
        labels.append({"research_event_id": identity, "Y": i % 2, "label_status": "complete",
                       "outcome_end": pd.Timestamp(endpoints[i]) if endpoints else event.public_event_day + pd.Timedelta(days=42),
                       "observation_cutoff": pd.Timestamp("2030-01-01"), "missing_reasons": []})
        for group in FEATURE_GROUPS:
            provenance.append({"research_event_id": identity, "feature_group": group,
                               "source_date": event.information_date - pd.Timedelta(days=1 if group == "market" else 0),
                               "verified": True, "canonical_identity_verified": True})
    return events, pd.DataFrame(features), pd.DataFrame(labels), pd.DataFrame(provenance)


def test_compounding_includes_t0_t29_and_preceding_price():
    events, prices, sessions = label_fixture()
    row = build_outperformance_labels(events, prices, sessions, observation_cutoff=sessions[30]).iloc[0]
    assert row.Y == 1 and row.label_status == "complete"
    assert row.stock_return_30d == pytest.approx(1.1 * 1.2 - 1)
    assert row.spy_return_30d == 0 and row.outcome_end == sessions[30]
    prices.loc[(prices.ticker == "ABC") & (prices.date == sessions[31]), "analysis_price"] = 1e9
    assert build_outperformance_labels(events, prices, sessions, observation_cutoff=sessions[-1]).iloc[0].stock_return_30d == row.stock_return_30d


def test_ties_are_zero():
    events, prices, sessions = label_fixture()
    prices["analysis_price"] = 100.
    assert build_outperformance_labels(events, prices, sessions, observation_cutoff=sessions[30]).iloc[0].Y == 0


@pytest.mark.parametrize("ticker,index", [("ABC", 0), ("ABC", 5), ("SPY", 30)])
def test_missing_prices_do_not_bridge_sessions(ticker, index):
    events, prices, sessions = label_fixture()
    prices = prices.loc[~((prices.ticker == ticker) & (prices.date == sessions[index]))]
    row = build_outperformance_labels(events, prices, sessions, observation_cutoff=sessions[30]).iloc[0]
    assert pd.isna(row.Y) and pd.isna(row.stock_return_30d)
    assert any("missing_paired_return" in reason for reason in row.missing_reasons)


@pytest.mark.parametrize("value", [0, -1, np.inf, np.nan, "bad"])
def test_invalid_prices_are_unavailable(value):
    events, prices, sessions = label_fixture()
    prices["analysis_price"] = prices.analysis_price.astype(object)
    prices.loc[(prices.ticker == "ABC") & (prices.date == sessions[10]), "analysis_price"] = value
    assert pd.isna(build_outperformance_labels(events, prices, sessions, observation_cutoff=sessions[30]).iloc[0].Y)


def test_shared_missing_session_and_short_calendar():
    events, prices, sessions = label_fixture()
    missing = prices.loc[prices.date != sessions[10]]
    assert build_outperformance_labels(events, missing, sessions, observation_cutoff=sessions[30]).iloc[0].label_status == "unavailable"
    row = build_outperformance_labels(events, prices, sessions[:30], observation_cutoff=sessions[-1]).iloc[0]
    assert "insufficient_expected_session_coverage" in row.missing_reasons


def test_cutoff_preserves_null_label_until_endpoint():
    events, prices, sessions = label_fixture()
    row = build_outperformance_labels(events, prices, sessions, observation_cutoff=sessions[29]).iloc[0]
    assert pd.isna(row.Y) and row.outcome_end == sessions[30]
    assert row.missing_reasons == ["outcome_not_observed_by_cutoff"]


def test_price_key_validation():
    events, prices, sessions = label_fixture()
    with pytest.raises(ValueError, match="duplicate ticker/date"):
        build_outperformance_labels(events, pd.concat([prices, prices.iloc[:1]]), sessions, observation_cutoff=sessions[-1])
    prices["date"] = prices.date.astype(object)
    prices.loc[0, "date"] = "bad"
    with pytest.raises(ValueError, match="malformed"):
        build_outperformance_labels(events, prices, sessions, observation_cutoff=sessions[-1])


def test_dataset_preserves_missing_values_categories_and_deterministic_order():
    inputs = dataset_inputs(("2024-03-01", "2024-03-02"))
    inputs[1].loc[0, "prior_return_5d"] = np.nan
    result = build_ml_dataset(*inputs)
    assert result.metadata.index.tolist() == ["event:0", "event:1"]
    assert result.features.columns.tolist() == list(FEATURE_COLUMNS)
    assert pd.isna(result.features.loc["event:0", "prior_return_5d"])
    assert result.features.loc["event:1", "role_bucket"] == "Director"
    assert result.availability.loc["event:0", "prior_return_5d"] == ["missing_or_invalid_feature"]
    other = build_ml_dataset(*(frame.iloc[::-1] for frame in inputs))
    pd.testing.assert_frame_equal(result.features, other.features)
    pd.testing.assert_frame_equal(result.metadata, other.metadata)


@pytest.mark.parametrize("position", [0, 1, 2])
def test_duplicate_and_missing_ids(position):
    inputs = list(dataset_inputs())
    inputs[position] = pd.concat([inputs[position]] * 2)
    with pytest.raises(ValueError, match="duplicate"):
        build_ml_dataset(*inputs)
    inputs = list(dataset_inputs())
    inputs[position].loc[0, "research_event_id"] = None
    with pytest.raises(ValueError, match="non-null"):
        build_ml_dataset(*inputs)


@pytest.mark.parametrize("position", [1, 2, 3])
def test_unmatched_ids(position):
    inputs = list(dataset_inputs())
    inputs[position].loc[0, "research_event_id"] = "unknown"
    with pytest.raises(ValueError, match="unmatched"):
        build_ml_dataset(*inputs)


def test_missing_rows_and_inconsistent_labels_are_rejected():
    inputs = list(dataset_inputs())
    inputs[1] = inputs[1].iloc[:0]
    with pytest.raises(ValueError, match="missing rows"):
        build_ml_dataset(*inputs)
    inputs = list(dataset_inputs())
    inputs[2].loc[0, "label_status"] = "unavailable"
    with pytest.raises(ValueError, match="contradict"):
        build_ml_dataset(*inputs)


def test_buyer_features_require_verified_canonical_identity():
    inputs = list(dataset_inputs())
    inputs[3].loc[inputs[3].feature_group == "buyers", "canonical_identity_verified"] = False
    result = build_ml_dataset(*inputs)
    assert result.features.loc["event:0", ["unique_buyers_7d", "unique_buyers_30d"]].isna().all()
    assert "canonical_buyer_identity_unverified" in result.availability.loc["event:0", "unique_buyers_7d"]
    assert result.targets.loc["event:0", "Y"] == 0
    assert build_ml_dataset(*dataset_inputs()).features.loc["event:0", "unique_buyers_7d"] == 1


def test_empty_label_events_preserve_output_schema():
    events, prices, sessions = label_fixture()
    result = build_outperformance_labels(events.iloc[:0], prices, sessions, observation_cutoff=sessions[-1])
    assert result.empty and "Y" in result


def test_equal_compounded_endpoint_returns_remain_ties_with_different_paths():
    events, prices, sessions = label_fixture()
    mask = prices.ticker == "SPY"
    prices.loc[mask, "analysis_price"] = np.linspace(100., 132., 35)
    prices.loc[mask & (prices.date == sessions[30]), "analysis_price"] = 132.
    row = build_outperformance_labels(events, prices, sessions, observation_cutoff=sessions[30]).iloc[0]
    assert row.stock_return_30d == row.spy_return_30d
    assert row.Y == 0


def test_public_event_day_must_be_first_supplied_session_after_information_date():
    events, prices, sessions = label_fixture()
    events.loc[0, "public_event_day"] = sessions[2]
    row = build_outperformance_labels(events, prices, sessions, observation_cutoff=sessions[-1]).iloc[0]
    assert row.label_status == "unavailable"
    assert "public_event_day_is_not_first_session_after_information_date" in row.missing_reasons


def test_duplicate_provenance_group_is_rejected():
    inputs = list(dataset_inputs())
    inputs[3] = pd.concat([inputs[3], inputs[3].iloc[:1]])
    with pytest.raises(ValueError, match="duplicate event/feature_group"):
        build_ml_dataset(*inputs)


def test_complete_label_with_missing_data_reasons_is_rejected():
    inputs = list(dataset_inputs())
    inputs[2].at[0, "missing_reasons"] = ["missing_session"]
    with pytest.raises(ValueError, match="contradict"):
        build_ml_dataset(*inputs)


def test_nonfinite_predictor_becomes_missing_with_a_reason():
    inputs = list(dataset_inputs())
    inputs[1].loc[0, "prior_return_5d"] = np.inf
    result = build_ml_dataset(*inputs)
    assert pd.isna(result.features.loc["event:0", "prior_return_5d"])
    assert result.availability.loc["event:0", "prior_return_5d"] == ["missing_or_invalid_feature"]


def test_empty_assembled_dataset_can_be_split():
    from app.ml.dataset import split_temporally

    inputs = tuple(frame.iloc[:0] for frame in dataset_inputs())
    dataset = build_ml_dataset(*inputs)
    result = split_temporally(dataset)
    assert dataset.features.empty and result.audit.empty
    assert result.summary.sample_count.sum() == 0
