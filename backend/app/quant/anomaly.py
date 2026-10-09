"""Leakage-aware Mahalanobis anomaly score (A).

The initial vector has five dimensions: log aggregate purchase value (natural
log of currency units), unique buyers in the prior/current 30 calendar days
(count), prior 30-session stock return (decimal), prior 30-session volatility
(sample standard deviation of simple returns, decimal), and 90-session
drawdown (decimal, zero or negative). Callers pass the outputs of event
feature engineering and activity scoring; raw transactions are not expanded
into additional event rows here.

For each event, only complete feature vectors with strictly earlier
information dates can enter the reference population. Same-sector history is
preferred; if it has fewer than ``MIN_ANOMALY_REFERENCE`` usable rows, the
function falls back to all earlier events for tickers present in ``companies``
(the frozen project S&P 100 universe). The chi-square calibration assumes the
reference vectors are approximately multivariate normal. A deterministic
diagonal ridge regularization stabilizes singular/near-singular covariance.

MODEL_SPEC.md does not define partial-vector behavior. This component
conservatively requires all five values for both the scored event and each
reference event, never silently changing the dimension count.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import chi2


MIN_ANOMALY_REFERENCE = 30
ANOMALY_FEATURES = (
    "log_aggregate_purchase_value",
    "buyers_30d",
    "prior_return_30d",
    "prior_volatility_30d",
    "drawdown_90d",
)
_RIDGE_RELATIVE = 1e-8


def _dates(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, errors="coerce").dt.normalize()


def _finite_number(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if np.isfinite(number) else None


def ordinary_z_score(value: object, reference_values: Sequence[object]) -> float | None:
    """Return a sample-standardized z-score, or ``None`` when undefined.

    Invalid reference values are excluded. At least two finite reference
    observations and nonzero sample standard deviation are required. The
    sample mean and standard deviation are calculated only from the supplied
    reference population; callers are responsible for supplying a
    leakage-safe population.
    """
    observed = _finite_number(value)
    reference = np.asarray(
        [number for item in reference_values if (number := _finite_number(item)) is not None],
        dtype=float,
    )
    if observed is None or len(reference) < 2:
        return None
    scale = float(np.std(reference, ddof=1))
    if not np.isfinite(scale) or scale == 0:
        return None
    score = (observed - float(np.mean(reference))) / scale
    return float(score) if np.isfinite(score) else None


def _prepare_inputs(
    research_events: pd.DataFrame,
    event_features: pd.DataFrame,
    activity_scores: pd.DataFrame,
    companies: pd.DataFrame,
) -> tuple[pd.DataFrame, set[str]]:
    required_events = {"research_event_id", "ticker", "information_date"}
    required_companies = {"ticker", "sector"}
    if not required_events.issubset(research_events.columns):
        raise ValueError(f"research_events missing {sorted(required_events - set(research_events.columns))}")
    if not required_companies.issubset(companies.columns):
        raise ValueError(f"companies missing {sorted(required_companies - set(companies.columns))}")
    if "research_event_id" not in event_features:
        raise ValueError("event_features must include research_event_id")
    if "research_event_id" not in activity_scores:
        raise ValueError("activity_scores must include research_event_id")
    if research_events["research_event_id"].duplicated().any():
        raise ValueError("research_events must contain unique research_event_id values")
    if event_features["research_event_id"].duplicated().any():
        raise ValueError("event_features must contain at most one row per research_event_id")
    if activity_scores["research_event_id"].duplicated().any():
        raise ValueError("activity_scores must contain at most one row per research_event_id")

    event_ids = research_events["research_event_id"]
    for input_name, frame in (
        ("event_features", event_features),
        ("activity_scores", activity_scores),
    ):
        unmatched_ids = frame.loc[~frame["research_event_id"].isin(event_ids), "research_event_id"]
        if not unmatched_ids.empty:
            examples = unmatched_ids.drop_duplicates().head(5).tolist()
            raise ValueError(
                f"{input_name} contains research_event_id values not present in research_events: {examples}"
            )

    events = research_events[["research_event_id", "ticker", "information_date"]].copy()
    events["ticker"] = events["ticker"].astype("string").str.strip().str.upper()
    events["information_date"] = _dates(events["information_date"])

    company_rows = companies[["ticker", "sector"]].copy()
    company_rows["ticker"] = company_rows["ticker"].astype("string").str.strip().str.upper()
    if company_rows["ticker"].dropna().duplicated().any():
        raise ValueError("companies must contain one row per ticker")
    sector_map = company_rows.set_index("ticker")["sector"].to_dict()
    events["sector"] = events["ticker"].map(sector_map)

    feature_columns = [name for name in ("research_event_id", *ANOMALY_FEATURES) if name in event_features]
    activity_columns = [name for name in ("research_event_id", "buyers_30d") if name in activity_scores]
    events = events.merge(event_features[feature_columns], on="research_event_id", how="left", validate="one_to_one")
    events = events.merge(activity_scores[activity_columns], on="research_event_id", how="left", validate="one_to_one")

    # If raw aggregate value accompanies the precomputed log, enforce the
    # feature builder's nonpositive-value behavior rather than trusting a
    # contradictory log value.
    if "aggregate_purchase_value" in event_features:
        raw_values = event_features.set_index("research_event_id")["aggregate_purchase_value"]
        raw_for_event = events["research_event_id"].map(raw_values)
        invalid_aggregate = raw_for_event.map(lambda value: (n := _finite_number(value)) is None or n <= 0)
        events.loc[invalid_aggregate, "log_aggregate_purchase_value"] = np.nan

    universe = set(company_rows["ticker"].dropna().astype(str))
    return events, universe


def _row_vector(row: pd.Series) -> tuple[np.ndarray | None, list[str]]:
    values: list[float] = []
    missing: list[str] = []
    for feature in ANOMALY_FEATURES:
        value = _finite_number(row.get(feature))
        if value is None:
            missing.append(feature)
        else:
            values.append(value)
    return (np.asarray(values, dtype=float) if not missing else None), missing


def _distance_and_score(reference: np.ndarray, current: np.ndarray) -> dict[str, Any]:
    if reference.ndim != 2 or reference.shape[1] != len(ANOMALY_FEATURES) or len(reference) < 2:
        return {"status": "invalid_reference", "missing_reasons": ["invalid_reference_matrix"]}
    if not np.isfinite(reference).all() or not np.isfinite(current).all():
        return {"status": "invalid_features", "missing_reasons": ["nonfinite_feature_value"]}

    mean = reference.mean(axis=0)
    covariance = np.cov(reference, rowvar=False, ddof=1)
    if covariance.shape != (len(ANOMALY_FEATURES), len(ANOMALY_FEATURES)) or not np.isfinite(covariance).all():
        return {"status": "invalid_covariance", "missing_reasons": ["invalid_covariance"]}
    covariance = (covariance + covariance.T) / 2.0
    ridge = _RIDGE_RELATIVE * max(float(np.max(np.diag(covariance))), 1.0)
    regularized_covariance = covariance + np.eye(len(ANOMALY_FEATURES)) * ridge
    try:
        delta = current - mean
        solved = np.linalg.solve(regularized_covariance, delta)
        d2 = float(delta @ solved)
    except (np.linalg.LinAlgError, FloatingPointError, ValueError):
        return {"status": "invalid_covariance", "missing_reasons": ["covariance_solve_failed"]}
    if not np.isfinite(d2):
        return {"status": "invalid_distance", "missing_reasons": ["nonfinite_mahalanobis_distance"]}
    if d2 < -1e-10:
        return {"status": "invalid_distance", "missing_reasons": ["negative_mahalanobis_squared_distance"]}
    d2 = max(d2, 0.0)
    distance = float(np.sqrt(d2))
    score = float(100.0 * chi2.cdf(d2, df=len(ANOMALY_FEATURES)))
    if not np.isfinite(score) or not np.isfinite(distance):
        return {"status": "invalid_distance", "missing_reasons": ["nonfinite_anomaly_score"]}
    return {
        "D2": d2,
        "D": distance,
        "A": min(100.0, max(0.0, score)),
        "feature_count": len(ANOMALY_FEATURES),
        "required_features": list(ANOMALY_FEATURES),
        "features_used": list(ANOMALY_FEATURES),
        "covariance_regularized": bool(ridge > 0),
        "covariance_ridge": ridge,
        "status": "complete",
        "missing_reasons": [],
    }


def build_anomaly_scores(
    research_events: pd.DataFrame,
    event_features: pd.DataFrame,
    activity_scores: pd.DataFrame,
    companies: pd.DataFrame,
) -> pd.DataFrame:
    """Return one leakage-safe anomaly result for each research event.

    ``event_features`` is the output of ``build_event_features`` and supplies
    the log-value and market dimensions. ``activity_scores`` is the output of
    ``build_activity_scores`` and supplies ``buyers_30d``. ``companies`` is
    the frozen S&P 100 ticker/sector table. Raw transactions are not input and
    are never treated as independent anomaly observations. ``required_features``
    always lists the locked five dimensions; ``feature_count`` and
    ``features_used`` describe successful calculations only and are ``None``
    and empty, respectively, when no score is available.
    """
    events, universe = _prepare_inputs(research_events, event_features, activity_scores, companies)
    vectors: list[np.ndarray | None] = []
    missing_features: list[list[str]] = []
    for _, row in events.iterrows():
        vector, missing = _row_vector(row)
        vectors.append(vector)
        missing_features.append(missing)
    events["_vector"] = vectors
    events["_missing_features"] = missing_features

    output: list[dict[str, Any]] = []
    for _, current in events.iterrows():
        information_date = current["information_date"]
        ticker = current["ticker"]
        prior = events.loc[
            events["information_date"].lt(information_date)
            & events["ticker"].isin(universe)
            & events["_vector"].map(lambda vector: vector is not None)
        ] if pd.notna(information_date) else events.iloc[0:0]

        sector = current["sector"]
        sector_valid = sector is not None and not pd.isna(sector) and bool(str(sector).strip())
        sector_reference = prior.loc[prior["sector"].eq(sector)] if sector_valid else prior.iloc[0:0]
        if len(sector_reference) >= MIN_ANOMALY_REFERENCE:
            reference_rule = "sector"
            reference = sector_reference
        else:
            reference_rule = "sp100"
            reference = prior

        reference_matrix = (
            np.vstack(reference["_vector"].tolist())
            if len(reference)
            else np.empty((0, len(ANOMALY_FEATURES)), dtype=float)
        )
        vector, missing = current["_vector"], current["_missing_features"]
        base: dict[str, Any] = {
            "research_event_id": current["research_event_id"],
            "ticker": ticker,
            "information_date": information_date,
            "reference_rule": reference_rule,
            "reference_sample_size": int(len(reference)),
            "required_feature_count": len(ANOMALY_FEATURES),
            "required_features": list(ANOMALY_FEATURES),
            "feature_count": None,
            "features_used": [],
            "missing_features": list(missing),
            "D2": None,
            "D": None,
            "A": None,
            "covariance_regularized": None,
            "covariance_ridge": None,
            "missing_reasons": [],
        }
        if pd.isna(information_date):
            base["status"] = "missing_information_date"
            base["missing_reasons"] = ["missing_information_date"]
        elif pd.isna(ticker) or str(ticker).strip() not in universe:
            base["status"] = "missing_company_metadata"
            base["missing_reasons"] = ["ticker_not_in_sp100_universe"]
        elif missing:
            base["status"] = "missing_features"
            base["missing_reasons"] = [f"missing_feature:{name}" for name in missing]
        elif len(reference) < MIN_ANOMALY_REFERENCE:
            base["status"] = "insufficient_data"
            base["missing_reasons"] = ["insufficient_usable_reference_history"]
        else:
            calculated = _distance_and_score(reference_matrix, vector)
            if calculated["status"] == "complete":
                for key in (
                    "D2",
                    "D",
                    "A",
                    "feature_count",
                    "required_features",
                    "features_used",
                    "covariance_regularized",
                    "covariance_ridge",
                ):
                    base[key] = calculated[key]
            base["status"] = calculated["status"]
            base["missing_reasons"] = calculated["missing_reasons"]
        output.append(base)
    return pd.DataFrame(output)


ANOMALY_FEATURE_DEFINITIONS: Mapping[str, str] = {
    "log_aggregate_purchase_value": "Natural log of aggregate qualifying transaction value in currency units; null for missing or nonpositive aggregate value.",
    "buyers_30d": "Unique canonical insider buyers in the inclusive prior/current 30 calendar-day window; count; null when identity coverage is unavailable.",
    "prior_return_30d": "Simple return across 30 completed trading intervals ending strictly before information_date; decimal.",
    "prior_volatility_30d": "Sample standard deviation of 30 simple daily returns ending strictly before information_date; decimal.",
    "drawdown_90d": "Last pre-information-date analysis_price divided by trailing 90-session peak minus one; decimal (zero or negative).",
}
