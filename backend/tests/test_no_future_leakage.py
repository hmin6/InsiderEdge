import pandas as pd
import pytest

from app.ml.dataset import build_ml_dataset, build_outperformance_labels
from test_ml_dataset import dataset_inputs, label_fixture


def test_forbidden_column_injection_cannot_enter_predictors():
    inputs = list(dataset_inputs())
    forbidden = {"Y", "car30", "anomaly_score", "activity_score", "statistical_score", "dislocation_score", "insider_edge_score", "ticker", "cik", "insider_name"}
    for name in forbidden:
        inputs[1][name] = 999
    result = build_ml_dataset(*inputs)
    assert not (forbidden | {"research_event_id"}).intersection(result.features.columns)


@pytest.mark.parametrize("group,offset", [("market", 0), ("market", 1), ("insider", 1), ("buyers", 1), ("categories", 1)])
def test_future_sources_rejected_even_with_unverified_provenance(group, offset):
    inputs = list(dataset_inputs())
    mask = inputs[3].feature_group.eq(group)
    inputs[3].loc[mask, "source_date"] = inputs[0].loc[0, "information_date"] + pd.Timedelta(days=offset)
    inputs[3].loc[mask, "verified"] = False
    with pytest.raises(ValueError, match="future feature"):
        build_ml_dataset(*inputs)


@pytest.mark.parametrize("case", ["absent", "unverified", "missing_date"])
def test_missing_provenance_masks_features(case):
    inputs = list(dataset_inputs())
    mask = inputs[3].feature_group.eq("market")
    if case == "absent":
        inputs[3] = inputs[3].loc[~mask]
    elif case == "unverified":
        inputs[3].loc[mask, "verified"] = False
    else:
        inputs[3].loc[mask, "source_date"] = pd.NaT
    result = build_ml_dataset(*inputs)
    assert pd.isna(result.features.loc["event:0", "prior_return_5d"])
    assert "missing_or_unverified_provenance" in result.availability.loc["event:0", "prior_return_5d"]


def test_future_prices_change_eventual_label_without_changing_features():
    events, prices, sessions = label_fixture()
    _, features, _, provenance = dataset_inputs((str(sessions[0].date()),))
    features["research_event_id"] = "ABC:event"
    provenance["research_event_id"] = "ABC:event"
    original = build_outperformance_labels(events, prices, sessions, observation_cutoff=sessions[30])
    future = prices.copy()
    future.loc[(future.ticker == "ABC") & (future.date == sessions[30]), "analysis_price"] = 50.
    changed = build_outperformance_labels(events, future, sessions, observation_cutoff=sessions[30])
    assert original.iloc[0].Y == 1 and changed.iloc[0].Y == 0
    before = build_ml_dataset(events, features, original, provenance)
    after = build_ml_dataset(events, features, changed, provenance)
    pd.testing.assert_frame_equal(before.features, after.features)
    early = build_outperformance_labels(events, prices, sessions, observation_cutoff=sessions[29])
    early_changed = build_outperformance_labels(events, future, sessions, observation_cutoff=sessions[29])
    pd.testing.assert_frame_equal(early, early_changed)
