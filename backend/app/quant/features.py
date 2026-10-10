"""Leakage-aware features for one row per SEC research event.

Inputs are normalized tables matching ``docs/DATA_SCHEMA.md``. Prices must
contain the persisted ``analysis_price`` convention for stocks, SPY, and sector
ETFs. This module computes pre-event features only; it does not train a model.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from math import log

import numpy as np
import pandas as pd

from app.services.events.buyers import BuyerEvidence

EVENT_KEY = "research_event_id"
_TRUE = {True, 1, "1", "true", "True", "TRUE", "yes", "Y"}


def _date_series(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, errors="coerce").dt.normalize()


def _valid_number(value: object) -> bool:
    try:
        return value is not None and bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


def _prepare_price_index(prices: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Normalize and index valid prices once for repeated point-in-time lookups."""
    price_rows = prices.copy()
    price_rows["ticker"] = price_rows["ticker"].astype("string").str.upper()
    price_rows["date"] = _date_series(price_rows["date"])
    price_rows = price_rows.loc[
        price_rows["date"].notna() & price_rows["analysis_price"].map(_valid_number)
    ]
    return {
        ticker: rows.sort_values("date").reset_index(drop=True)
        for ticker, rows in price_rows.groupby("ticker", sort=False)
    }


def _qualifying_mask(transactions: pd.DataFrame) -> pd.Series:
    """Use the normalized P0 flag, or reproduce its documented SEC predicate."""
    if "is_p0_qualifying" in transactions.columns:
        return transactions["is_p0_qualifying"].map(lambda value: value in _TRUE).fillna(False)
    required = {"transaction_code", "acquired_or_disposed", "derivative_flag"}
    if not required.issubset(transactions.columns):
        return pd.Series(False, index=transactions.index)
    return (
        transactions["transaction_code"].astype("string").str.upper().eq("P")
        & transactions["acquired_or_disposed"].astype("string").str.upper().eq("A")
        & ~transactions["derivative_flag"].map(lambda value: value in _TRUE).fillna(False)
    )


def _ownership_aggregate(rows: pd.DataFrame) -> tuple[float | None, bool | None]:
    """Apply DATA_SCHEMA's per-transaction ownership formula when supported."""
    changes: list[float] = []
    new_positions: list[bool] = []
    ownership_rows = 0
    unknown_ownership = False
    if not {"shares", "shares_owned_after"}.issubset(rows.columns):
        return None, None
    for shares, after in zip(rows["shares"], rows["shares_owned_after"]):
        if not (_valid_number(shares) and _valid_number(after)):
            unknown_ownership = True
            continue
        ownership_rows += 1
        prior = float(after) - float(shares)
        if prior > 0:
            changes.append(float(shares) / prior)
            new_positions.append(False)
        elif prior == 0:
            new_positions.append(True)
        else:
            unknown_ownership = True
    new_position = True if any(new_positions) else (None if unknown_ownership or ownership_rows == 0 else False)
    return (max(changes) if changes else None, new_position)


