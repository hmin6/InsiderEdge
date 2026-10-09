"""Point-in-time market-dislocation scores over the frozen project universe."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import numpy as np
import pandas as pd

from app.quant.features import EVENT_KEY, _valid_number, build_market_feature_snapshot


MIN_DISLOCATION_REFERENCE = 10


def empirical_midrank_percentile(value: float, reference_values: Iterable[float]) -> float | None:
    """Return the empirical midrank percentile on a 0–100 scale.

    The percentile is ``100 * (count(reference < value) + 0.5 *
    count(reference == value)) / n``. Values outside the reference range map
    to 0 or 100. Non-finite reference values are excluded.
    """
    if not _valid_number(value):
        return None
    reference = np.asarray([float(item) for item in reference_values if _valid_number(item)], dtype=float)
    if reference.size == 0:
        return None
    value = float(value)
    less = int(np.count_nonzero(reference < value))
    equal = int(np.count_nonzero(reference == value))
    return float(100.0 * (less + 0.5 * equal) / reference.size)


def _universe_tickers(frozen_universe) -> list[str]:
    companies = getattr(frozen_universe, "companies", None)
    values = (company.ticker for company in companies) if companies is not None else frozen_universe
    try:
        raw_tickers = list(values)
    except TypeError as exc:
        raise ValueError("frozen_universe must be a ticker iterable or Universe") from exc
    if any(pd.isna(value) for value in raw_tickers):
        raise ValueError("frozen_universe must contain valid tickers")
    tickers = [str(value).strip().upper() for value in raw_tickers]
    if not tickers or any(not ticker or ticker in {"NAN", "NONE"} for ticker in tickers):
        raise ValueError("frozen_universe must contain valid tickers")
    if len(set(tickers)) != len(tickers):
        raise ValueError("frozen_universe must not contain duplicate tickers")
    return sorted(tickers)


def build_dislocation_scores(
    research_events: pd.DataFrame,
    prices: pd.DataFrame,
    frozen_universe,
    *,
    sector_etf_by_ticker: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """Return one market-dislocation result per research event.

    For each event information date, the reference cross-section is calculated
    for every ticker in the supplied frozen universe using only ``analysis_price``
    observations strictly before that date. The frozen membership can create
    survivorship/selection bias; it is not a historical point-in-time index
    reconstruction. Sector gap and drawdown use separate complete-case
    reference distributions and each requires at least
    ``MIN_DISLOCATION_REFERENCE`` rows.

    ``drawdown_90d`` is nonpositive by the feature contract, so its magnitude is
    ``abs(drawdown_90d)``. The score is unavailable if either component or its
    reference distribution is unavailable/insufficient; weights are never
    renormalized and missing values are never imputed.
    """
    required_events = {EVENT_KEY, "ticker", "information_date"}
    if not required_events.issubset(research_events.columns):
        raise ValueError(f"research_events missing {sorted(required_events - set(research_events.columns))}")
    if research_events[EVENT_KEY].isna().any() or research_events[EVENT_KEY].duplicated().any():
        raise ValueError("research_events must contain unique, non-null research_event_id values")

    events = research_events[[EVENT_KEY, "ticker", "information_date"]].copy()
    events["ticker"] = events["ticker"].astype("string").str.strip().str.upper()
    events["information_date"] = pd.to_datetime(events["information_date"], errors="coerce").dt.normalize()
    if events["ticker"].isna().any() or events["ticker"].eq("").any() or events["information_date"].isna().any():
        raise ValueError("research_events must have valid ticker and information_date values")
    events = events.sort_values(["information_date", "ticker", EVENT_KEY], kind="stable").reset_index(drop=True)

    tickers = _universe_tickers(frozen_universe)
    etf_map = {str(key).strip().upper(): str(value).strip().upper()
               for key, value in (sector_etf_by_ticker or {}).items()}
    snapshots = build_market_feature_snapshot(
        events["information_date"].drop_duplicates().tolist(),
        prices,
        tickers,
        sector_etf_by_ticker=etf_map,
    )
    snapshots["sector_gap90"] = snapshots["sector_return_90d"] - snapshots["prior_return_90d"]
    snapshots["drawdown_magnitude_90d"] = snapshots["drawdown_90d"].abs()

    universe_set = set(tickers)
    results: list[dict[str, object]] = []
    for event in events.itertuples(index=False):
        event_id, ticker, information_date = getattr(event, EVENT_KEY), event.ticker, event.information_date
        date_snapshot = snapshots.loc[snapshots["information_date"].eq(information_date)]
        ticker_rows = date_snapshot.loc[date_snapshot["ticker"].eq(ticker)]
        reasons: list[str] = []
        if ticker not in universe_set:
            reasons.append("ticker_not_in_frozen_universe")

        market = ticker_rows.iloc[0] if not ticker_rows.empty else None
        stock_return = market["prior_return_90d"] if market is not None else None
        sector_return = market["sector_return_90d"] if market is not None else None
        sector_gap = market["sector_gap90"] if market is not None else None
        drawdown = market["drawdown_90d"] if market is not None else None
        drawdown_magnitude = market["drawdown_magnitude_90d"] if market is not None else None

        sector_reference = date_snapshot["sector_gap90"].dropna().astype(float).to_numpy()
        drawdown_reference = date_snapshot["drawdown_magnitude_90d"].dropna().astype(float).to_numpy()
        sector_count, drawdown_count = len(sector_reference), len(drawdown_reference)

        sector_percentile = None
        if ticker in universe_set and _valid_number(sector_gap) and sector_count >= MIN_DISLOCATION_REFERENCE:
            sector_percentile = empirical_midrank_percentile(float(sector_gap), sector_reference)
        elif ticker in universe_set and not _valid_number(sector_gap):
            reasons.append("sector_gap_unavailable")
        if sector_count < MIN_DISLOCATION_REFERENCE:
            reasons.append("insufficient_sector_gap_reference")

        drawdown_percentile = None
        if ticker in universe_set and _valid_number(drawdown_magnitude) and drawdown_count >= MIN_DISLOCATION_REFERENCE:
            drawdown_percentile = empirical_midrank_percentile(float(drawdown_magnitude), drawdown_reference)
        elif ticker in universe_set and not _valid_number(drawdown_magnitude):
            reasons.append("drawdown_unavailable")
        if drawdown_count < MIN_DISLOCATION_REFERENCE:
            reasons.append("insufficient_drawdown_reference")

        score = None
        if sector_percentile is not None and drawdown_percentile is not None:
            score = 0.60 * sector_percentile + 0.40 * drawdown_percentile
        results.append({
            EVENT_KEY: event_id,
            "ticker": ticker,
            "information_date": information_date,
            "stock_return_90d": stock_return,
            "sector_return_90d": sector_return,
            "sector_gap90": sector_gap,
            "sector_gap_percentile": sector_percentile,
            "sector_gap_reference_count": sector_count,
            "drawdown_90d": drawdown,
            "drawdown_magnitude_90d": drawdown_magnitude,
            "drawdown_percentile": drawdown_percentile,
            "drawdown_reference_count": drawdown_count,
            "dislocation_score": score,
            "status": "complete" if score is not None else "insufficient_data",
            "unavailable_reasons": list(dict.fromkeys(reasons)),
        })

    output = pd.DataFrame(results)
    if output[EVENT_KEY].duplicated().any() or len(output) != len(research_events):
        raise AssertionError("dislocation output must preserve exactly one row per research event")
    return output
