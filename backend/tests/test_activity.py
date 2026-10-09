from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.quant.activity import (
    MIN_ACTIVITY_REFERENCE,
    _empirical_percentile,
    build_activity_scores,
)


def fixture_frames(start: date, end: date, ticker: str = "AAA", sector: str | None = "Technology"):
    event_rows = []
    transaction_rows = []
    identities = {}
    cik = str(1_000_000_000 + sum(map(ord, ticker)))
    day = start
    while day <= end:
        event_id = f"{ticker}:{day.isoformat()}"
        transaction_id = f"tx:{event_id}"
        event_rows.append({
            "research_event_id": event_id,
            "ticker": ticker,
            "public_event_day": day + timedelta(days=1),
            "information_date": day,
            "source_transaction_count": 1,
            "source_filing_count": 1,
            "aggregate_purchase_value": None,
            "unique_buyer_count": 1,
            "role_bucket": "Other",
            "has_executive": False,
            "has_director": False,
            "has_other": True,
            "has_cfo": None,
            "max_valid_ownership_change_pct": None,
            "any_new_position_flag": None,
            "feature_metadata": None,
        })
        transaction_rows.append({
            "transaction_id": transaction_id,
            "canonical_transaction_key": transaction_id,
            "accession_number": f"accession:{event_id}",
            "source_type": "bulk",
            "document_type": "4",
            "ticker": ticker,
            "cik": cik,
            "company_name": f"Synthetic {ticker}",
            "insider_role": "Other",
            "transaction_date": day - timedelta(days=2),
            "filing_date": day,
            "accepted_at": None,
            "public_event_day": day + timedelta(days=1),
            "transaction_code": "P",
            "acquired_or_disposed": "A",
            "derivative_flag": False,
            "source_table": "non_derivative",
            "security_title": "Common Stock",
            "shares": None,
            "price": None,
            "transaction_value": None,
            "shares_owned_after": None,
            "direct_or_indirect": None,
            "aff10b5one": None,
            "is_amendment": False,
            "is_p0_qualifying": True,
            "insider_name": "Schema owner name",
        })
        identities[transaction_id] = f"{ticker}-owner-{day.isoformat()}"
        day += timedelta(days=1)
    companies = pd.DataFrame([{
        "ticker": ticker,
        "cik": cik,
        "company_name": f"Synthetic {ticker}",
        "sector": sector,
        "industry": None,
    }])
    return pd.DataFrame(event_rows), pd.DataFrame(transaction_rows), companies, identities


def run_scores(events, transactions, companies, identities):
    return build_activity_scores(
        events,
        transactions,
        companies,
        insider_identity_by_transaction_id=identities,
    )


def current_row(result: pd.DataFrame, event_id: str):
    return result.loc[result["research_event_id"].eq(event_id)].iloc[0]


def test_normal_history_rates_percentiles_and_final_score_are_auditable():
    events, transactions, companies, identities = fixture_frames(date(2024, 1, 1), date(2025, 3, 31))
    scores = run_scores(events, transactions, companies, identities)
    current = current_row(scores, "AAA:2025-03-31")

    assert current["buyers_30d"] == 30
    assert current["recent_event_count"] == 30
    assert current["recent_rate"] == 1.0
    assert current["historical_event_count"] == 365
    assert current["historical_rate"] == 1.0
    assert current["rate_ratio"] == 1.0
    assert current["reference_rule"] == "company"
    assert current["reference_sample_size"] >= MIN_ACTIVITY_REFERENCE

    earlier = scores.loc[scores["information_date"].lt(current["information_date"])]
    buyer_ref = pd.to_numeric(earlier["buyers_30d"], errors="coerce").dropna()
    ratio_ref = pd.to_numeric(earlier["rate_ratio"], errors="coerce").dropna()
    expected_buyers = 100 * (buyer_ref <= current["buyers_30d"]).sum() / len(buyer_ref)
    expected_ratio = 100 * (ratio_ref <= current["rate_ratio"]).sum() / len(ratio_ref)
    assert current["buyer_count_percentile"] == expected_buyers
    assert current["rate_ratio_percentile"] == expected_ratio
    assert current["activity_score"] == pytest.approx((expected_buyers + expected_ratio) / 2)
    assert 0 <= current["activity_score"] <= 100
    assert current["status"] == "complete"


