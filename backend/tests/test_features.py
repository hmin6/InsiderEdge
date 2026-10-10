from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from app.quant.features import FEATURE_DEFINITIONS, build_event_features
from app.services.events.buyers import BuyerEvidence


def events_frame() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "research_event_id": "ABC:2024-04-01",
            "ticker": "ABC",
            "public_event_day": "2024-04-01",
            "information_date": "2024-03-29",
            "role_bucket": "Executive",
            "has_executive": True,
            "has_cfo": True,
            "has_director": False,
            "max_valid_ownership_change_pct": None,
            "any_new_position_flag": None,
        }
    ])


def transactions_frame() -> pd.DataFrame:
    rows = [
        ("2024-03-29", "2024-04-01", "Alice", 100.0, 10, 20),
        ("2024-03-28", "2024-04-01", "ALICE", 50.0, 5, 5),
        ("2024-03-23", "2024-03-25", "Bob", 25.0, 5, 5),
        ("2024-02-28", "2024-03-01", "Carol", 40.0, 4, 12),
        # This transaction is not public by the event information date.
        ("2024-03-29", "2024-04-01", "Future", 900.0, 9, 18),
    ]
    frame = pd.DataFrame(rows, columns=["filing_date", "public_event_day", "insider_name", "transaction_value", "shares", "shares_owned_after"])
    frame["ticker"] = "ABC"
    frame["transaction_code"] = "P"
    frame["acquired_or_disposed"] = "A"
    frame["derivative_flag"] = False
    frame["is_p0_qualifying"] = True
    # The last row is filed after the information boundary.
    frame.loc[4, "filing_date"] = "2024-04-02"
    return frame


def prices_frame(count: int = 121) -> pd.DataFrame:
    dates = pd.bdate_range("2023-10-01", periods=count + 1)
    rows = []
    for ticker, prices in (
        ("ABC", np.arange(100.0, 100.0 + len(dates))),
        ("SPY", np.arange(200.0, 200.0 + len(dates))),
        ("XLK", np.arange(50.0, 50.0 + len(dates))),
    ):
        rows.extend({"ticker": ticker, "date": date, "analysis_price": price, "volume": 100 + index}
                    for index, (date, price) in enumerate(zip(dates, prices)))
    # The last bar occurs on the information date and must not be used.
    rows.extend([
        {"ticker": ticker, "date": "2024-03-29", "analysis_price": 9999.0, "volume": 99999}
        for ticker in ("ABC", "SPY", "XLK")
    ])
    return pd.DataFrame(rows)