def _price_features(
    event: pd.Series,
    price_index: Mapping[str, pd.DataFrame],
    sector_etf_by_ticker: Mapping[str, str],
) -> dict[str, float | None]:
    ticker = str(event["ticker"]).upper()
    cutoff = pd.Timestamp(event["information_date"]).normalize()
    ticker_prices = price_index.get(ticker)
    if ticker_prices is None:
        history = pd.DataFrame(columns=["date", "analysis_price"])
    else:
        end = int(np.searchsorted(ticker_prices["date"].to_numpy(), cutoff.to_datetime64(), side="left"))
        history = ticker_prices.iloc[:end].tail(121)
    result: dict[str, float | None] = {
        "prior_return_5d": None,
        "prior_return_30d": None,
        "prior_return_90d": None,
        "sector_return_90d": None,
        "prior_volatility_30d": None,
        "drawdown_90d": None,
        "volume_zscore_30d": None,
        "spy_relative_return_30d": None,
        "sector_relative_return_30d": None,
    }
    values = history["analysis_price"].astype(float).to_numpy()
    if len(values) >= 6 and values[-6] != 0:
        result["prior_return_5d"] = float(values[-1] / values[-6] - 1)
    if len(values) >= 31 and values[-31] != 0:
        result["prior_return_30d"] = float(values[-1] / values[-31] - 1)
        denominators = values[-31:-1]
        if np.all(denominators != 0):
            returns_30 = values[-30:] / denominators - 1
            if np.all(np.isfinite(returns_30)):
                result["prior_volatility_30d"] = float(np.std(returns_30, ddof=1))
    if len(values) >= 91 and values[-91] != 0:
        result["prior_return_90d"] = float(values[-1] / values[-91] - 1)
        trailing = values[-91:]
        peak = np.max(trailing)
        if peak > 0:
            result["drawdown_90d"] = float(trailing[-1] / peak - 1)

        etf = sector_etf_by_ticker.get(ticker)
        if etf:
            stock_dates = history.tail(91)["date"]
            benchmark_rows = price_index.get(etf)
            aligned = (benchmark_rows.set_index("date")["analysis_price"].reindex(stock_dates).to_numpy(dtype=float)
                       if benchmark_rows is not None else np.array([]))
            if len(aligned) == 91 and np.all(np.isfinite(aligned)):
                benchmark_prices = aligned.astype(float)
                if benchmark_prices[0] > 0:
                    result["sector_return_90d"] = float(benchmark_prices[-1] / benchmark_prices[0] - 1)

    if "volume" in history.columns and len(history) >= 31:
        volume = pd.to_numeric(history["volume"], errors="coerce").to_numpy(dtype=float)
        baseline, latest = volume[-31:-1], volume[-1]
        baseline = baseline[np.isfinite(baseline)]
        if len(baseline) >= 2 and np.isfinite(latest):
            scale = float(np.std(baseline, ddof=1))
            if scale > 0:
                result["volume_zscore_30d"] = float((latest - np.mean(baseline)) / scale)

    etf = sector_etf_by_ticker.get(ticker)
    stock_return = result["prior_return_30d"]
    if etf and stock_return is not None and len(history) >= 31:
        stock_window = history.tail(31)
        stock_dates = stock_window["date"]
        for benchmark, feature in (("SPY", "spy_relative_return_30d"), (etf, "sector_relative_return_30d")):
            benchmark_rows = price_index.get(benchmark.upper())
            aligned = (benchmark_rows.set_index("date")["analysis_price"].reindex(stock_dates).to_numpy(dtype=float)
                       if benchmark_rows is not None else np.array([]))
            if len(aligned) == 31 and np.all(np.isfinite(aligned)):
                benchmark_prices = aligned.astype(float)
                if benchmark_prices[0] != 0:
                    benchmark_return = benchmark_prices[-1] / benchmark_prices[0] - 1
                    result[feature] = float(stock_return - benchmark_return)
    return result


def _supported_buyers(transactions: pd.DataFrame, evidence_by_transaction_id: Mapping) -> tuple[int | None, dict]:
    """Require existing transaction-associated evidence for every window row.

    A zero means the supplied qualifying window is empty, never that its owners
    were unnamed. Names and filing-wide owner groups are not identity evidence.
    """
    identities, sources, unknown = set(), set(), []
    for row in transactions.to_dict('records'):
        transaction_id = row.get('transaction_id')
        evidence = evidence_by_transaction_id.get(transaction_id) if isinstance(transaction_id, str) else None
        if (not isinstance(evidence, BuyerEvidence) or not evidence.identities
                or not isinstance(evidence.source, str) or not evidence.source.strip()
                or any(not isinstance(identity, str) or not identity.strip() for identity in evidence.identities)):
            unknown.append(transaction_id if isinstance(transaction_id, str) else 'missing_transaction_id')
        else:
            identities.update(identity.strip() for identity in evidence.identities)
            sources.add(evidence.source)
    return (None if unknown else len(identities)), {
        'status': 'unknown' if unknown else ('supported' if len(transactions) else 'no_qualifying_transactions'),
        'canonical_identity_verified': not unknown,
        'reason': 'buyer identity/count unknown: no reliable transaction-associated evidence' if unknown else None,
        'unknown_transaction_ids': sorted(set(unknown)),
        'evidence_sources': sorted(sources),
    }