def test_company_reference_falls_back_to_sufficient_sector_history():
    start, current_date = date(2024, 1, 1), date(2025, 3, 31)
    peer_events, peer_tx, _, peer_ids = fixture_frames(start, current_date - timedelta(days=1), "BBB")
    sparse_events, sparse_tx, _, sparse_ids = fixture_frames(current_date - timedelta(days=200), current_date, "AAA")
    sparse_events = sparse_events.loc[sparse_events["information_date"].isin([
        current_date - timedelta(days=200), current_date - timedelta(days=100),
        current_date - timedelta(days=5), current_date - timedelta(days=2), current_date,
    ])]
    sparse_tx = sparse_tx.loc[sparse_tx["filing_date"].isin(sparse_events["information_date"])]
    events = pd.concat([peer_events, sparse_events], ignore_index=True)
    transactions = pd.concat([peer_tx, sparse_tx], ignore_index=True)
    companies = pd.DataFrame([
        {"ticker": "AAA", "sector": "Technology"},
        {"ticker": "BBB", "sector": "Technology"},
    ])
    identities = {**peer_ids, **sparse_ids}

    scores = run_scores(events, transactions, companies, identities)
    current = current_row(scores, "AAA:2025-03-31")
    assert current["reference_rule"] == "sector"
    assert current["reference_sample_size"] >= MIN_ACTIVITY_REFERENCE
    assert current["status"] == "complete"


def test_insufficient_company_and_sector_reference_returns_insufficient_data():
    current_date = date(2025, 1, 4)
    events, transactions, companies, identities = fixture_frames(current_date - timedelta(days=50), current_date)
    keep_dates = {current_date - timedelta(days=50), current_date - timedelta(days=2), current_date - timedelta(days=1), current_date}
    events = events.loc[events["information_date"].isin(keep_dates)]
    transactions = transactions.loc[transactions["filing_date"].isin(keep_dates)]
    result = run_scores(events, transactions, companies, identities)
    current = current_row(result, "AAA:2025-01-04")
    assert current["reference_rule"] == "sector"
    assert current["reference_sample_size"] < MIN_ACTIVITY_REFERENCE
    assert current["activity_score"] is None
    assert current["status"] == "insufficient_data"
    assert "insufficient_company_and_sector_reference_history" in current["missing_reasons"]


def test_zero_historical_rate_has_no_ratio_or_score():
    events, transactions, companies, identities = fixture_frames(date(2025, 3, 25), date(2025, 3, 31))
    result = run_scores(events, transactions, companies, identities)
    current = current_row(result, "AAA:2025-03-31")
    assert current["historical_event_count"] == 0
    assert current["historical_rate"] == 0
    assert pd.isna(current["rate_ratio"])
    assert current["activity_score"] is None or pd.isna(current["activity_score"])
    assert current["status"] == "zero_historical_rate"
    assert "zero_historical_rate" in current["missing_reasons"]
    assert not np.isinf(pd.to_numeric(result["rate_ratio"], errors="coerce")).any()


def test_future_events_and_filings_do_not_change_current_score_or_reference():
    events, transactions, companies, identities = fixture_frames(date(2024, 1, 1), date(2025, 3, 31))
    base = current_row(run_scores(events, transactions, companies, identities), "AAA:2025-03-31")
    future_date = date(2025, 4, 1)
    future_events, future_tx, _, future_ids = fixture_frames(future_date, future_date)
    with_future = current_row(run_scores(
        pd.concat([events, future_events], ignore_index=True),
        pd.concat([transactions, future_tx], ignore_index=True),
        companies,
        {**identities, **future_ids},
    ), "AAA:2025-03-31")
    for column in (
        "buyers_30d", "recent_rate", "historical_rate", "rate_ratio",
        "reference_sample_size", "buyer_count_percentile", "rate_ratio_percentile", "activity_score",
    ):
        assert with_future[column] == base[column]


def test_calendar_window_boundaries_are_inclusive_and_non_overlapping():
    current_date = date(2025, 6, 30)
    dates = [
        current_date - timedelta(days=395),  # outside historical
        current_date - timedelta(days=394),  # first historical day
        current_date - timedelta(days=30),   # last historical day
        current_date - timedelta(days=29),   # first recent day
        current_date,                        # current event day
        current_date + timedelta(days=1),    # future
    ]
    events, transactions, companies, identities = fixture_frames(current_date, current_date, "AAA")
    extra_events, extra_tx, _, extra_ids = fixture_frames(min(dates), max(dates), "AAA")
    events = pd.concat([events, extra_events], ignore_index=True).drop_duplicates("research_event_id")
    transactions = pd.concat([transactions, extra_tx], ignore_index=True).drop_duplicates("transaction_id")
    events = events.loc[events["information_date"].isin(dates)]
    transactions = transactions.loc[transactions["filing_date"].isin(dates)]
    identities.update(extra_ids)
    result = run_scores(events, transactions, companies, identities)
    current = current_row(result, f"AAA:{current_date.isoformat()}")
    assert current["recent_window_start"] == pd.Timestamp(current_date - timedelta(days=29))
    assert current["recent_window_end"] == pd.Timestamp(current_date)
    assert current["historical_window_start"] == pd.Timestamp(current_date - timedelta(days=394))
    assert current["historical_window_end"] == pd.Timestamp(current_date - timedelta(days=30))
    assert current["recent_event_count"] == 2
    assert current["historical_event_count"] == 2
    assert current["recent_event_count"] + current["historical_event_count"] == 4


