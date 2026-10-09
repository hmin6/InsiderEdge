from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from scipy.stats import chi2

from app.quant.anomaly import (
    ANOMALY_FEATURES,
    MIN_ANOMALY_REFERENCE,
    build_anomaly_scores,
    ordinary_z_score,
)


BASE_FEATURES = {
    "log_aggregate_purchase_value": 10.0,
    "prior_return_30d": 0.0,
    "prior_volatility_30d": 0.02,
    "drawdown_90d": -0.1,
}


def make_frames(
    vectors: list[dict[str, float | None]],
    *,
    tickers: list[str] | None = None,
    sectors: dict[str, str] | None = None,
    start: date = date(2025, 1, 1),
    raw_aggregates: list[float | None] | None = None,
):
    tickers = tickers or ["AAA"] * len(vectors)
    sectors = sectors or {ticker: "Technology" for ticker in set(tickers)}
    events = pd.DataFrame([
        {
            "research_event_id": f"{ticker}:{(start + timedelta(days=i)).isoformat()}",
            "ticker": ticker,
            "information_date": start + timedelta(days=i),
            "public_event_day": start + timedelta(days=i + 1),
        }
        for i, ticker in enumerate(tickers)
    ])
    feature_rows = []
    activity_rows = []
    for i, (event, vector) in enumerate(zip(events.to_dict("records"), vectors)):
        row = {"research_event_id": event["research_event_id"], **BASE_FEATURES}
        row.update({key: value for key, value in vector.items() if key != "buyers_30d"})
        if raw_aggregates is not None:
            row["aggregate_purchase_value"] = raw_aggregates[i]
        feature_rows.append(row)
        activity_rows.append({
            "research_event_id": event["research_event_id"],
            "buyers_30d": vector.get("buyers_30d", 2.0),
        })
    companies = pd.DataFrame([
        {"ticker": ticker, "sector": sectors[ticker]}
        for ticker in sorted(set(tickers))
    ])
    return events, pd.DataFrame(feature_rows), pd.DataFrame(activity_rows), companies


def constant_history(n: int, current: dict[str, float | None] | None = None):
    vectors = [{"buyers_30d": 2.0} for _ in range(n)]
    if current is not None:
        vectors.append({"buyers_30d": 2.0, **current})
    return vectors


def score_last(frames):
    result = build_anomaly_scores(*frames)
    return result, result.iloc[-1]


def test_center_point_has_zero_mahalanobis_distance_and_score():
    _, current = score_last(make_frames(constant_history(MIN_ANOMALY_REFERENCE, {})))
    assert current["status"] == "complete"
    assert current["D2"] == pytest.approx(0.0)
    assert current["D"] == pytest.approx(0.0)
    assert current["A"] == pytest.approx(0.0)
    assert current["feature_count"] == 5
    assert current["required_feature_count"] == 5
    assert current["required_features"] == list(ANOMALY_FEATURES)
    assert current["features_used"] == list(ANOMALY_FEATURES)


def test_extreme_point_has_larger_anomaly_score_and_score_is_bounded():
    center = make_frames(constant_history(MIN_ANOMALY_REFERENCE, {}))
    extreme_vector = {
        "log_aggregate_purchase_value": 12.0,
        "buyers_30d": 20.0,
        "prior_return_30d": 0.5,
        "prior_volatility_30d": 0.20,
        "drawdown_90d": -0.8,
    }
    extreme = make_frames(constant_history(MIN_ANOMALY_REFERENCE, extreme_vector))
    _, center_score = score_last(center)
    _, extreme_score = score_last(extreme)
    assert extreme_score["A"] > center_score["A"]
    assert 0 <= extreme_score["A"] <= 100
    assert np.isfinite(extreme_score["D2"])


def test_covariance_aware_distance_respects_correlated_dimensions():
    from app.quant.anomaly import _distance_and_score

    t = np.linspace(-1.0, 1.0, MIN_ANOMALY_REFERENCE)
    reference = np.column_stack((10 + t, 20 + 2 * t, t * 0, t * 0 + 0.02, t * 0 - 0.1))
    along_correlation = np.array([10.5, 21.0, 0.0, 0.02, -0.1])
    orthogonal_to_correlation = np.array([10.5, 20.0, 0.0, 0.02, -0.1])
    along = _distance_and_score(reference, along_correlation)
    orthogonal = _distance_and_score(reference, orthogonal_to_correlation)
    assert along["status"] == orthogonal["status"] == "complete"
    assert orthogonal["D2"] > along["D2"]
    assert orthogonal["A"] > along["A"]


