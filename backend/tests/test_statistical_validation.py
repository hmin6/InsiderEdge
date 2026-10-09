from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from app.quant.event_study import build_event_studies
from app.quant.statistical_validation import (
    DEFAULT_BOOTSTRAP_RESAMPLES,
    DEFAULT_BOOTSTRAP_SEED,
    DEFAULT_RANDOMIZATION_REPLICATES,
    DEFAULT_RANDOMIZATION_SEED,
    _bootstrap_component,
    _combine_result,
    _pseudo_candidates,
    _randomization_component,
    build_statistical_validations,
    select_comparable_events,
)


def _selection_fixture(
    *,
    same_sector_role: int = 9,
    same_sector_other_role: int = 1,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DatetimeIndex, str]:
    sessions = pd.bdate_range("2020-01-02", periods=300)
    focal_id = "FOCAL:event"
    focal_info = sessions[250]
    rows: list[dict[str, object]] = [{
        "research_event_id": focal_id,
        "ticker": "FOCAL",
        "public_event_day": sessions[251],
        "information_date": focal_info,
        "role_bucket": "Director",
    }]
    study_rows: list[dict[str, object]] = []
    company_rows: list[dict[str, object]] = [{"ticker": "FOCAL", "sector": "Technology"}]

    def add_event(event_id: str, ticker: str, index: int, role: str, *, info_offset: int = -1,
                  car30: float = 0.02, status: str = "complete", sector: str = "Technology") -> None:
        day = sessions[index]
        rows.append({
            "research_event_id": event_id,
            "ticker": ticker,
            "public_event_day": day,
            "information_date": day + pd.Timedelta(days=info_offset),
            "role_bucket": role,
        })
        study_rows.append({"research_event_id": event_id, "car30": car30, "car30_status": status})
        if ticker not in {row["ticker"] for row in company_rows}:
            company_rows.append({"ticker": ticker, "sector": sector})

    for index in range(same_sector_role):
        add_event(f"ROLE:{index}", f"R{index}", 100 + index, "Director", car30=(-1.0 if index % 2 else 100.0))
    for index in range(same_sector_other_role):
        add_event(f"OTHER:{index}", f"O{index}", 120 + index, "Executive", car30=float(index))
    # Public information on the focal information date is not strictly earlier.
    add_event(
        "SAME_INFO_DATE", "LATE", 130, "Director",
        info_offset=int((sessions[250] - sessions[130]).days),
    )
    # Its CAR30 ends exactly at the focal information date, so it is too late.
    add_event("ENDS_AT_CUTOFF", "CUTOFF", 221, "Director")
    add_event("UNAVAILABLE_CAR", "UNAVAILABLE", 140, "Director", status="unavailable")
    add_event("OTHER_SECTOR", "FINANCE", 150, "Director", sector="Finance")
    return (
        pd.DataFrame(rows),
        pd.DataFrame(study_rows),
        pd.DataFrame(company_rows),
        sessions,
        focal_id,
    )