class EventFeatureTests(unittest.TestCase):
    def features(self, event_frame=None, tx_frame=None, market_frame=None, buyer_evidence=None):
        return build_event_features(
            event_frame if event_frame is not None else events_frame(),
            tx_frame if tx_frame is not None else transactions_frame(),
            market_frame if market_frame is not None else prices_frame(),
            sector_etf_by_ticker={"ABC": "XLK"},
            buyer_evidence=buyer_evidence,
        )

    def test_market_returns_volatility_drawdown_and_relative_features(self):
        row = self.features().iloc[0]
        # Last valid pre-filing bar is the session before 2024-03-29.
        self.assertAlmostEqual(row["prior_return_5d"], 5 / 216)
        self.assertAlmostEqual(row["prior_return_30d"], 30 / 191)
        self.assertAlmostEqual(row["prior_return_90d"], 90 / 131)
        self.assertAlmostEqual(row["sector_return_90d"], 90 / 81)
        self.assertGreater(row["prior_volatility_30d"], 0)
        self.assertLessEqual(row["drawdown_90d"], 0)
        self.assertAlmostEqual(row["spy_relative_return_30d"], row["prior_return_30d"] - ((30 / 291)))
        self.assertAlmostEqual(row["sector_relative_return_30d"], row["prior_return_30d"] - (30 / 141))

    def test_event_aggregation_window_boundaries_and_ownership(self):
        tx = transactions_frame().assign(transaction_id=['t0', 't1', 't2', 't3', 't4'])
        evidence = {key: BuyerEvidence((buyer,), 'synthetic transaction association')
                    for key, buyer in zip(tx.transaction_id, ['owner1', 'owner1', 'owner2', 'owner3', 'future'])}
        row = self.features(tx_frame=tx, buyer_evidence=evidence).iloc[0]
        self.assertEqual(row["aggregate_purchase_value"], 150.0)
        self.assertAlmostEqual(row["log_aggregate_purchase_value"], np.log(150.0))
        self.assertAlmostEqual(row["max_valid_ownership_change_pct"], 1.0)
        self.assertTrue(row["any_new_position_flag"])
        self.assertEqual(row["unique_buyers_7d"], 2)  # March 23 is the inclusive first day of the seven-day window.
        self.assertEqual(row["unique_buyers_30d"], 2)
        self.assertEqual(row["purchase_value_7d"], 175.0)
        self.assertEqual(row["purchase_value_30d"], 175.0)
        self.assertTrue(row["has_executive"])
        self.assertTrue(row["has_cfo"])
        self.assertEqual(row["role_bucket"], "Executive")

    def test_missing_or_joint_names_never_establish_buyer_identity(self):
        for names in [None, 'Alice', 'Alice | Bob']:
            tx = transactions_frame().iloc[:1].assign(transaction_id='t0', insider_name=names)
            row = self.features(tx_frame=tx).iloc[0]
            for window in ('7d', '30d'):
                self.assertTrue(pd.isna(row[f'unique_buyers_{window}']))
                diagnostic = row['buyer_identity_diagnostics'][window]
                self.assertEqual(diagnostic['status'], 'unknown')
                self.assertFalse(diagnostic['canonical_identity_verified'])
                self.assertEqual(diagnostic['unknown_transaction_ids'], ['t0'])
                self.assertIn('transaction-associated evidence', diagnostic['reason'])

    def test_supported_multiple_buyers_and_names_are_irrelevant(self):
        tx = transactions_frame().iloc[:2].assign(transaction_id=['t0', 't1'], insider_name='Ambiguous | Names')
        evidence = {'t0': BuyerEvidence(('owner1', 'owner2'), 'verified transaction-level source'),
                    't1': BuyerEvidence(('owner1',), 'verified transaction-level source')}
        row = self.features(tx_frame=tx, buyer_evidence=evidence).iloc[0]
        self.assertEqual(row.unique_buyers_7d, 2)
        self.assertEqual(row.unique_buyers_30d, 2)
        self.assertTrue(row.buyer_identity_diagnostics['30d']['canonical_identity_verified'])
        self.assertEqual(row.buyer_identity_diagnostics['30d']['evidence_sources'], ['verified transaction-level source'])

    def test_partial_buyer_coverage_blocks_only_affected_window(self):
        tx = transactions_frame().iloc[[0, 3]].assign(transaction_id=['recent', 'older'])
        tx.loc[3, 'filing_date'] = '2024-03-10'
        row = self.features(tx_frame=tx, buyer_evidence={
            'recent': BuyerEvidence(('owner1',), 'verified source')}).iloc[0]
        self.assertEqual(row.unique_buyers_7d, 1)
        self.assertTrue(pd.isna(row.unique_buyers_30d))
        self.assertEqual(row.buyer_identity_diagnostics['30d']['unknown_transaction_ids'], ['older'])

    def test_empty_qualifying_window_is_genuine_zero(self):
        tx = transactions_frame().iloc[:1].assign(transaction_id='old', filing_date='2024-01-01')
        row = self.features(tx_frame=tx).iloc[0]
        self.assertEqual(row.unique_buyers_7d, 0)
        self.assertEqual(row.unique_buyers_30d, 0)
        self.assertEqual(row.buyer_identity_diagnostics['30d']['status'], 'no_qualifying_transactions')

    def test_invalid_buyer_evidence_remains_unknown(self):
        tx = transactions_frame().iloc[:1].assign(transaction_id='t0')
        for evidence in ['Alice | Bob', BuyerEvidence((), 'source'), BuyerEvidence(('owner',), ''),
                         BuyerEvidence(('',), 'source')]:
            row = self.features(tx_frame=tx, buyer_evidence={'t0': evidence}).iloc[0]
            self.assertTrue(pd.isna(row.unique_buyers_30d))

    def test_buyer_processing_is_idempotent_and_does_not_mutate_sources(self):
        tx = transactions_frame().assign(transaction_id=['t0', 't1', 't2', 't3', 't4'])
        before = tx.copy(deep=True)
        evidence = {key: BuyerEvidence(('owner1',), 'verified source') for key in tx.transaction_id}
        first = self.features(tx_frame=tx, buyer_evidence=evidence)
        second = self.features(tx_frame=tx, buyer_evidence=evidence)
        pd.testing.assert_frame_equal(first, second)
        pd.testing.assert_frame_equal(tx, before)
        self.assertEqual(first.iloc[0].unique_buyers_30d, 1)

    def test_multiple_raw_transactions_still_emit_one_ml_event_row(self):
        output = self.features()
        self.assertEqual(len(output), 1)
        self.assertEqual(output["research_event_id"].tolist(), ["ABC:2024-04-01"])
        self.assertFalse(output["research_event_id"].duplicated().any())

    def test_missing_history_is_explicit(self):
        short_prices = prices_frame(count=10)
        row = self.features(market_frame=short_prices).iloc[0]
        self.assertTrue(pd.notna(row["prior_return_5d"]))
        for column in ("prior_return_30d", "prior_return_90d", "sector_return_90d", "prior_volatility_30d", "drawdown_90d", "volume_zscore_30d", "spy_relative_return_30d", "sector_relative_return_30d"):
            self.assertTrue(pd.isna(row[column]), column)

    def test_missing_ownership_inputs_remain_missing(self):
        transactions = transactions_frame()
        transactions["shares"] = np.nan
        transactions["shares_owned_after"] = np.nan
        row = self.features(tx_frame=transactions).iloc[0]
        self.assertTrue(pd.isna(row["max_valid_ownership_change_pct"]))
        self.assertTrue(pd.isna(row["any_new_position_flag"]))

    def test_relative_returns_require_aligned_trading_dates(self):
        prices = prices_frame()
        cutoff_dates = pd.to_datetime(prices.loc[(prices["ticker"] == "ABC") & (pd.to_datetime(prices["date"]) < "2024-03-29"), "date"])
        stock_window = cutoff_dates.tail(31)
        missing_date = stock_window.iloc[10]
        prices = prices.loc[~((prices["ticker"] == "SPY") & (pd.to_datetime(prices["date"]) == missing_date))]
        row = self.features(market_frame=prices).iloc[0]
        self.assertTrue(pd.isna(row["spy_relative_return_30d"]))
        self.assertTrue(pd.notna(row["sector_relative_return_30d"]))

    def test_transaction_and_market_temporal_leakage_excluded(self):
        tx = transactions_frame()
        tx.loc[len(tx)] = ["2024-03-30", "2024-04-01", "Late filing", 5000, 5, 10, "ABC", "P", "A", False, True]
        row = self.features(tx_frame=tx).iloc[0]
        self.assertEqual(row["aggregate_purchase_value"], 150.0)
        self.assertLess(row["prior_return_30d"], 1)
        self.assertLess(row["volume_zscore_30d"], 100)

    def test_precomputed_ownership_aggregation_is_authoritative(self):
        events = events_frame()
        events.loc[0, "max_valid_ownership_change_pct"] = 0.25
        events.loc[0, "any_new_position_flag"] = False
        row = self.features(event_frame=events).iloc[0]
        self.assertEqual(row["max_valid_ownership_change_pct"], 0.25)
        self.assertFalse(row["any_new_position_flag"])

    def test_feature_formulas_and_missingness_are_documented(self):
        for feature in ("prior_return_5d", "prior_return_30d", "prior_return_90d", "sector_return_90d", "prior_volatility_30d", "drawdown_90d", "volume_zscore_30d", "aggregate_purchase_value", "recent_purchase_rate", "historical_purchase_rate"):
            self.assertIn(feature, FEATURE_DEFINITIONS)
            definition = FEATURE_DEFINITIONS[feature].lower()
            self.assertTrue("null" in definition or "nullable" in definition or "0 if none" in definition)


if __name__ == "__main__":
    unittest.main()