def test_hand_checkable_distance_and_chi_square_calibration_use_five_dimensions():
    center = np.array([10.0, 10.0, 0.0, 0.10, -0.20])
    variances = np.array([1.0, 1.0, 0.0004, 0.0004, 0.0004])
    amplitudes = np.sqrt(29.0 * variances / 6.0)
    reference_vectors = []
    for dimension, amplitude in enumerate(amplitudes):
        for _ in range(3):
            positive = center.copy()
            negative = center.copy()
            positive[dimension] += amplitude
            negative[dimension] -= amplitude
            reference_vectors.extend((positive, negative))
    # Six symmetric observations per dimension make the sample covariance
    # diagonal with the listed variances (n=30 and ddof=1).
    reference = np.vstack(reference_vectors)
    feature_rows = []
    activity_rows = []
    start = date(2025, 1, 1)
    for index, vector in enumerate(reference):
        event_id = f"AAA:{index}"
        feature_rows.append({
            "research_event_id": event_id,
            "log_aggregate_purchase_value": vector[0],
            "prior_return_30d": vector[2],
            "prior_volatility_30d": vector[3],
            "drawdown_90d": vector[4],
        })
        activity_rows.append({"research_event_id": event_id, "buyers_30d": vector[1]})
    current_vector = center.copy()
    current_vector[0] += 2.0
    current_id = "AAA:current"
    feature_rows.append({
        "research_event_id": current_id,
        "log_aggregate_purchase_value": current_vector[0],
        "prior_return_30d": current_vector[2],
        "prior_volatility_30d": current_vector[3],
        "drawdown_90d": current_vector[4],
    })
    activity_rows.append({"research_event_id": current_id, "buyers_30d": current_vector[1]})
    events = pd.DataFrame([
        {
            "research_event_id": row["research_event_id"],
            "ticker": "AAA",
            "information_date": start + timedelta(days=index),
        }
        for index, row in enumerate(feature_rows)
    ])

    result = build_anomaly_scores(
        events,
        pd.DataFrame(feature_rows),
        pd.DataFrame(activity_rows),
        pd.DataFrame([{"ticker": "AAA", "sector": "Technology"}]),
    )
    current = result.loc[result["research_event_id"].eq(current_id)].iloc[0]
    # Covariance is diag(variances); the implementation adds ridge=1e-8,
    # therefore this displacement's D² is 2² / (1 + 1e-8).
    expected_d2 = 4.0 / (1.0 + 1e-8)
    assert current["status"] == "complete"
    assert current["D2"] == pytest.approx(expected_d2, rel=1e-8)
    assert current["D"] == pytest.approx(np.sqrt(expected_d2), rel=1e-8)
    assert current["feature_count"] == 5
    assert current["features_used"] == list(ANOMALY_FEATURES)
    assert current["A"] == pytest.approx(100.0 * chi2.cdf(current["D2"], df=5), rel=1e-12)
    assert abs(current["A"] - 100.0 * chi2.cdf(current["D2"], df=4)) > 1.0


def test_singular_covariance_is_regularized_and_returns_finite_result():
    frames = make_frames(constant_history(MIN_ANOMALY_REFERENCE, {
        "log_aggregate_purchase_value": 11.0,
        "buyers_30d": 4.0,
    }))
    _, result = score_last(frames)
    assert result["status"] == "complete"
    assert result["covariance_regularized"] is True
    assert result["covariance_ridge"] > 0
    assert np.isfinite(result["D2"])
    assert np.isfinite(result["D"])
    assert np.isfinite(result["A"])


def test_insufficient_sector_history_falls_back_to_prior_sp100_history():
    n_tech, n_other = 5, MIN_ANOMALY_REFERENCE
    tickers = ["AAA"] * n_tech + ["BBB"] * n_other + ["AAA"]
    vectors = [{"buyers_30d": 2.0} for _ in tickers]
    frames = make_frames(
        vectors,
        tickers=tickers,
        sectors={"AAA": "Technology", "BBB": "Financials"},
    )
    _, current = score_last(frames)
    assert current["status"] == "complete"
    assert current["reference_rule"] == "sp100"
    assert current["reference_sample_size"] == n_tech + n_other


def test_insufficient_history_is_explicit():
    _, current = score_last(make_frames(constant_history(MIN_ANOMALY_REFERENCE - 1, {})))
    assert current["status"] == "insufficient_data"
    assert current["A"] is None
    assert current["reference_rule"] == "sp100"
    assert current["reference_sample_size"] == MIN_ANOMALY_REFERENCE - 1
    assert "insufficient_usable_reference_history" in current["missing_reasons"]


