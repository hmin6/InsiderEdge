from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from app.quant.event_study import build_event_studies


ALPHA = 0.0015
BETA = 1.2
EVENT_INDEX = 130


def market_fixture(
    *,
    count: int = 240,
    event_index: int = EVENT_INDEX,
    residuals: dict[int, float] | None = None,
    missing_stock_indices: set[int] | None = None,
    missing_spy_indices: set[int] | None = None,
) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    """Build prices from known per-session returns and optional AR shocks."""
    dates = pd.bdate_range("2024-01-02", periods=count)
    market_returns = np.zeros(count, dtype=float)
    for index in range(1, count):
        market_returns[index] = 0.01 if index % 2 else -0.005
    stock_returns = ALPHA + BETA * market_returns
    for offset, shock in (residuals or {}).items():
        stock_returns[event_index + offset] += shock

    spy = np.empty(count, dtype=float)
    stock = np.empty(count, dtype=float)
    spy[0], stock[0] = 200.0, 100.0
    for index in range(1, count):
        spy[index] = spy[index - 1] * (1 + market_returns[index])
        stock[index] = stock[index - 1] * (1 + stock_returns[index])

    rows = [
        {"ticker": "ABC", "date": date, "analysis_price": price}
        for index, (date, price) in enumerate(zip(dates, stock))
        if index not in (missing_stock_indices or set())
    ]
    rows.extend(
        {"ticker": "SPY", "date": date, "analysis_price": price}
        for index, (date, price) in enumerate(zip(dates, spy))
        if index not in (missing_spy_indices or set())
    )
    return pd.DataFrame(rows), dates


def event_frame(event_index: int = EVENT_INDEX, event_id: str = "ABC:event") -> pd.DataFrame:
    day = pd.Timestamp("2024-01-02") + pd.offsets.BDay(event_index)
    return pd.DataFrame([{
        "research_event_id": event_id,
        "ticker": "ABC",
        "public_event_day": day,
        "information_date": day - pd.Timedelta(days=1),
    }])