def build_event_features(
    research_events: pd.DataFrame,
    transactions: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    sector_etf_by_ticker: Mapping[str, str] | None = None,
    buyer_evidence: Mapping[str, BuyerEvidence] | None = None,
) -> pd.DataFrame:
    """Return one pre-event feature row per ``research_event_id``.

    ``transactions`` retain their raw transaction grain. The current event is
    matched on ticker + public_event_day, then only qualifying filings with
    ``filing_date <= information_date`` contribute. Seven/thirty-day windows
    are inclusive calendar windows ending on the event information date.
    ``buyer_evidence`` reuses the event builder's transaction-id -> BuyerEvidence
    contract. Incomplete identity coverage makes that window's count null, with
    per-window ``buyer_identity_diagnostics``. ML provenance checks still apply.
    Recent rate is distinct event days in the inclusive current 30 days / 30;
    historical rate is events in the preceding 365 days, excluding those 30
    recent days, / 365. Missing/unavailable values remain ``None``.
    """
    required_events = {EVENT_KEY, "ticker", "public_event_day", "information_date"}
    required_prices = {"ticker", "date", "analysis_price"}
    if not required_events.issubset(research_events.columns):
        raise ValueError(f"research_events missing {sorted(required_events - set(research_events.columns))}")
    if not required_prices.issubset(prices.columns):
        raise ValueError(f"prices missing {sorted(required_prices - set(prices.columns))}")
    if research_events[EVENT_KEY].duplicated().any():
        raise ValueError("research_events must contain one row per research_event_id")

    events = research_events.copy().reset_index(drop=True)
    events["ticker"] = events["ticker"].astype("string").str.upper()
    events["public_event_day"] = _date_series(events["public_event_day"])
    events["information_date"] = _date_series(events["information_date"])
    tx = transactions.copy()
    if tx.empty:
        tx = pd.DataFrame(columns=["ticker", "public_event_day", "filing_date"])
    if "ticker" in tx:
        tx["ticker"] = tx["ticker"].astype("string").str.upper()
    if "filing_date" in tx:
        tx["filing_date"] = _date_series(tx["filing_date"])
    if "public_event_day" in tx:
        tx["public_event_day"] = _date_series(tx["public_event_day"])
    if "transaction_value" not in tx:
        tx["transaction_value"] = np.nan
    if "filing_date" not in tx:
        tx["filing_date"] = pd.NaT
    tx["_qualifies"] = _qualifying_mask(tx)
    tx = tx.loc[tx["_qualifies"]].copy()

    price_index = _prepare_price_index(prices)
    etf_map = {str(k).upper(): str(v).upper() for k, v in (sector_etf_by_ticker or {}).items()}

    transaction_feature_rows: list[dict[str, object]] = []
    for event in events.itertuples(index=False):
        record = event._asdict()
        ticker, event_day, information_date = record["ticker"], record["public_event_day"], record["information_date"]
        event_tx = tx.loc[
            tx.get("ticker", pd.Series(index=tx.index, dtype="string")).eq(ticker)
            & tx.get("public_event_day", pd.Series(index=tx.index, dtype="datetime64[ns]")).eq(event_day)
            & tx["filing_date"].le(information_date)
        ]
        ticker_tx = tx.loc[
            tx.get("ticker", pd.Series(index=tx.index, dtype="string")).eq(ticker)
            & tx["filing_date"].le(information_date)
        ]
        values = pd.to_numeric(event_tx["transaction_value"], errors="coerce")
        valid_values = values[np.isfinite(values) & values.ge(0)]
        aggregate = float(valid_values.sum()) if len(valid_values) else None
        tx_dates = ticker_tx["filing_date"]
        start7, start30 = information_date - pd.Timedelta(days=6), information_date - pd.Timedelta(days=29)
        window7 = tx_dates.between(start7, information_date, inclusive="both")
        window30 = tx_dates.between(start30, information_date, inclusive="both")
        buyers7, diagnostics7 = _supported_buyers(ticker_tx.loc[window7], buyer_evidence or {})
        buyers30, diagnostics30 = _supported_buyers(ticker_tx.loc[window30], buyer_evidence or {})
        value_series = pd.to_numeric(ticker_tx["transaction_value"], errors="coerce")
        valid_window_values = value_series.where(value_series.ge(0))

        # Counts/rates are event counts, not raw transaction counts.
        same_ticker_events = events.loc[events["ticker"].eq(ticker)]
        info_dates = same_ticker_events["information_date"]
        recent_events = info_dates.between(start30, information_date, inclusive="both").sum()
        historical_events = info_dates.between(
            information_date - pd.Timedelta(days=394), start30 - pd.Timedelta(days=1), inclusive="both"
        ).sum()

        # Event-level ownership values from Person 1 are authoritative when present.
        precomputed_change = record.get("max_valid_ownership_change_pct")
        precomputed_new = record.get("any_new_position_flag")
        has_precomputed_new = precomputed_new is not None and not pd.isna(precomputed_new)
        if _valid_number(precomputed_change) or has_precomputed_new:
            ownership_change = float(precomputed_change) if _valid_number(precomputed_change) else None
            new_position = bool(precomputed_new) if has_precomputed_new else None
        else:
            ownership_change, new_position = _ownership_aggregate(event_tx)

        aggregate_log = log(aggregate) if aggregate is not None and aggregate > 0 else None
        transaction_feature_rows.append({
            EVENT_KEY: record[EVENT_KEY],
            "aggregate_purchase_value": aggregate,
            "log_aggregate_purchase_value": aggregate_log,
            "max_valid_ownership_change_pct": ownership_change,
            "any_new_position_flag": new_position,
            "has_executive": record.get("has_executive"),
            "has_cfo": record.get("has_cfo"),
            "has_director": record.get("has_director"),
            "role_bucket": record.get("role_bucket"),
            "unique_buyers_7d": buyers7,
            "unique_buyers_30d": buyers30,
            "buyer_identity_diagnostics": {"7d": diagnostics7, "30d": diagnostics30},
            "purchase_value_7d": float(valid_window_values.loc[window7].sum()) if valid_window_values.loc[window7].notna().any() else None,
            "purchase_value_30d": float(valid_window_values.loc[window30].sum()) if valid_window_values.loc[window30].notna().any() else None,
            "recent_purchase_rate": float(recent_events / 30),
            "historical_purchase_rate": float(historical_events / 365),
        })

    transaction_features = pd.DataFrame(transaction_feature_rows)
    feature_rows: list[dict[str, object]] = []
    for _, event in events.iterrows():
        feature_rows.append({EVENT_KEY: event[EVENT_KEY], **_price_features(event, price_index, etf_map)})
    market_features = pd.DataFrame(feature_rows)
    result = events[[EVENT_KEY]].merge(transaction_features, on=EVENT_KEY, validate="one_to_one")
    result = result.merge(market_features, on=EVENT_KEY, validate="one_to_one")
    if result[EVENT_KEY].duplicated().any() or len(result) != len(research_events):
        raise AssertionError("feature output must preserve exactly one row per research event")
    return result