def _market_fixture() -> tuple[pd.DataFrame, pd.DatetimeIndex, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    sessions = pd.bdate_range("2022-01-03", periods=500)
    tickers = ["CO"]
    market_returns = np.zeros(len(sessions), dtype=float)
    market_returns[1:] = np.where(np.arange(1, len(sessions)) % 2 == 0, -0.005, 0.01)
    spy = np.empty(len(sessions), dtype=float)
    spy[0] = 200.0
    for index in range(1, len(sessions)):
        spy[index] = spy[index - 1] * (1.0 + market_returns[index])

    price_rows = [
        {"ticker": "SPY", "date": date, "analysis_price": spy[index]}
        for index, date in enumerate(sessions)
    ]
    for ticker_index, ticker in enumerate(tickers):
        stock = np.empty(len(sessions), dtype=float)
        stock[0] = 50.0 + ticker_index
        for index in range(1, len(sessions)):
            stock_return = 0.001 + 1.1 * market_returns[index] + ticker_index * 0.00001
            stock[index] = stock[index - 1] * (1.0 + stock_return)
        price_rows.extend(
            {"ticker": ticker, "date": date, "analysis_price": stock[index]}
            for index, date in enumerate(sessions)
        )

    events = []
    for index in range(10):
        ticker = "CO"
        day = sessions[160 + index]
        events.append({
            "research_event_id": f"{ticker}:event:{index}",
            "ticker": ticker,
            "public_event_day": day,
            "information_date": day - pd.Timedelta(days=1),
            "role_bucket": "Executive",
        })
    focal_day = sessions[400]
    events.append({
        "research_event_id": "FOCAL:event",
        "ticker": "FOCAL",
        "public_event_day": sessions[401],
        "information_date": focal_day - pd.Timedelta(days=1),
        "role_bucket": "Executive",
    })
    companies = pd.DataFrame(
        [{"ticker": ticker, "sector": "Technology"} for ticker in tickers]
        + [{"ticker": "FOCAL", "sector": "Technology"}]
    )
    research_events = pd.DataFrame(events)
    # The focal event intentionally has no event-study row: its future CAR30 is
    # not required for validating its historical cohort.
    studies = build_event_studies(research_events.iloc[:-1], pd.DataFrame(price_rows), sessions)
    return pd.DataFrame(price_rows), sessions, research_events, companies, studies


class ComparableSelectorTests(unittest.TestCase):
    def test_sector_fallback_strict_cutoffs_minimum_and_car_magnitude_independence(self):
        events, studies, companies, sessions, focal_id = _selection_fixture()
        selected = select_comparable_events(events, studies, companies, sessions)
        focal = selected.loc[selected["research_event_id"].eq(focal_id)].iloc[0]
        self.assertEqual(focal["status"], "complete")
        self.assertEqual(focal["cohort_definition"], "same_sector")
        self.assertEqual(focal["same_sector_role_eligible_count"], 9)
        self.assertEqual(focal["comparable_event_count"], 10)
        self.assertNotIn("SAME_INFO_DATE", focal["comparable_event_ids"])
        self.assertNotIn("ENDS_AT_CUTOFF", focal["comparable_event_ids"])
        self.assertNotIn("UNAVAILABLE_CAR", focal["comparable_event_ids"])
        self.assertNotIn("OTHER_SECTOR", focal["comparable_event_ids"])

        changed = studies.copy()
        changed["car30"] = np.where(changed["car30"].gt(0), -1e9, 1e9)
        second = select_comparable_events(events, changed, companies, sessions)
        second_focal = second.loc[second["research_event_id"].eq(focal_id)].iloc[0]
        self.assertEqual(focal["comparable_event_ids"], second_focal["comparable_event_ids"])

    def test_same_sector_role_is_preferred_at_ten_and_under_ten_is_insufficient(self):
        events, studies, companies, sessions, focal_id = _selection_fixture(
            same_sector_role=10, same_sector_other_role=3
        )
        result = select_comparable_events(events, studies, companies, sessions)
        focal = result.loc[result["research_event_id"].eq(focal_id)].iloc[0]
        self.assertEqual(focal["cohort_definition"], "same_sector_and_role")
        self.assertEqual(focal["comparable_event_count"], 10)
        self.assertTrue(all(event_id.startswith("ROLE:") for event_id in focal["comparable_event_ids"]))

        events, studies, companies, sessions, focal_id = _selection_fixture(
            same_sector_role=8, same_sector_other_role=1
        )
        result = select_comparable_events(events, studies, companies, sessions)
        focal = result.loc[result["research_event_id"].eq(focal_id)].iloc[0]
        self.assertEqual(focal["status"], "insufficient_data")
        self.assertEqual(focal["comparable_event_count"], 9)
        self.assertIn("fewer_than_10_eligible_comparable_events", focal["missing_reasons"])


class BootstrapTests(unittest.TestCase):
    def test_bootstrap_interval_support_and_seeded_reproducibility(self):
        self.assertEqual(DEFAULT_BOOTSTRAP_RESAMPLES, 1_000)
        self.assertEqual(DEFAULT_BOOTSTRAP_SEED, 13)
        values = [-0.05, -0.02, -0.01, -0.005, 0.0, 0.005, 0.01, 0.02, 0.03, 0.04]
        first = _bootstrap_component(values, n_resamples=1_000, seed=13)
        second = _bootstrap_component(values, n_resamples=1_000, seed=13)
        self.assertEqual(first, second)
        self.assertAlmostEqual(first["mean_car30"], 0.002)
        self.assertAlmostEqual(first["bootstrap_ci_lower"], -0.0135)
        self.assertAlmostEqual(first["bootstrap_ci_upper"], 0.0165)
        self.assertEqual(first["bootstrap_q"], 0.605)
        self.assertAlmostEqual(first["B_support"], 21.0)

    def test_zero_bootstrap_means_use_strictly_greater_than_zero_for_q(self):
        result = _bootstrap_component([0.0] * 10, n_resamples=50, seed=4)
        self.assertEqual(result["bootstrap_q"], 0.0)
        self.assertEqual(result["B_support"], 0.0)


class RandomizationTests(unittest.TestCase):
    def test_upper_tail_counts_ties_and_uses_finite_sample_correction(self):
        event_ids = [f"event-{index}" for index in range(10)]
        result = _randomization_component(
            [0.1] * 10,
            {event_id: [f"pseudo-{index}"] for index, event_id in enumerate(event_ids)},
            {f"pseudo-{index}": 0.1 for index in range(10)},
            n_replicates=25,
            seed=5,
            max_attempts=25,
        )
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["T_obs"], 0.1)
        self.assertEqual(result["randomization_exceedance_count"], 25)
        self.assertEqual(result["randomization_p_value"], (1 + 25) / (25 + 1))
        self.assertEqual(result["P_support"], 0.0)

    def test_incomplete_draws_are_rejected_and_full_valid_count_is_required(self):
        result = _randomization_component(
            [0.1] * 10,
            {f"event-{index}": ["missing"] for index in range(10)},
            {"missing": None},
            n_replicates=4,
            seed=2,
            max_attempts=7,
        )
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["randomization_attempted_count"], 7)
        self.assertEqual(result["randomization_valid_replicate_count"], 0)
        self.assertIn("full_valid_randomization_replicate_count_not_achieved", result["missing_reasons"])

    def test_mixed_candidate_pool_rejects_incomplete_draws_until_full_quota(self):
        event_ids = [f"event-{index}" for index in range(10)]
        complete_values = {f"complete-{index}": 0.1 for index in range(10)}
        mixed_values = {
            **complete_values,
            **{f"incomplete-{index}": None for index in range(10)},
        }
        mixed_pools = {
            event_id: [f"complete-{index}", f"incomplete-{index}"]
            for index, event_id in enumerate(event_ids)
        }
        filtered_pools = {
            event_id: [f"complete-{index}"]
            for index, event_id in enumerate(event_ids)
        }

        # The full-pool path rejects any draw containing an incomplete outcome;
        # filtering first yields the same conditional distribution here because
        # each event has exactly one complete candidate (a degenerate example).
        rejected_draws = _randomization_component(
            [0.1] * 10,
            mixed_pools,
            mixed_values,
            n_replicates=32,
            seed=27,
            max_attempts=100_000,
        )
        filtered_draws = _randomization_component(
            [0.1] * 10,
            filtered_pools,
            complete_values,
            n_replicates=32,
            seed=27,
            max_attempts=32,
        )

        self.assertEqual(rejected_draws["status"], "complete")
        self.assertEqual(rejected_draws["randomization_valid_replicate_count"], 32)
        self.assertGreater(rejected_draws["randomization_attempted_count"], 32)
        self.assertEqual(filtered_draws["status"], "complete")
        self.assertEqual(filtered_draws["randomization_attempted_count"], 32)
        self.assertEqual(rejected_draws["randomization_p_value"], filtered_draws["randomization_p_value"])
        self.assertEqual(rejected_draws["randomization_exceedance_count"], 32)

    def test_date_candidates_exclude_actual_events_and_obey_strict_focal_cutoff(self):
        prices, sessions, events, companies, studies = _market_fixture()
        selected = select_comparable_events(events, studies, companies, sessions)
        focal = selected.loc[selected["research_event_id"].eq("FOCAL:event")].iloc[0]
        all_events = events.copy()
        all_events["ticker"] = all_events["ticker"].astype("string").str.upper()
        all_events["public_event_day"] = pd.to_datetime(all_events["public_event_day"])
        all_events["information_date"] = pd.to_datetime(all_events["information_date"])
        prepared = all_events
        cohort = prepared.loc[prepared["research_event_id"].isin(focal["comparable_event_ids"])]
        broken_date = sessions[220]
        broken_prices = prices.copy()
        broken_mask = broken_prices["ticker"].eq("CO") & pd.to_datetime(broken_prices["date"]).eq(broken_date)
        broken_prices.loc[broken_mask, "analysis_price"] = np.nan
        pools, values, error = _pseudo_candidates(
            cohort, prepared, broken_prices, list(sessions), focal["information_date"]
        )
        self.assertIsNone(error)
        self.assertTrue(values)
        actual = {
            f"pseudo:{row.ticker}:{pd.Timestamp(row.public_event_day).date().isoformat()}"
            for row in cohort.itertuples(index=False)
        }
        for candidate_ids in pools.values():
            self.assertTrue(actual.isdisjoint(candidate_ids))
            for candidate_id in candidate_ids:
                date = pd.Timestamp(str(candidate_id).rsplit(":", 1)[1])
                index = sessions.get_loc(date)
                self.assertLess(sessions[index + 29], focal["information_date"])
        missing_candidate_id = f"pseudo:CO:{broken_date.date().isoformat()}"
        self.assertIsNone(values[missing_candidate_id])
        self.assertNotIn(missing_candidate_id, pools["CO:event:0"])

    def test_full_pipeline_is_reproducible_and_does_not_require_focal_car30(self):
        prices, sessions, events, companies, studies = _market_fixture()
        self.assertNotIn("FOCAL:event", set(studies["research_event_id"]))
        first = build_statistical_validations(
            events, studies, companies, prices, sessions,
            bootstrap_seed=41,
            randomization_seed=42,
        )
        second = build_statistical_validations(
            events, studies, companies, prices, sessions,
            bootstrap_seed=41,
            randomization_seed=42,
        )
        focal = first.loc[first["research_event_id"].eq("FOCAL:event")].iloc[0]
        focal_again = second.loc[second["research_event_id"].eq("FOCAL:event")].iloc[0]
        self.assertEqual(focal["status"], "complete")
        self.assertEqual(focal["comparable_event_count"], 10)
        self.assertEqual(focal["randomization_replicates_requested"], DEFAULT_RANDOMIZATION_REPLICATES)
        self.assertEqual(focal["randomization_seed"], 42)
        self.assertEqual(focal["randomization_valid_replicate_count"], 1_000)
        self.assertEqual(focal["randomization_p_value"], focal_again["randomization_p_value"])
        self.assertEqual(focal["bootstrap_ci_lower"], focal_again["bootstrap_ci_lower"])
        self.assertAlmostEqual(
            focal["statistical_score"],
            0.5 * focal["B_support"] + 0.5 * focal["P_support"],
        )

    def test_randomization_failure_preserves_bootstrap_and_leaves_score_null(self):
        sessions = pd.bdate_range("2022-01-03", periods=500)
        tickers = [f"CO{i:02d}" for i in range(10)]
        rows = []
        market_returns = np.zeros(len(sessions), dtype=float)
        market_returns[1:] = np.where(np.arange(1, len(sessions)) % 2 == 0, -0.005, 0.01)
        for ticker in ["SPY", *tickers]:
            prices = np.empty(len(sessions), dtype=float)
            prices[0] = 100.0
            for index in range(1, len(sessions)):
                returns = market_returns[index] if ticker == "SPY" else 0.001 + 1.1 * market_returns[index]
                prices[index] = prices[index - 1] * (1.0 + returns)
            rows.extend({"ticker": ticker, "date": date, "analysis_price": prices[i]}
                        for i, date in enumerate(sessions))
        events = pd.DataFrame([
            {
                "research_event_id": f"{ticker}:event",
                "ticker": ticker,
                "public_event_day": sessions[121],
                "information_date": sessions[121] - pd.Timedelta(days=1),
                "role_bucket": "Executive",
            }
            for ticker in tickers
        ] + [{
            "research_event_id": "FOCAL:event",
            "ticker": "FOCAL",
            "public_event_day": sessions[152],
            "information_date": sessions[151],
            "role_bucket": "Executive",
        }])
        companies = pd.DataFrame(
            [{"ticker": ticker, "sector": "Technology"} for ticker in [*tickers, "FOCAL"]]
        )
        prices = pd.DataFrame(rows)
        studies = build_event_studies(events.iloc[:-1], prices, sessions)
        result = build_statistical_validations(
            events, studies, companies, prices, sessions,
        )
        focal = result.loc[result["research_event_id"].eq("FOCAL:event")].iloc[0]
        self.assertEqual(focal["bootstrap_status"], "complete")
        self.assertIsNotNone(focal["bootstrap_ci_lower"])
        self.assertEqual(focal["randomization_status"], "unavailable")
        self.assertIsNone(focal["P_support"])
        self.assertIsNone(focal["statistical_score"])
        self.assertEqual(focal["status"], "partial")

    def test_same_ticker_year_candidates_can_be_reused_and_overlap(self):
        prices, sessions, events, companies, studies = _market_fixture()
        events = pd.concat([
            events,
            pd.DataFrame([{
                "research_event_id": "CO00:second-event",
                "ticker": "CO",
                "public_event_day": sessions[180],
                "information_date": sessions[180] - pd.Timedelta(days=1),
                "role_bucket": "Executive",
            }]),
        ], ignore_index=True)
        companies = companies.drop_duplicates("ticker")
        extra_study = build_event_studies(events.iloc[[-1]], prices, sessions)
        studies = pd.concat([studies, extra_study], ignore_index=True)
        selected = select_comparable_events(events, studies, companies, sessions)
        focal = selected.loc[selected["research_event_id"].eq("FOCAL:event")].iloc[0]
        cohort = events.loc[events["research_event_id"].isin(focal["comparable_event_ids"])]
        pools, _, error = _pseudo_candidates(
            cohort, events, prices, list(sessions), focal["information_date"]
        )
        self.assertIsNone(error)
        self.assertIn("CO:event:0", pools)
        self.assertIn("CO00:second-event", pools)
        self.assertEqual(pools["CO:event:0"], pools["CO00:second-event"])
        candidate_dates = [pd.Timestamp(candidate.rsplit(":", 1)[1]) for candidate in pools["CO:event:0"]]
        candidate_positions = [sessions.get_loc(date) for date in candidate_dates]
        self.assertTrue(any(right - left == 1 for left, right in zip(candidate_positions, candidate_positions[1:])))

    def test_randomization_result_is_preserved_when_bootstrap_fails(self):
        selection = pd.Series({
            "research_event_id": "FOCAL:event",
            "ticker": "FOCAL",
            "information_date": pd.Timestamp("2024-01-02"),
            "comparable_event_ids": [f"event-{index}" for index in range(10)],
            "comparable_event_count": 10,
            "cohort_definition": "same_sector",
        })
        bootstrap = {"status": "unavailable", "missing_reasons": ["bootstrap_calculation_failed"]}
        randomization = {
            "status": "complete",
            "randomization_p_value": 0.02,
            "P_support": 80.0,
            "randomization_missing_reasons": [],
            "missing_reasons": [],
        }
        result = _combine_result(selection, bootstrap, randomization, mean_car30=0.05)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["randomization_p_value"], 0.02)
        self.assertEqual(result["P_support"], 80.0)
        self.assertEqual(result["mean_car30"], 0.05)
        self.assertIsNone(result["B_support"])
        self.assertIsNone(result["statistical_score"])


if __name__ == "__main__":
    unittest.main()
