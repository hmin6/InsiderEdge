"""Comparable-event bootstrap and randomized-timing validation.

Inputs are company-level research events, their market-model event-study rows,
company sector metadata, supplied adjustment-aware prices, and an independently
sourced expected-session index. The module does not fetch, persist, or infer
market data. Historical comparators require public information before the
focal event and a complete CAR30 window ending strictly before the focal
information date. Pseudo-event dates use the same ticker and calendar year,
exclude actual insider-event days, and must also finish their complete CAR30
window before the focal information date.

Bootstrap observations are company-event CAR30 values. Randomization draws one
pseudo day independently for each selected event, with replacement; overlapping
windows are permitted. Incomplete draws are rejected. A fixed attempt cap keeps
the run bounded, and every requested valid replicate is required for a p-value.
Seed defaults are deterministic (13 for both components) and are included with
replicate diagnostics.

Output is one row per focal ``research_event_id``. Return/CAR quantities and
confidence bounds are decimal returns; p-values are in [0, 1], and support
scores are on [0, 100]. The row reports the chosen cohort/count, mean CAR30,
bootstrap interval and seed/count, randomization ``T_obs``, corrected p-value,
support, seed, requested/attempted/valid replicate counts, and component
statuses/reasons. Unavailable numeric results are null; overall status is
``complete``, ``partial``, or ``insufficient_data``. The final score is
``0.5 * B_support + 0.5 * P_support`` and remains null if either support is
unavailable.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from app.quant.event_study import build_event_studies


MIN_COMPARABLE_EVENTS = 10
DEFAULT_BOOTSTRAP_RESAMPLES = 1_000
DEFAULT_RANDOMIZATION_REPLICATES = 1_000
DEFAULT_BOOTSTRAP_SEED = 13
DEFAULT_RANDOMIZATION_SEED = 13
DEFAULT_RANDOMIZATION_ATTEMPT_MULTIPLIER = 10


def _dates(values: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(values, errors="coerce", format="mixed")
    try:
        if parsed.dt.tz is not None:
            parsed = parsed.dt.tz_localize(None)
    except (AttributeError, TypeError):
        pass
    return parsed.dt.normalize()


def _expected_sessions(values: pd.Series | pd.Index | Sequence[object]) -> list[pd.Timestamp]:
    if isinstance(values, (str, bytes)):
        raise ValueError("expected_sessions must be an ordered sequence of dates")
    try:
        sessions = _dates(pd.Series(values))
    except (TypeError, ValueError) as exc:
        raise ValueError("expected_sessions must be an ordered sequence of dates") from exc
    if sessions.empty or sessions.isna().any():
        raise ValueError("expected_sessions must contain valid dates")
    if sessions.duplicated().any():
        raise ValueError("expected_sessions must contain unique dates")
    if not sessions.is_monotonic_increasing:
        raise ValueError("expected_sessions must be in chronological order")
    return sessions.tolist()


def _finite_number(value: object) -> float | None:
    if value is None:
        return None
    try:
        missing = pd.isna(value)
        if isinstance(missing, (bool, np.bool_)) and missing:
            return None
        if not isinstance(missing, (bool, np.bool_)):
            return None
    except (TypeError, ValueError):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if np.isfinite(number) else None


def _prepare_inputs(
    research_events: pd.DataFrame,
    event_studies: pd.DataFrame,
    companies: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[object, dict[str, Any]]]:
    event_columns = {
        "research_event_id", "ticker", "public_event_day", "information_date", "role_bucket",
    }
    study_columns = {"research_event_id", "car30", "car30_status"}
    company_columns = {"ticker", "sector"}
    for name, frame, required in (
        ("research_events", research_events, event_columns),
        ("event_studies", event_studies, study_columns),
        ("companies", companies, company_columns),
    ):
        if not required.issubset(frame.columns):
            raise ValueError(f"{name} missing required columns: {sorted(required - set(frame.columns))}")
    for name, frame in (("research_events", research_events), ("event_studies", event_studies)):
        if frame["research_event_id"].isna().any() or frame["research_event_id"].duplicated().any():
            raise ValueError(f"{name} must contain unique, non-null research_event_id values")

    events = research_events[
        ["research_event_id", "ticker", "public_event_day", "information_date", "role_bucket"]
    ].copy()
    events["ticker"] = events["ticker"].astype("string").str.strip().str.upper()
    events["public_event_day"] = _dates(events["public_event_day"])
    events["information_date"] = _dates(events["information_date"])
    events["role_key"] = events["role_bucket"].astype("string").str.strip().str.casefold()

    company_rows = companies[["ticker", "sector"]].copy()
    company_rows["ticker"] = company_rows["ticker"].astype("string").str.strip().str.upper()
    if company_rows["ticker"].isna().any() or company_rows["ticker"].eq("").any():
        raise ValueError("companies must contain non-empty ticker values")
    if company_rows["ticker"].duplicated().any():
        raise ValueError("companies must contain one row per ticker")
    company_rows["sector_key"] = company_rows["sector"].astype("string").str.strip().str.casefold()
    sector_by_ticker = company_rows.set_index("ticker")["sector_key"].to_dict()
    events["sector_key"] = events["ticker"].map(sector_by_ticker)

    event_ids = set(events["research_event_id"])
    unmatched = event_studies.loc[~event_studies["research_event_id"].isin(event_ids), "research_event_id"]
    if not unmatched.empty:
        examples = unmatched.drop_duplicates().head(5).tolist()
        raise ValueError(f"event_studies contains IDs absent from research_events: {examples}")
    studies = {
        row.research_event_id: {
            "car30": _finite_number(row.car30),
            "car30_status": None if pd.isna(row.car30_status) else str(row.car30_status),
        }
        for row in event_studies.itertuples(index=False)
    }
    events = events.sort_values(
        ["public_event_day", "research_event_id"], kind="stable", na_position="last"
    ).reset_index(drop=True)
    return events, studies


def _car30_end(
    public_event_day: pd.Timestamp,
    session_positions: dict[pd.Timestamp, int],
    sessions: list[pd.Timestamp],
) -> pd.Timestamp | None:
    event_index = session_positions.get(public_event_day)
    if event_index is None or event_index + 29 >= len(sessions):
        return None
    return sessions[event_index + 29]


def select_comparable_events(
    research_events: pd.DataFrame,
    event_studies: pd.DataFrame,
    companies: pd.DataFrame,
    expected_sessions: pd.Series | pd.Index | Sequence[object],
) -> pd.DataFrame:
    """Select an auditable, leakage-safe comparable cohort for every event.

    Selection uses event metadata and CAR30 availability only; CAR30 magnitude
    and sign never affect cohort membership. The returned
    ``comparable_event_ids`` list identifies the selected company-event rows.
    """
    sessions = _expected_sessions(expected_sessions)
    positions = {date: index for index, date in enumerate(sessions)}
    events, studies = _prepare_inputs(research_events, event_studies, companies)
    output: list[dict[str, Any]] = []

    for _, focal in events.iterrows():
        reasons: list[str] = []
        focal_info = focal["information_date"]
        focal_sector = focal["sector_key"]
        focal_role = focal["role_key"]
        if pd.isna(focal_info):
            reasons.append("missing_focal_information_date")
        if pd.isna(focal["ticker"]) or not str(focal["ticker"]).strip():
            reasons.append("missing_focal_ticker")
        if pd.isna(focal_sector) or not str(focal_sector).strip():
            reasons.append("missing_focal_sector")

        eligible_ids: list[object] = []
        sector_ids: list[object] = []
        role_ids: list[object] = []
        if not reasons:
            for _, candidate in events.iterrows():
                candidate_id = candidate["research_event_id"]
                if candidate_id == focal["research_event_id"]:
                    continue
                if pd.isna(candidate["sector_key"]) or candidate["sector_key"] != focal_sector:
                    continue
                if pd.isna(candidate["information_date"]) or not candidate["information_date"] < focal_info:
                    continue
                study = studies.get(candidate_id)
                if study is None or study["car30_status"] != "complete" or study["car30"] is None:
                    continue
                end_date = _car30_end(candidate["public_event_day"], positions, sessions)
                if end_date is None or not end_date < focal_info:
                    continue
                sector_ids.append(candidate_id)
                if (
                    pd.notna(focal_role)
                    and pd.notna(candidate["role_key"])
                    and candidate["role_key"] == focal_role
                ):
                    role_ids.append(candidate_id)
            if len(role_ids) >= MIN_COMPARABLE_EVENTS:
                eligible_ids = role_ids
                rule = "same_sector_and_role"
            else:
                eligible_ids = sector_ids
                rule = "same_sector"
        else:
            rule = "unavailable"

        status = "complete" if len(eligible_ids) >= MIN_COMPARABLE_EVENTS else "insufficient_data"
        if status == "insufficient_data" and not reasons:
            reasons.append("fewer_than_10_eligible_comparable_events")
        output.append({
            "research_event_id": focal["research_event_id"],
            "ticker": focal["ticker"],
            "information_date": focal_info,
            "comparable_event_ids": eligible_ids,
            "comparable_event_count": len(eligible_ids),
            "same_sector_role_eligible_count": len(role_ids),
            "same_sector_eligible_count": len(sector_ids),
            "cohort_definition": rule,
            "status": status,
            "missing_reasons": reasons,
        })
    return pd.DataFrame(output)


def _bootstrap_component(
    car30_values: Sequence[float],
    *,
    n_resamples: int,
    seed: int,
) -> dict[str, Any]:
    values = np.asarray(car30_values, dtype=float)
    if values.ndim != 1 or len(values) < MIN_COMPARABLE_EVENTS or not np.isfinite(values).all():
        return {
            "status": "unavailable",
            "missing_reasons": ["invalid_or_insufficient_car30_sample"],
        }
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(values), size=(n_resamples, len(values)))
    means = values[draws].mean(axis=1)
    if not np.isfinite(means).all():
        return {"status": "unavailable", "missing_reasons": ["nonfinite_bootstrap_estimates"]}
    q = float(np.mean(means > 0.0))
    support = float(100.0 * np.clip((q - 0.5) / 0.5, 0.0, 1.0))
    lower, upper = np.quantile(means, [0.025, 0.975])
    return {
        "mean_car30": float(values.mean()),
        "bootstrap_ci_lower": float(lower),
        "bootstrap_ci_upper": float(upper),
        "bootstrap_q": q,
        "B_support": support,
        "bootstrap_seed": int(seed),
        "bootstrap_resample_count": int(n_resamples),
        "status": "complete",
        "missing_reasons": [],
    }


def _pseudo_candidates(
    cohort: pd.DataFrame,
    all_events: pd.DataFrame,
    prices: pd.DataFrame,
    sessions: list[pd.Timestamp],
    focal_information_date: pd.Timestamp,
) -> tuple[dict[object, list[object]], dict[object, float | None], str | None]:
    actual_days: dict[str, set[pd.Timestamp]] = defaultdict(set)
    for _, event in all_events.iterrows():
        if pd.notna(event["public_event_day"]) and pd.notna(event["ticker"]):
            actual_days[str(event["ticker"])].add(event["public_event_day"])

    candidate_rows: list[dict[str, Any]] = []
    candidate_key_by_event: dict[object, tuple[str, int]] = {}
    candidate_id_by_key_date: dict[tuple[str, int, pd.Timestamp], object] = {}
    seen_keys: set[tuple[str, int]] = set()
    for _, event in cohort.iterrows():
        ticker = str(event["ticker"])
        year = int(event["public_event_day"].year)
        key = (ticker, year)
        candidate_key_by_event[event["research_event_id"]] = key
        if key in seen_keys:
            continue
        seen_keys.add(key)
        for session_index, date in enumerate(sessions):
            if date.year != year or date in actual_days[ticker]:
                continue
            if session_index + 29 >= len(sessions):
                continue
            if not sessions[session_index + 29] < focal_information_date:
                continue
            pseudo_id = f"pseudo:{ticker}:{date.date().isoformat()}"
            candidate_id_by_key_date[(ticker, year, date)] = pseudo_id
            candidate_rows.append({
                "research_event_id": pseudo_id,
                "ticker": ticker,
                "public_event_day": date,
                "information_date": date - pd.Timedelta(days=1),
            })

    candidate_ids_by_key: dict[tuple[str, int], list[object]] = defaultdict(list)
    for (ticker, year, _), pseudo_id in candidate_id_by_key_date.items():
        candidate_ids_by_key[(ticker, year)].append(pseudo_id)
    candidate_ids_by_event = {
        event_id: list(candidate_ids_by_key[key])
        for event_id, key in candidate_key_by_event.items()
    }
    if any(not candidate_ids for candidate_ids in candidate_ids_by_event.values()):
        return candidate_ids_by_event, {}, "no_eligible_pseudo_event_dates"
    if not candidate_rows:
        return candidate_ids_by_event, {}, "no_eligible_pseudo_event_dates"

    pseudo_events = pd.DataFrame(candidate_rows).drop_duplicates("research_event_id")
    pseudo_studies = build_event_studies(pseudo_events, prices, sessions)
    pseudo_values = {
        row.research_event_id: (
            _finite_number(row.car30)
            if row.car30_status == "complete"
            else None
        )
        for row in pseudo_studies.itertuples(index=False)
    }
    # Sampling only from complete candidate outcomes is equivalent to drawing
    # from the full date pool and rejecting every replicate that selected an
    # incomplete outcome. It avoids wasting attempts while preserving that
    # conditional randomized-timing distribution.
    candidate_ids_by_event = {
        event_id: [candidate_id for candidate_id in ids if pseudo_values.get(candidate_id) is not None]
        for event_id, ids in candidate_ids_by_event.items()
    }
    if any(not ids for ids in candidate_ids_by_event.values()):
        return candidate_ids_by_event, pseudo_values, "no_complete_pseudo_event_candidates"
    return candidate_ids_by_event, pseudo_values, None


def _randomization_component(
    actual_car30: Sequence[float],
    candidate_ids_by_event: dict[object, list[object]],
    pseudo_car30: dict[object, float | None],
    *,
    n_replicates: int,
    seed: int,
    max_attempts: int,
) -> dict[str, Any]:
    actual = np.asarray(actual_car30, dtype=float)
    t_observed = float(actual.mean())
    base = {
        "T_obs": t_observed,
        "randomization_seed": int(seed),
        "randomization_replicates_requested": int(n_replicates),
        "randomization_max_attempts": int(max_attempts),
        "randomization_attempted_count": 0,
        "randomization_valid_replicate_count": 0,
    }
    if not candidate_ids_by_event or any(not ids for ids in candidate_ids_by_event.values()):
        return {
            **base,
            "status": "unavailable",
            "missing_reasons": ["no_eligible_pseudo_event_dates"],
        }

    rng = np.random.default_rng(seed)
    t_stars: list[float] = []
    attempted = 0
    while attempted < max_attempts and len(t_stars) < n_replicates:
        attempted += 1
        sampled: list[float] = []
        for event_id, candidate_ids in candidate_ids_by_event.items():
            candidate_id = candidate_ids[int(rng.integers(0, len(candidate_ids)))]
            value = pseudo_car30.get(candidate_id)
            if value is None:
                break
            sampled.append(value)
        if len(sampled) == len(candidate_ids_by_event):
            t_stars.append(float(np.mean(sampled)))

    base["randomization_attempted_count"] = attempted
    base["randomization_valid_replicate_count"] = len(t_stars)
    if len(t_stars) != n_replicates:
        return {
            **base,
            "status": "unavailable",
            "missing_reasons": ["full_valid_randomization_replicate_count_not_achieved"],
        }
    exceedances = int(np.count_nonzero(np.asarray(t_stars) >= t_observed))
    p_value = float((1 + exceedances) / (n_replicates + 1))
    p_support = float(100.0 * np.clip(1.0 - p_value / 0.10, 0.0, 1.0))
    return {
        **base,
        "randomization_exceedance_count": exceedances,
        "randomization_p_value": p_value,
        "P_support": p_support,
        "status": "complete",
        "missing_reasons": [],
    }


def _empty_component(status: str, reasons: list[str]) -> dict[str, Any]:
    return {"status": status, "missing_reasons": list(reasons)}


def _combine_result(
    selection: pd.Series,
    bootstrap: dict[str, Any],
    randomization: dict[str, Any],
    mean_car30: float | None = None,
) -> dict[str, Any]:
    b_support = bootstrap.get("B_support")
    p_support = randomization.get("P_support")
    score = None if b_support is None or p_support is None else float(0.5 * b_support + 0.5 * p_support)
    bootstrap_ok = bootstrap.get("status") == "complete"
    randomization_ok = randomization.get("status") == "complete"
    if bootstrap_ok and randomization_ok:
        status = "complete"
    elif bootstrap_ok or randomization_ok:
        status = "partial"
    else:
        status = "insufficient_data"
    reasons = [
        f"bootstrap:{reason}" for reason in bootstrap.get("missing_reasons", [])
    ] + [
        f"randomization:{reason}" for reason in randomization.get("missing_reasons", [])
    ]
    row = {
        "research_event_id": selection["research_event_id"],
        "ticker": selection["ticker"],
        "information_date": selection["information_date"],
        "comparable_event_ids": selection["comparable_event_ids"],
        "comparable_event_count": selection["comparable_event_count"],
        "cohort_definition": selection["cohort_definition"],
        "mean_car30": bootstrap.get("mean_car30") if mean_car30 is None else mean_car30,
        "bootstrap_ci_lower": bootstrap.get("bootstrap_ci_lower"),
        "bootstrap_ci_upper": bootstrap.get("bootstrap_ci_upper"),
        "bootstrap_q": bootstrap.get("bootstrap_q"),
        "B_support": b_support,
        "bootstrap_seed": bootstrap.get("bootstrap_seed"),
        "bootstrap_resample_count": bootstrap.get("bootstrap_resample_count"),
        "bootstrap_status": bootstrap.get("status"),
        "bootstrap_missing_reasons": bootstrap.get("missing_reasons", []),
        "T_obs": randomization.get("T_obs"),
        "randomization_p_value": randomization.get("randomization_p_value"),
        "P_support": p_support,
        "randomization_seed": randomization.get("randomization_seed"),
        "randomization_replicates_requested": randomization.get("randomization_replicates_requested"),
        "randomization_max_attempts": randomization.get("randomization_max_attempts"),
        "randomization_attempted_count": randomization.get("randomization_attempted_count"),
        "randomization_valid_replicate_count": randomization.get("randomization_valid_replicate_count"),
        "randomization_exceedance_count": randomization.get("randomization_exceedance_count"),
        "randomization_status": randomization.get("status"),
        "randomization_missing_reasons": randomization.get("missing_reasons", []),
        "statistical_score": score,
        "status": status,
        "missing_reasons": reasons,
    }
    return row


def build_statistical_validations(
    research_events: pd.DataFrame,
    event_studies: pd.DataFrame,
    companies: pd.DataFrame,
    prices: pd.DataFrame,
    expected_sessions: pd.Series | pd.Index | Sequence[object],
    *,
    bootstrap_seed: int = DEFAULT_BOOTSTRAP_SEED,
    randomization_seed: int = DEFAULT_RANDOMIZATION_SEED,
    max_randomization_attempts: int | None = None,
) -> pd.DataFrame:
    """Return one statistical-validation row per focal research event.

    The focal event's own future CAR30 is never required. ``event_studies``
    supplies realized comparator CAR30 values; pseudo-event CAR30 values are
    recomputed through :func:`build_event_studies`. Component results remain
    available independently, while ``statistical_score`` is null unless both
    support components are complete.
    """
    for name, value in (("bootstrap_seed", bootstrap_seed), ("randomization_seed", randomization_seed)):
        if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")
    if max_randomization_attempts is None:
        max_randomization_attempts = DEFAULT_RANDOMIZATION_REPLICATES * DEFAULT_RANDOMIZATION_ATTEMPT_MULTIPLIER
    if (
        isinstance(max_randomization_attempts, bool)
        or not isinstance(max_randomization_attempts, (int, np.integer))
        or max_randomization_attempts < DEFAULT_RANDOMIZATION_REPLICATES
    ):
        raise ValueError("max_randomization_attempts must be an integer >= 1000")

    sessions = _expected_sessions(expected_sessions)
    if not {"ticker", "date", "analysis_price"}.issubset(prices.columns):
        missing = sorted({"ticker", "date", "analysis_price"} - set(prices.columns))
        raise ValueError(f"prices missing required columns: {missing}")
    events, studies = _prepare_inputs(research_events, event_studies, companies)
    # Validate price dates, tickers, and duplicate keys even when calendar or
    # metadata constraints leave no pseudo dates to evaluate.
    empty_events = research_events.iloc[0:0][
        ["research_event_id", "ticker", "public_event_day", "information_date"]
    ]
    build_event_studies(empty_events, prices, sessions)
    selections = select_comparable_events(research_events, event_studies, companies, sessions)
    study_by_id = studies
    output: list[dict[str, Any]] = []
    for _, selection in selections.iterrows():
        if selection["status"] != "complete":
            reasons = list(selection["missing_reasons"])
            bootstrap = {
                "bootstrap_seed": int(bootstrap_seed),
                "bootstrap_resample_count": DEFAULT_BOOTSTRAP_RESAMPLES,
                "status": "insufficient_data",
                "missing_reasons": reasons,
            }
            randomization = _empty_component("insufficient_data", reasons)
            randomization.update({
                "T_obs": None,
                "randomization_seed": int(randomization_seed),
                "randomization_replicates_requested": DEFAULT_RANDOMIZATION_REPLICATES,
                "randomization_max_attempts": int(max_randomization_attempts),
                "randomization_attempted_count": 0,
                "randomization_valid_replicate_count": 0,
            })
            output.append(_combine_result(selection, bootstrap, randomization))
            continue

        cohort = events.loc[events["research_event_id"].isin(selection["comparable_event_ids"])].copy()
        actual_values = [float(study_by_id[event_id]["car30"]) for event_id in selection["comparable_event_ids"]]
        try:
            bootstrap = _bootstrap_component(
                actual_values,
                n_resamples=DEFAULT_BOOTSTRAP_RESAMPLES,
                seed=int(bootstrap_seed),
            )
        except (FloatingPointError, ValueError, OverflowError):
            bootstrap = {
                "bootstrap_seed": int(bootstrap_seed),
                "bootstrap_resample_count": DEFAULT_BOOTSTRAP_RESAMPLES,
                "status": "unavailable",
                "missing_reasons": ["bootstrap_calculation_failed"],
            }

        randomization: dict[str, Any]
        try:
            candidate_ids, pseudo_values, candidate_error = _pseudo_candidates(
                cohort, events, prices, sessions, selection["information_date"]
            )
            if candidate_error is not None:
                actual_mean = float(np.mean(actual_values))
                randomization = {
                    "T_obs": actual_mean,
                    "randomization_seed": int(randomization_seed),
                    "randomization_replicates_requested": DEFAULT_RANDOMIZATION_REPLICATES,
                    "randomization_max_attempts": int(max_randomization_attempts),
                    "randomization_attempted_count": 0,
                    "randomization_valid_replicate_count": 0,
                    "status": "unavailable",
                    "missing_reasons": [candidate_error],
                }
            else:
                randomization = _randomization_component(
                    actual_values,
                    candidate_ids,
                    pseudo_values,
                    n_replicates=DEFAULT_RANDOMIZATION_REPLICATES,
                    seed=int(randomization_seed),
                    max_attempts=int(max_randomization_attempts),
                )
        except (FloatingPointError, OverflowError):
            randomization = {
                "T_obs": float(np.mean(actual_values)),
                "randomization_seed": int(randomization_seed),
                "randomization_replicates_requested": DEFAULT_RANDOMIZATION_REPLICATES,
                "randomization_max_attempts": int(max_randomization_attempts),
                "randomization_attempted_count": 0,
                "randomization_valid_replicate_count": 0,
                "status": "unavailable",
                "missing_reasons": ["pseudo_event_study_calculation_failed"],
            }
        output.append(_combine_result(selection, bootstrap, randomization, float(np.mean(actual_values))))
    return pd.DataFrame(output)