def test_duplicate_transactions_do_not_inflate_unique_buyer_count():
    event_date = date(2025, 3, 31)
    events, transactions, companies, identities = fixture_frames(event_date - timedelta(days=1), event_date)
    current_tx = transactions.loc[transactions["filing_date"].astype(str).eq(event_date.isoformat())].iloc[0].copy()
    duplicate = current_tx.copy()
    duplicate["transaction_id"] = "second-transaction-same-owner"
    duplicate["canonical_transaction_key"] = "second-transaction-same-owner"
    transactions = pd.concat([transactions, pd.DataFrame([duplicate])], ignore_index=True)
    events.loc[events["information_date"].astype(str).eq(event_date.isoformat()), "source_transaction_count"] = 2
    identities["second-transaction-same-owner"] = identities[current_tx["transaction_id"]]
    result = run_scores(events, transactions, companies, identities)
    current = current_row(result, "AAA:2025-03-31")
    assert current["buyers_30d"] == 2


def test_raw_transactions_do_not_count_as_multiple_company_events():
    event_date = date(2025, 3, 31)
    events, transactions, companies, identities = fixture_frames(event_date - timedelta(days=1), event_date)
    extra = transactions.loc[transactions["filing_date"].astype(str).eq(event_date.isoformat())].iloc[0].copy()
    extra["transaction_id"] = "another-raw-row"
    extra["canonical_transaction_key"] = "another-raw-row"
    transactions = pd.concat([transactions, pd.DataFrame([extra])], ignore_index=True)
    events.loc[events["information_date"].astype(str).eq(event_date.isoformat()), "source_transaction_count"] = 2
    identities["another-raw-row"] = "same-canonical-owner"
    result = run_scores(events, transactions, companies, identities)
    current = current_row(result, "AAA:2025-03-31")
    assert current["recent_event_count"] == 2
    assert current["recent_rate"] == pytest.approx(2 / 30)


def test_empirical_percentile_ties_use_upper_rank_deterministically():
    values = pd.Series([1.0, 2.0, 2.0, 4.0])
    assert _empirical_percentile(2.0, values) == 75.0
    assert _empirical_percentile(0.0, values) == 0.0
    assert _empirical_percentile(5.0, values) == 100.0
    assert _empirical_percentile(2.0, values) == _empirical_percentile(2.0, values)


def test_missing_canonical_insider_id_makes_buyer_count_and_score_unavailable():
    event_date = date(2025, 3, 31)
    events, transactions, companies, identities = fixture_frames(date(2024, 1, 1), event_date)
    transaction_id = transactions.loc[transactions["filing_date"].astype(str).eq(event_date.isoformat()), "transaction_id"].iloc[0]
    del identities[transaction_id]
    result = run_scores(events, transactions, companies, identities)
    current = current_row(result, "AAA:2025-03-31")
    assert pd.isna(current["buyers_30d"])
    assert pd.isna(current["buyer_count_percentile"])
    assert pd.isna(current["activity_score"])
    assert "missing_canonical_insider_identifier" in current["missing_reasons"]


def test_missing_sector_and_missing_company_identifier_are_explicit():
    events, transactions, companies, identities = fixture_frames(date(2025, 1, 1), date(2025, 1, 4), sector=None)
    result = run_scores(events, transactions, companies, identities)
    current = current_row(result, "AAA:2025-01-04")
    assert current["reference_rule"] is None
    assert "missing_sector_for_reference_fallback" in current["missing_reasons"]

    events.loc[events["research_event_id"].eq("AAA:2025-01-04"), "ticker"] = None
    missing_company = run_scores(events, transactions, companies, identities)
    row = current_row(missing_company, "AAA:2025-01-04")
    assert "missing_company_identifier" in row["missing_reasons"]
    assert row["activity_score"] is None or pd.isna(row["activity_score"])


def test_scores_and_component_percentiles_stay_on_zero_to_hundred_scale():
    events, transactions, companies, identities = fixture_frames(date(2024, 1, 1), date(2025, 3, 31))
    result = run_scores(events, transactions, companies, identities)
    complete = result.loc[result["status"].eq("complete")]
    for column in ("buyer_count_percentile", "rate_ratio_percentile", "activity_score"):
        values = pd.to_numeric(complete[column], errors="coerce")
        assert values.between(0, 100).all()
