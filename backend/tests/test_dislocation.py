from __future__ import annotations

import numpy as np
import pandas as pd

from app.quant.dislocation import build_dislocation_scores, empirical_midrank_percentile


TICKERS = [f"T{index:02d}" for index in range(10)]
DATES = pd.bdate_range("2024-01-02", periods=91)
INFO_DATE = DATES[-1] + pd.offsets.BDay(1)


def market_prices() -> pd.DataFrame:
    rows = []
    for index, ticker in enumerate(TICKERS):
        values = np.linspace(100.0, 100.0 * (1 + index / 100), len(DATES))
        if ticker == TICKERS[-1]:
            values[-2:] = [120.0, 90.0]
        rows.extend({"ticker": ticker, "date": day, "analysis_price": value}
                    for day, value in zip(DATES, values))
    rows.extend({"ticker": "XLK", "date": day, "analysis_price": value}
                for day, value in zip(DATES, np.linspace(100.0, 105.0, len(DATES))))
    return pd.DataFrame(rows)


def events(tickers=None) -> pd.DataFrame:
    tickers = tickers or [TICKERS[0]]
    return pd.DataFrame({
        "research_event_id": [f"{ticker}:{INFO_DATE.date()}" for ticker in tickers],
        "ticker": tickers,
        "information_date": [INFO_DATE] * len(tickers),
    })


def score(event_frame=None, prices=None, mapping=None):
    mapping = mapping if mapping is not None else {ticker: "XLK" for ticker in TICKERS}
    return build_dislocation_scores(
        event_frame if event_frame is not None else events(),
        prices if prices is not None else market_prices(),
        TICKERS,
        sector_etf_by_ticker=mapping,
    )


def test_sector_gap_sign_midrank_and_weighted_formula():
    row = score().iloc[0]
    assert row["stock_return_90d"] == 0
    assert np.isclose(row["sector_return_90d"], 0.05)
    assert np.isclose(row["sector_gap90"], 0.05)  # sector outperformance minus stock return
    assert row["sector_gap_percentile"] == 85.0
    assert row["drawdown_90d"] == 0
    assert row["drawdown_magnitude_90d"] == 0
    assert row["drawdown_percentile"] == 45.0
    assert row["dislocation_score"] == 69.0  # 0.60 * 85 + 0.40 * 45
    assert 0 <= row["dislocation_score"] <= 100
    assert row["status"] == "complete"
    severe_drawdown = score(event_frame=events([TICKERS[-1]])).iloc[0]
    assert np.isclose(severe_drawdown["drawdown_90d"], -0.25)
    assert np.isclose(severe_drawdown["drawdown_magnitude_90d"], 0.25)
    assert severe_drawdown["drawdown_percentile"] == 95.0
    assert severe_drawdown["dislocation_score"] > row["dislocation_score"]
    assert 0 <= severe_drawdown["dislocation_score"] <= 100


def test_empirical_midrank_ties_and_boundary_values_are_deterministic():
    refs = [2.0, 1.0, 2.0, 3.0]
    assert empirical_midrank_percentile(2.0, refs) == 50.0
    assert empirical_midrank_percentile(0.0, refs) == 0.0
    assert empirical_midrank_percentile(4.0, refs) == 100.0
    assert empirical_midrank_percentile(2.0, refs) == empirical_midrank_percentile(2.0, refs)


def test_reference_minimum_boundary_and_missing_price_observation():
    complete = score().iloc[0]
    assert complete["sector_gap_reference_count"] == 10
    assert complete["drawdown_reference_count"] == 10
    assert pd.notna(complete["dislocation_score"])

    prices = market_prices()
    prices = prices.loc[~((prices["ticker"] == TICKERS[-1]) & (prices["date"] == DATES[10]))]
    insufficient = score(prices=prices).iloc[0]
    assert insufficient["sector_gap_reference_count"] == 9
    assert insufficient["drawdown_reference_count"] == 9
    assert pd.isna(insufficient["dislocation_score"])
    assert insufficient["status"] == "insufficient_data"
    assert "insufficient_sector_gap_reference" in insufficient["unavailable_reasons"]
    assert "insufficient_drawdown_reference" in insufficient["unavailable_reasons"]
    missing_target = score(event_frame=events([TICKERS[-1]]), prices=prices).iloc[0]
    assert pd.isna(missing_target["stock_return_90d"])
    assert pd.isna(missing_target["drawdown_90d"])
    assert pd.isna(missing_target["dislocation_score"])
    assert "sector_gap_unavailable" in missing_target["unavailable_reasons"]
    assert "drawdown_unavailable" in missing_target["unavailable_reasons"]


def test_missing_sector_mapping_or_unaligned_sector_price_is_not_imputed():
    no_mapping = score(mapping={ticker: "XLK" for ticker in TICKERS[1:]}).iloc[0]
    assert pd.isna(no_mapping["sector_return_90d"])
    assert pd.isna(no_mapping["sector_gap_percentile"])
    assert pd.isna(no_mapping["dislocation_score"])
    assert "sector_gap_unavailable" in no_mapping["unavailable_reasons"]

    prices = market_prices()
    prices = prices.loc[~((prices["ticker"] == "XLK") & (prices["date"] == DATES[20]))]
    unaligned = score(prices=prices).iloc[0]
    assert pd.isna(unaligned["sector_return_90d"])
    assert pd.isna(unaligned["dislocation_score"])


def test_information_date_is_strict_cutoff_and_future_prices_do_not_change_score():
    baseline = score().iloc[0]
    prices = market_prices()
    future_rows = [
        {"ticker": ticker, "date": INFO_DATE, "analysis_price": 100000.0}
        for ticker in [*TICKERS, "XLK"]
    ]
    with_future = score(prices=pd.concat([prices, pd.DataFrame(future_rows)], ignore_index=True)).iloc[0]
    assert with_future["stock_return_90d"] == baseline["stock_return_90d"]
    assert with_future["sector_return_90d"] == baseline["sector_return_90d"]
    assert with_future["dislocation_score"] == baseline["dislocation_score"]


def test_one_result_per_event_includes_unavailable_events_and_is_deterministic():
    event_frame = events([TICKERS[0], "OUTSIDE"])
    first = score(event_frame=event_frame)
    second = score(event_frame=event_frame)
    assert len(first) == 2
    assert first["research_event_id"].is_unique
    assert first["research_event_id"].tolist() == sorted(event_frame["research_event_id"].tolist())
    pd.testing.assert_frame_equal(first, second)
    outside = first.loc[first["ticker"].eq("OUTSIDE")].iloc[0]
    assert pd.isna(outside["dislocation_score"])
    assert outside["status"] == "insufficient_data"
    assert "ticker_not_in_frozen_universe" in outside["unavailable_reasons"]
