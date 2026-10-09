"""Market-model event study for supplied, adjustment-aware daily prices.

The caller supplies one row per research event and price observations for each
event ticker plus SPY. The sorted union of the ticker's and SPY's supplied
dates defines that pair's observed session calendar. Daily returns are formed
only between adjacent dates on that calendar when both prices are finite and
positive on both dates. No prices or sessions are forward-filled or inferred.

The benchmark calendar cannot reveal a session absent from *both* supplied
series; callers must supply complete daily observations to guarantee that
absence is detected. An event must have a public_event_day after its
information_date. Model fitting uses returns ending only in sessions -120
through -21; post-event returns are outcomes and never enter the fit.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


MIN_ESTIMATION_OBSERVATIONS = 60
ESTIMATION_START = -120
ESTIMATION_END = -21
CAR_HORIZONS = {"car5": 5, "car30": 30, "car90": 90}
BENCHMARK = "SPY"


def _normalized_dates(values: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(values, errors="coerce", format="mixed")
    # Preserve calendar dates when values carry a timezone; daily bars are
    # identified by their displayed date, not an intraday instant.
    try:
        if parsed.dt.tz is not None:
            parsed = parsed.dt.tz_localize(None)
    except (AttributeError, TypeError):
        pass
    return parsed.dt.normalize()


def _prepare_inputs(
    research_events: pd.DataFrame,
    prices: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    event_columns = {"research_event_id", "ticker", "public_event_day", "information_date"}
    price_columns = {"ticker", "date", "analysis_price"}
    if not event_columns.issubset(research_events.columns):
        missing = sorted(event_columns - set(research_events.columns))
        raise ValueError(f"research_events missing required columns: {missing}")
    if not price_columns.issubset(prices.columns):
        missing = sorted(price_columns - set(prices.columns))
        raise ValueError(f"prices missing required columns: {missing}")
    if research_events["research_event_id"].isna().any():
        raise ValueError("research_events must contain non-null research_event_id values")
    if research_events["research_event_id"].duplicated().any():
        raise ValueError("research_events must contain unique research_event_id values")

    events = research_events[["research_event_id", "ticker", "public_event_day", "information_date"]].copy()
    events["ticker"] = events["ticker"].astype("string").str.strip().str.upper()
    events["public_event_day"] = _normalized_dates(events["public_event_day"])
    events["information_date"] = _normalized_dates(events["information_date"])

    market = prices[["ticker", "date", "analysis_price"]].copy()
    market["ticker"] = market["ticker"].astype("string").str.strip().str.upper()
    market["date"] = _normalized_dates(market["date"])
    if market["date"].isna().any():
        bad_rows = market.index[market["date"].isna()].tolist()[:5]
        raise ValueError(f"prices contain malformed or missing dates at rows: {bad_rows}")
    if market["ticker"].isna().any() or market["ticker"].eq("").any():
        bad_rows = market.index[market["ticker"].isna() | market["ticker"].eq("")].tolist()[:5]
        raise ValueError(f"prices contain missing tickers at rows: {bad_rows}")
    duplicate_mask = market.duplicated(["ticker", "date"], keep=False)
    if duplicate_mask.any():
        examples = market.loc[duplicate_mask, ["ticker", "date"]].drop_duplicates().head(5)
        raise ValueError(f"prices contain duplicate ticker/date observations: {examples.to_dict('records')}")

    market["analysis_price"] = pd.to_numeric(market["analysis_price"], errors="coerce")
    # Keep invalid observations in the date calendar, but never use their
    # values. This lets affected horizons report missing/invalid prices.
    invalid = ~np.isfinite(market["analysis_price"].to_numpy(dtype=float, na_value=np.nan))
    invalid |= market["analysis_price"].le(0).fillna(True).to_numpy()
    market.loc[invalid, "analysis_price"] = np.nan
    market = market.sort_values(["ticker", "date"], kind="stable").reset_index(drop=True)
    events = events.sort_values(["public_event_day", "research_event_id"], kind="stable", na_position="last").reset_index(drop=True)
    return events, market


def _price_map(market: pd.DataFrame, ticker: str) -> dict[pd.Timestamp, float | None]:
    rows = market.loc[market["ticker"].eq(ticker)]
    return {
        row.date: (float(row.analysis_price) if pd.notna(row.analysis_price) else None)
        for row in rows.itertuples(index=False)
    }


def _returns_for_pair(
    market: pd.DataFrame,
    ticker: str,
) -> tuple[list[pd.Timestamp], dict[pd.Timestamp, tuple[float | None, float | None]]]:
    stock_prices = _price_map(market, ticker)
    spy_prices = _price_map(market, BENCHMARK)
    # The union catches dates observed for only one member of the pair. A
    # return is valid only when both prices are present on consecutive dates.
    sessions = sorted(set(stock_prices) | set(spy_prices))
    returns: dict[pd.Timestamp, tuple[float | None, float | None]] = {}
    for index in range(1, len(sessions)):
        previous, current = sessions[index - 1], sessions[index]
        stock_prev, stock_now = stock_prices.get(previous), stock_prices.get(current)
        spy_prev, spy_now = spy_prices.get(previous), spy_prices.get(current)
        if None in (stock_prev, stock_now, spy_prev, spy_now):
            returns[current] = (None, None)
            continue
        assert stock_prev is not None and stock_now is not None
        assert spy_prev is not None and spy_now is not None
        stock_return = stock_now / stock_prev - 1.0
        spy_return = spy_now / spy_prev - 1.0
        if not np.isfinite(stock_return) or not np.isfinite(spy_return):
            returns[current] = (None, None)
        else:
            returns[current] = (float(stock_return), float(spy_return))
    return sessions, returns


def _unavailable_horizons(reason: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in CAR_HORIZONS:
        result[name] = None
        result[f"{name}_status"] = "unavailable"
        result[f"{name}_missing_reasons"] = [reason]
    return result


def _mark_horizons_unavailable(base: dict[str, Any], reason: str) -> None:
    for name in CAR_HORIZONS:
        base[name] = None
        base[f"{name}_status"] = "unavailable"
        base[f"{name}_missing_reasons"] = [reason]


def _event_result(event: pd.Series, market: pd.DataFrame) -> dict[str, Any]:
    base: dict[str, Any] = {
        "research_event_id": event["research_event_id"],
        "ticker": event["ticker"],
        "public_event_day": event["public_event_day"],
        "information_date": event["information_date"],
        "alpha": None,
        "beta": None,
        "estimation_observation_count": 0,
        **_unavailable_horizons("not_calculated"),
    }
    if pd.isna(event["ticker"]) or not str(event["ticker"]).strip():
        base.update(status="missing_company_identifier", missing_reasons=["missing_ticker"])
        return base
    if pd.isna(event["public_event_day"]):
        base.update(status="missing_event_date", missing_reasons=["missing_public_event_day"])
        return base
    if pd.isna(event["information_date"]):
        base.update(status="missing_information_date", missing_reasons=["missing_information_date"])
        return base
    if event["public_event_day"] <= event["information_date"]:
        base.update(status="invalid_event_timing", missing_reasons=["public_event_day_not_after_information_date"])
        return base
    if event["ticker"] == BENCHMARK:
        base.update(status="invalid_company_identifier", missing_reasons=["event_ticker_is_benchmark"])
        return base

    sessions, returns = _returns_for_pair(market, str(event["ticker"]))
    session_positions = {date: index for index, date in enumerate(sessions)}
    event_date = event["public_event_day"]
    if event_date not in session_positions:
        base.update(status="missing_event_session", missing_reasons=["public_event_day_not_in_supplied_session_calendar"])
        return base
    event_index = session_positions[event_date]

    estimation: list[tuple[float, float]] = []
    for offset in range(ESTIMATION_START, ESTIMATION_END + 1):
        index = event_index + offset
        if index < 1 or index >= len(sessions):
            continue
        pair = returns.get(sessions[index])
        if pair is not None and pair[0] is not None and pair[1] is not None:
            estimation.append((pair[0], pair[1]))
    base["estimation_observation_count"] = len(estimation)
    if len(estimation) < MIN_ESTIMATION_OBSERVATIONS:
        base["status"] = "insufficient_estimation_data"
        base["missing_reasons"] = ["fewer_than_60_paired_estimation_returns"]
        _mark_horizons_unavailable(base, "insufficient_estimation_sample")
        return base

    sample = np.asarray(estimation, dtype=float)
    stock_returns, market_returns = sample[:, 0], sample[:, 1]
    if not np.isfinite(sample).all() or float(np.var(market_returns)) == 0.0:
        base["status"] = "invalid_estimation_data"
        base["missing_reasons"] = ["nonfinite_returns_or_zero_benchmark_variance"]
        _mark_horizons_unavailable(base, "invalid_estimation_data")
        return base
    design = np.column_stack((np.ones(len(market_returns)), market_returns))
    coefficients, _, rank, _ = np.linalg.lstsq(design, stock_returns, rcond=None)
    if rank < 2 or not np.isfinite(coefficients).all():
        base["status"] = "invalid_estimation_data"
        base["missing_reasons"] = ["market_model_fit_failed"]
        _mark_horizons_unavailable(base, "market_model_fit_failed")
        return base
    alpha, beta = map(float, coefficients)
    base["alpha"], base["beta"] = alpha, beta

    for name, horizon in CAR_HORIZONS.items():
        abnormal_returns: list[float] = []
        missing_reasons: list[str] = []
        for offset in range(horizon):
            index = event_index + offset
            if index < 1 or index >= len(sessions):
                missing_reasons.append(f"missing_event_session_t{offset}")
                continue
            session_date = sessions[index]
            pair = returns.get(session_date)
            if pair is None or pair[0] is None or pair[1] is None:
                missing_reasons.append(f"missing_paired_return_t{offset}")
                continue
            stock_return, market_return = pair
            abnormal_returns.append(stock_return - (alpha + beta * market_return))
        if missing_reasons:
            base[name] = None
            base[f"{name}_status"] = "unavailable"
            base[f"{name}_missing_reasons"] = missing_reasons
        else:
            base[name] = float(np.sum(abnormal_returns))
            base[f"{name}_status"] = "complete"
            base[f"{name}_missing_reasons"] = []

    horizon_statuses = [base[f"{name}_status"] for name in CAR_HORIZONS]
    if all(status == "complete" for status in horizon_statuses):
        base["status"] = "complete"
        base["missing_reasons"] = []
    elif any(status == "complete" for status in horizon_statuses):
        base["status"] = "partial"
        base["missing_reasons"] = [
            f"{name}:{reason}"
            for name in CAR_HORIZONS
            for reason in base[f"{name}_missing_reasons"]
        ]
    else:
        base["status"] = "insufficient_data"
        base["missing_reasons"] = [
            f"{name}:{reason}"
            for name in CAR_HORIZONS
            for reason in base[f"{name}_missing_reasons"]
        ]
    return base


def build_event_studies(research_events: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Return one market-model event-study result per research_event_id.

    Price dates are paired exactly. The pair-specific union of observed stock
    and SPY dates is the session calendar, so an unpaired supplied date breaks
    returns on that date and the next adjacent date. A missing date absent from
    both series cannot be detected without an external exchange calendar.
    Invalid (nonfinite, nonnumeric, zero, or negative) prices are treated as
    missing observations. Duplicate ticker/date rows and malformed price dates
    raise ``ValueError``. Event horizons are all-or-nothing: no partial CAR is
    returned when any required paired return is unavailable.
    """
    events, market = _prepare_inputs(research_events, prices)
    rows = [_event_result(event, market) for _, event in events.iterrows()]
    return pd.DataFrame(rows)