class EventStudyTests(unittest.TestCase):
    def run_study(self, prices=None, events=None):
        market, _ = market_fixture() if prices is None else (prices, None)
        return build_event_studies(events if events is not None else event_frame(), market)

    def test_hand_calculable_market_model_and_car_window_boundaries(self):
        shocks = {-121: 0.30, -20: 0.25,
                  0: 0.01, 1: -0.02, 4: 0.03, 5: 0.07,
                  29: 0.04, 30: -0.08, 89: 0.05, 90: 0.09}
        prices, _ = market_fixture(residuals=shocks)
        result = self.run_study(prices=prices).iloc[0]

        # The t=-121 and t=-20 shocks are outside [-120, -21], so they do not
        # contaminate the fitted coefficients.
        self.assertAlmostEqual(result["alpha"], ALPHA, places=8)
        self.assertAlmostEqual(result["beta"], BETA, places=8)
        self.assertEqual(result["estimation_observation_count"], 100)
        self.assertAlmostEqual(result["car5"], 0.01 - 0.02 + 0.03, places=8)
        self.assertAlmostEqual(result["car30"], 0.01 - 0.02 + 0.03 + 0.07 + 0.04, places=8)
        self.assertAlmostEqual(result["car90"], 0.01 - 0.02 + 0.03 + 0.07 + 0.04 - 0.08 + 0.05, places=8)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["car5_status"], "complete")
        self.assertEqual(result["car30_status"], "complete")
        self.assertEqual(result["car90_status"], "complete")

    def test_estimation_minimum_is_60_and_fewer_observations_are_unavailable(self):
        exactly_60, _ = market_fixture(event_index=81)
        sufficient = self.run_study(prices=exactly_60, events=event_frame(81)).iloc[0]
        self.assertEqual(sufficient["estimation_observation_count"], 60)
        self.assertIsNotNone(sufficient["alpha"])

        only_59, _ = market_fixture(event_index=80)
        insufficient = self.run_study(prices=only_59, events=event_frame(80)).iloc[0]
        self.assertEqual(insufficient["estimation_observation_count"], 59)
        self.assertEqual(insufficient["status"], "insufficient_estimation_data")
        self.assertIsNone(insufficient["car5"])
        self.assertEqual(insufficient["car5_status"], "unavailable")
        self.assertIn("insufficient_estimation_sample", insufficient["car5_missing_reasons"])

    def test_zero_variance_benchmark_returns_make_model_and_cars_unavailable(self):
        prices, _ = market_fixture()
        prices.loc[prices["ticker"].eq("SPY"), "analysis_price"] = 200.0
        result = self.run_study(prices=prices).iloc[0]

        self.assertEqual(result["status"], "invalid_estimation_data")
        self.assertIn("zero_benchmark_variance", result["missing_reasons"][0])
        self.assertIsNone(result["alpha"])
        self.assertIsNone(result["beta"])
        for horizon in ("car5", "car30", "car90"):
            self.assertIsNone(result[horizon])
            self.assertEqual(result[f"{horizon}_status"], "unavailable")
            self.assertIn("invalid_estimation_data", result[f"{horizon}_missing_reasons"])

    def test_estimation_bounds_include_minus_120_and_minus_21_but_exclude_neighbors(self):
        baseline_prices, _ = market_fixture()
        outside_prices, _ = market_fixture(residuals={-121: 0.7, -20: -0.6})
        inside_prices, _ = market_fixture(residuals={-120: 0.08, -21: -0.05})
        baseline = self.run_study(prices=baseline_prices).iloc[0]
        outside = self.run_study(prices=outside_prices).iloc[0]
        inside = self.run_study(prices=inside_prices).iloc[0]
        self.assertEqual(inside["estimation_observation_count"], 100)
        self.assertAlmostEqual(outside["alpha"], baseline["alpha"], places=8)
        self.assertAlmostEqual(outside["beta"], baseline["beta"], places=8)
        self.assertAlmostEqual(outside["car5"], baseline["car5"], places=8)
        self.assertNotAlmostEqual(inside["alpha"], baseline["alpha"], places=8)

    def test_missing_or_unpaired_estimation_observations_are_not_filled(self):
        prices, _ = market_fixture(missing_stock_indices={EVENT_INDEX - 50})
        result = self.run_study(prices=prices).iloc[0]
        # A missing stock bar invalidates the return ending on that date and
        # the next adjacent date, rather than creating a two-session return.
        self.assertEqual(result["estimation_observation_count"], 98)
        self.assertIsNotNone(result["alpha"])

        unpaired, _ = market_fixture(missing_spy_indices={EVENT_INDEX - 50})
        unpaired_result = self.run_study(prices=unpaired).iloc[0]
        self.assertEqual(unpaired_result["estimation_observation_count"], 98)

    def test_shared_missing_session_is_not_detectable_without_external_calendar(self):
        missing_index = EVENT_INDEX - 50
        prices, _ = market_fixture(
            missing_stock_indices={missing_index},
            missing_spy_indices={missing_index},
        )
        missing_date = pd.Timestamp("2024-01-02") + pd.offsets.BDay(missing_index)
        self.assertFalse(prices["date"].eq(missing_date).any())

        # A complete result here means complete relative to the supplied date
        # union only. Since the omitted session is absent from both symbols,
        # this function has no calendar evidence that a gap exists; it cannot
        # validate the CAR against the missing session without an exchange calendar.
        result = self.run_study(prices=prices).iloc[0]
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["estimation_observation_count"], 100)

    def test_missing_event_window_data_makes_only_affected_horizons_unavailable(self):
        prices, dates = market_fixture(missing_stock_indices={EVENT_INDEX + 5})
        result = self.run_study(prices=prices).iloc[0]
        self.assertIsNotNone(result["car5"])
        self.assertEqual(result["car5_status"], "complete")
        self.assertIsNone(result["car30"])
        self.assertIsNone(result["car90"])
        self.assertEqual(result["car30_status"], "unavailable")
        self.assertIn("missing_paired_return_t5", result["car30_missing_reasons"])
        self.assertEqual(result["status"], "partial")

        # A missing final session leaves CAR30 complete but CAR90 unavailable.
        prices, _ = market_fixture(missing_stock_indices={EVENT_INDEX + 89})
        result = self.run_study(prices=prices).iloc[0]
        self.assertIsNotNone(result["car30"])
        self.assertIsNone(result["car90"])
        self.assertIn("missing_paired_return_t89", result["car90_missing_reasons"])

    def test_event_date_is_t0_and_information_date_must_precede_it(self):
        shocks = {0: 0.025, 1: 0.01}
        prices, dates = market_fixture(residuals=shocks)
        event = event_frame()
        event.loc[0, "public_event_day"] = dates[EVENT_INDEX]
        event.loc[0, "information_date"] = dates[EVENT_INDEX] - pd.Timedelta(days=1)
        result = self.run_study(prices=prices, events=event).iloc[0]
        self.assertAlmostEqual(result["car5"], 0.035, places=8)

        event.loc[0, "information_date"] = dates[EVENT_INDEX]
        invalid = self.run_study(prices=prices, events=event).iloc[0]
        self.assertEqual(invalid["status"], "invalid_event_timing")
        self.assertIn("public_event_day_not_after_information_date", invalid["missing_reasons"])

    def test_future_event_outcomes_do_not_change_estimated_model(self):
        original_prices, _ = market_fixture()
        future_prices, _ = market_fixture(residuals={0: 0.05, 10: -0.04, 89: 0.03})
        original = self.run_study(prices=original_prices).iloc[0]
        changed = self.run_study(prices=future_prices).iloc[0]
        self.assertAlmostEqual(original["alpha"], changed["alpha"], places=10)
        self.assertAlmostEqual(original["beta"], changed["beta"], places=10)
        self.assertNotAlmostEqual(original["car30"], changed["car30"], places=8)

    def test_duplicate_rows_and_malformed_price_dates_are_rejected(self):
        prices, _ = market_fixture()
        with self.assertRaisesRegex(ValueError, "duplicate ticker/date"):
            self.run_study(prices=pd.concat([prices, prices.iloc[[0]]], ignore_index=True))

        malformed = prices.copy()
        malformed["date"] = malformed["date"].astype(object)
        malformed.loc[malformed.index[0], "date"] = "not-a-date"
        with self.assertRaisesRegex(ValueError, "malformed or missing dates"):
            self.run_study(prices=malformed)

    def test_invalid_prices_are_explicitly_treated_as_missing(self):
        prices, _ = market_fixture()
        event_date = event_frame().loc[0, "public_event_day"]
        mask = prices["ticker"].eq("ABC") & pd.to_datetime(prices["date"]).eq(event_date)
        prices.loc[mask, "analysis_price"] = 0
        result = self.run_study(prices=prices).iloc[0]
        self.assertIsNone(result["car5"])
        self.assertIn("missing_paired_return_t0", result["car5_missing_reasons"])

    def test_missing_columns_and_duplicate_event_ids_are_rejected(self):
        prices, _ = market_fixture()
        with self.assertRaisesRegex(ValueError, "prices missing required columns"):
            build_event_studies(event_frame(), prices.drop(columns=["analysis_price"]))
        duplicate_events = pd.concat([event_frame(), event_frame()], ignore_index=True)
        with self.assertRaisesRegex(ValueError, "unique research_event_id"):
            build_event_studies(duplicate_events, prices)

    def test_multiple_events_return_one_row_each_in_deterministic_order(self):
        prices, _ = market_fixture()
        events = pd.concat([
            event_frame(145, "ABC:later"),
            event_frame(135, "ABC:earlier"),
        ], ignore_index=True)
        first = build_event_studies(events, prices)
        second = build_event_studies(events.iloc[::-1], prices.sample(frac=1, random_state=17))
        self.assertEqual(len(first), 2)
        self.assertEqual(first["research_event_id"].tolist(), ["ABC:earlier", "ABC:later"])
        self.assertEqual(first["research_event_id"].tolist(), second["research_event_id"].tolist())
        self.assertFalse(first["research_event_id"].duplicated().any())

    def test_missing_event_history_and_missing_information_are_explicit(self):
        prices, _ = market_fixture(count=20, event_index=15)
        event = event_frame(15)
        result = self.run_study(prices=prices, events=event).iloc[0]
        self.assertEqual(result["status"], "insufficient_estimation_data")
        self.assertIn("fewer_than_60_paired_estimation_returns", result["missing_reasons"])

        event.loc[0, "information_date"] = None
        result = self.run_study(prices=prices, events=event).iloc[0]
        self.assertEqual(result["status"], "missing_information_date")


if __name__ == "__main__":
    unittest.main()