def build_market_feature_snapshot(
    information_dates: Iterable[object],
    prices: pd.DataFrame,
    frozen_universe_tickers: Iterable[str],
    *,
    sector_etf_by_ticker: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """Build pre-information-date market features for each date and universe ticker.

    The caller supplies the repository's frozen S&P 100 ticker list and the
    sector-ETF mapping. This is a cross-sectional snapshot, not historical
    index-membership reconstruction. Every stock and ETF price used is strictly
    before the requested information date.
    """
    required_prices = {"ticker", "date", "analysis_price"}
    if not required_prices.issubset(prices.columns):
        raise ValueError(f"prices missing {sorted(required_prices - set(prices.columns))}")
    raw_tickers = list(frozen_universe_tickers)
    if any(pd.isna(ticker) for ticker in raw_tickers):
        raise ValueError("frozen_universe_tickers must contain valid ticker values")
    tickers = [str(ticker).strip().upper() for ticker in raw_tickers]
    if not tickers or any(not ticker for ticker in tickers):
        raise ValueError("frozen_universe_tickers must contain valid ticker values")
    if len(set(tickers)) != len(tickers):
        raise ValueError("frozen_universe_tickers must not contain duplicates")
    tickers.sort()
    dates = pd.to_datetime(pd.Series(list(information_dates)), errors="coerce").dt.normalize()
    if dates.empty or dates.isna().any():
        raise ValueError("information_dates must contain valid dates")
    dates = sorted(set(dates.tolist()))
    price_index = _prepare_price_index(prices)
    etf_map = {str(k).upper(): str(v).upper() for k, v in (sector_etf_by_ticker or {}).items()}

    rows: list[dict[str, object]] = []
    for information_date in dates:
        for ticker in tickers:
            event = pd.Series({"ticker": ticker, "information_date": information_date})
            rows.append({
                "ticker": ticker,
                "information_date": information_date,
                **_price_features(event, price_index, etf_map),
            })
    return pd.DataFrame(rows)


FEATURE_DEFINITIONS = {
    "prior_return_5d": "prices.analysis_price[-1] / [-6] - 1; five trading intervals; decimal; null without six valid bars strictly before information_date.",
    "prior_return_30d": "prices.analysis_price[-1] / [-31] - 1; thirty trading intervals; decimal; null without 31 valid pre-information-date bars.",
    "prior_return_90d": "prices.analysis_price[-1] / [-91] - 1; ninety trading intervals; decimal; null without 91 valid pre-information-date bars.",
    "sector_return_90d": "Mapped sector ETF analysis_price[-1] / [-91] - 1 over the exact same 91 stock trading dates; decimal; null if no mapping or any aligned ETF bar is unavailable.",
    "prior_volatility_30d": "Sample standard deviation of 30 simple returns from prices.analysis_price ending on the last bar strictly before information_date; decimal; null without 31 bars or valid returns.",
    "drawdown_90d": "Last pre-information-date prices.analysis_price / maximum of the prior 90 intervals' 91 prices - 1; decimal (zero or negative); null without 91 bars or a positive peak.",
    "volume_zscore_30d": "Latest pre-information-date prices.volume standardized against the preceding 30 completed sessions; unitless z-score; null if volume history is insufficient or constant.",
    "spy_relative_return_30d": "Stock prior 30-session return minus SPY prices.analysis_price return over the exact same 31 stock trading dates; decimal; null unless SPY has all aligned bars.",
    "sector_relative_return_30d": "Stock prior 30-session return minus mapped sector ETF prices.analysis_price return over the exact same 31 stock trading dates; decimal; null unless the ETF has all aligned bars or no mapping exists.",
    "aggregate_purchase_value": "Sum insider_transactions.transaction_value for qualifying transactions matched to ticker + public_event_day and known by information_date; currency units; null if no valid values.",
    "log_aggregate_purchase_value": "Natural log of aggregate_purchase_value; unitless; null if aggregate is missing or nonpositive.",
    "max_valid_ownership_change_pct": "Person 1 research_events.max_valid_ownership_change_pct when supplied, else maximum insider_transactions.shares / (shares_owned_after - shares) for valid positive prior ownership; ratio; null if unavailable.",
    "any_new_position_flag": "Person 1 research_events.any_new_position_flag when supplied, else whether any qualifying transaction has shares_owned_after - shares == 0; boolean; null when ownership evidence is incomplete.",
    "unique_buyers_7d/30d": "Distinct supported canonical buyers associated with every qualifying transaction filed in inclusive 7/30 calendar days ending on information_date; null with buyer_identity_diagnostics if identity coverage is incomplete; zero only for an empty qualifying window in the supplied data. Names alone never establish identity.",
    "purchase_value_7d/30d": "Sum nonnegative insider_transactions.transaction_value filed in inclusive 7/30 calendar days ending on information_date; currency units; null if no valid values.",
    "recent_purchase_rate": "Count research_events for ticker with information_date in current inclusive 30 calendar days (current event included) / 30; events/day; null only if event dates are unavailable.",
    "historical_purchase_rate": "Count research_events for ticker with information_date in prior 365 calendar days, excluding the current 30 days, / 365; events/day; null only if event dates are unavailable.",
    "has_executive/has_cfo/has_director/role_bucket": "Pass through research_events aggregation from qualifying insider_transactions; boolean or Executive/Director/Other category; nullable where source aggregation is unavailable.",
}