def test_future_events_do_not_change_earlier_score_or_reference_population():
    base = make_frames(constant_history(MIN_ANOMALY_REFERENCE, {
        "log_aggregate_purchase_value": 10.5,
    }))
    base_result, base_current = score_last(base)
    # Construct later rows explicitly to preserve original IDs and append dates
    # after the scored event without changing any earlier input.
    extra_events = pd.DataFrame([
        {"research_event_id": f"AAA:future:{i}", "ticker": "AAA", "information_date": date(2025, 3, 1) + timedelta(days=i)}
        for i in range(3)
    ])
    events = pd.concat([base[0], extra_events], ignore_index=True)
    extra_features = pd.DataFrame([
        {"research_event_id": event["research_event_id"], **BASE_FEATURES,
         "log_aggregate_purchase_value": 30.0 + i}
        for i, event in enumerate(extra_events.to_dict("records"))
    ])
    extra_activity = pd.DataFrame([
        {"research_event_id": event["research_event_id"], "buyers_30d": 100 + i}
        for i, event in enumerate(extra_events.to_dict("records"))
    ])
    extended = (
        events,
        pd.concat([base[1], extra_features], ignore_index=True),
        pd.concat([base[2], extra_activity], ignore_index=True),
        base[3],
    )
    extended_result = build_anomaly_scores(*extended)
    extended_current = extended_result.loc[
        extended_result["research_event_id"].eq(base_current["research_event_id"])
    ].iloc[0]
    assert extended_current["A"] == pytest.approx(base_current["A"])
    assert extended_current["D2"] == pytest.approx(base_current["D2"])
    assert extended_current["reference_rule"] == base_current["reference_rule"]
    assert extended_current["reference_sample_size"] == base_current["reference_sample_size"]
    assert len(base_result) == len(base[0])


def test_missing_dimensions_are_not_silently_dropped_and_reduce_reference_size():
    vectors = constant_history(MIN_ANOMALY_REFERENCE, {})
    vectors[0]["prior_return_30d"] = None
    vectors[-1] = {"buyers_30d": None}
    _, current = score_last(make_frames(vectors))
    assert current["status"] == "missing_features"
    assert current["A"] is None
    assert current["feature_count"] is None
    assert current["required_feature_count"] == 5
    assert current["required_features"] == list(ANOMALY_FEATURES)
    assert current["features_used"] == []
    assert current["missing_features"] == ["buyers_30d"]
    assert current["reference_sample_size"] == MIN_ANOMALY_REFERENCE - 1


def test_nonpositive_raw_transaction_value_invalidates_log_feature():
    values = [100.0] * (MIN_ANOMALY_REFERENCE + 1)
    values[-1] = 0.0
    vectors = constant_history(MIN_ANOMALY_REFERENCE, {})
    frames = make_frames(vectors, raw_aggregates=values)
    # Deliberately contradictory log: the raw zero must remain unavailable.
    frames[1].loc[frames[1].index[-1], "log_aggregate_purchase_value"] = 5.0
    _, current = score_last(frames)
    assert current["status"] == "missing_features"
    assert current["missing_features"] == ["log_aggregate_purchase_value"]


def test_z_score_and_zero_variance_behavior():
    assert ordinary_z_score(4, [1, 2, 3]) == pytest.approx(2.0)
    assert ordinary_z_score(1, [1, 1, 1]) is None
    assert ordinary_z_score(1, [1]) is None
    assert ordinary_z_score(float("nan"), [1, 2, 3]) is None


def test_duplicate_event_feature_or_activity_rows_are_rejected():
    frames = make_frames(constant_history(MIN_ANOMALY_REFERENCE, {}))
    duplicated = pd.concat([frames[1], frames[1].iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="at most one row"):
        build_anomaly_scores(frames[0], duplicated, frames[2], frames[3])


@pytest.mark.parametrize("input_index,input_name", [(1, "event_features"), (2, "activity_scores")])
def test_unmatched_input_event_ids_are_rejected(input_index, input_name):
    frames = list(make_frames(constant_history(MIN_ANOMALY_REFERENCE, {})))
    extra = frames[input_index].iloc[[0]].copy()
    extra.loc[:, "research_event_id"] = "orphan-event"
    frames[input_index] = pd.concat([frames[input_index], extra], ignore_index=True)
    with pytest.raises(ValueError, match=rf"{input_name} contains research_event_id.*orphan-event"):
        build_anomaly_scores(*frames)
