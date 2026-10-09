"""Leakage-aware insider activity / cluster score (C).

The schema has no canonical insider identifier. Callers must provide an
explicit transaction-id to canonical-insider-id mapping; insider names are
never silently treated as canonical identities.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd


MIN_ACTIVITY_REFERENCE = 10
RECENT_DAYS = 30
HISTORICAL_DAYS = 365
_TRUE = {True, 1, "1", "true", "True", "TRUE", "yes", "Y"}


def _dates(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, errors="coerce").dt.normalize()


def _qualifying_transactions(transactions: pd.DataFrame) -> pd.DataFrame:
    """Select non-derivative P acquisitions, honoring the normalized P0 flag."""
    tx = transactions.copy()
    if "is_p0_qualifying" in tx.columns:
        mask = tx["is_p0_qualifying"].map(lambda value: value in _TRUE).fillna(False)
    elif {"transaction_code", "acquired_or_disposed", "derivative_flag"}.issubset(tx.columns):
        mask = (
            tx["transaction_code"].astype("string").str.upper().eq("P")
            & tx["acquired_or_disposed"].astype("string").str.upper().eq("A")
            & ~tx["derivative_flag"].map(lambda value: value in _TRUE).fillna(False)
        )
    else:
        mask = pd.Series(False, index=tx.index)
    tx = tx.loc[mask].copy()
    if "ticker" in tx:
        tx["ticker"] = tx["ticker"].astype("string").str.strip().str.upper()
    if "filing_date" in tx:
        tx["filing_date"] = _dates(tx["filing_date"])
    return tx


def _identity_map(value: object, mapping: Mapping[Any, Any]) -> str | None:
    if value is None or pd.isna(value):
        return None
    identity = mapping.get(value)
    if identity is None or pd.isna(identity):
        return None
    normalized = str(identity).strip()
    return normalized or None


def _empirical_percentile(value: float, reference: pd.Series) -> float | None:
    """Empirical CDF on [0, 100], with ties assigned the upper/weak rank."""
    valid = pd.to_numeric(reference, errors="coerce").dropna().to_numpy(dtype=float)
    if not len(valid) or not np.isfinite(value):
        return None
    return float(100.0 * np.searchsorted(np.sort(valid), value, side="right") / len(valid))


def _event_activity(
    event: pd.Series,
    events: pd.DataFrame,
    transactions: pd.DataFrame,
    insider_identity_by_transaction_id: Mapping[Any, Any],
) -> dict[str, Any]:
    """Compute raw activity for one event using information available by its date."""
    ticker = event["ticker"]
    information_date = event["information_date"]
    result: dict[str, Any] = {
        "buyers_30d": None,
        "recent_event_count": None,
        "recent_rate": None,
        "historical_event_count": None,
        "historical_rate": None,
        "rate_ratio": None,
        "missing_reasons": [],
    }
    if pd.isna(ticker) or not str(ticker).strip():
        result["missing_reasons"].append("missing_company_identifier")
        return result
    if pd.isna(information_date):
        result["missing_reasons"].append("missing_information_date")
        return result

    ticker = str(ticker).strip().upper()
    recent_start = information_date - pd.Timedelta(days=RECENT_DAYS - 1)
    historical_start = information_date - pd.Timedelta(days=RECENT_DAYS + HISTORICAL_DAYS - 1)
    historical_end = recent_start - pd.Timedelta(days=1)

    company_events = events.loc[events["ticker"].eq(ticker)]
    available_events = company_events.loc[company_events["information_date"].le(information_date)]
    recent_event_days = available_events.loc[
        available_events["information_date"].between(recent_start, information_date, inclusive="both"),
        "public_event_day",
    ].dropna().drop_duplicates()
    historical_event_days = available_events.loc[
        available_events["information_date"].between(historical_start, historical_end, inclusive="both"),
        "public_event_day",
    ].dropna().drop_duplicates()
    result["recent_event_count"] = int(len(recent_event_days))
    result["recent_rate"] = float(len(recent_event_days) / RECENT_DAYS)
    result["historical_event_count"] = int(len(historical_event_days))
    result["historical_rate"] = float(len(historical_event_days) / HISTORICAL_DAYS)
    if result["historical_rate"] > 0:
        result["rate_ratio"] = float(result["recent_rate"] / result["historical_rate"])
    else:
        result["missing_reasons"].append("zero_historical_rate")

    recent_transactions = transactions.loc[
        transactions["ticker"].eq(ticker)
        & transactions["filing_date"].between(recent_start, information_date, inclusive="both")
        & transactions["filing_date"].le(information_date)
    ]
    transaction_id_column = "transaction_id"
    if transaction_id_column not in recent_transactions.columns:
        if len(recent_transactions):
            result["missing_reasons"].append("missing_transaction_identifier")
            return result
        result["buyers_30d"] = 0
        return result

    identifiers: list[str] = []
    missing_identity = False
    for transaction_id in recent_transactions[transaction_id_column]:
        identity = _identity_map(transaction_id, insider_identity_by_transaction_id)
        if identity is None:
            missing_identity = True
        else:
            identifiers.append(identity)
    if missing_identity:
        result["missing_reasons"].append("missing_canonical_insider_identifier")
    else:
        result["buyers_30d"] = int(len(set(identifiers)))
    return result


def build_activity_scores(
    research_events: pd.DataFrame,
    transactions: pd.DataFrame,
    companies: pd.DataFrame,
    *,
    insider_identity_by_transaction_id: Mapping[Any, Any] | None = None,
) -> pd.DataFrame:
    """Return an auditable activity result per unique ticker + event day.

    ``research_events`` and ``transactions`` follow ``DATA_SCHEMA.md``. The
    canonical company identifier is the normalized ticker (the companies
    primary key). Since the schema does not define a stable insider ID, the
    optional identity mapping must map each ``transaction_id`` to a canonical
    insider identifier. Missing mappings make ``buyers_30d`` and C unavailable
    when an unmapped qualifying transaction is in the recent window.

    Calendar windows are inclusive: recent is ``[information_date - 29 days,
    information_date]``; historical is ``[information_date - 394 days,
    information_date - 30 days]``. They contain 30 and 365 calendar dates,
    respectively, and do not overlap. Recent/historical rates are event counts
    divided by 30/365 days. Percentiles use the empirical CDF
    ``100 * count(reference <= current) / n``; ties receive the upper rank.
    """
    required_events = {"research_event_id", "ticker", "public_event_day", "information_date"}
    required_companies = {"ticker", "sector"}
    if not required_events.issubset(research_events.columns):
        raise ValueError(f"research_events missing {sorted(required_events - set(research_events.columns))}")
    if not required_companies.issubset(companies.columns):
        raise ValueError(f"companies missing {sorted(required_companies - set(companies.columns))}")
    if not {"ticker", "filing_date"}.issubset(transactions.columns):
        raise ValueError("transactions must include ticker and filing_date")

    events = research_events.copy()
    events["ticker"] = events["ticker"].astype("string").str.strip().str.upper()
    events["public_event_day"] = _dates(events["public_event_day"])
    events["information_date"] = _dates(events["information_date"])
    if events["research_event_id"].duplicated().any():
        raise ValueError("research_events must contain unique research_event_id values")
    # The contract is one event per company + public day. Deduplicate event rows
    # before rates and reference distributions so one company-day counts once.
    events = events.sort_values(["information_date", "research_event_id"], kind="stable")
    events = events.drop_duplicates(["ticker", "public_event_day"], keep="first").reset_index(drop=True)

    tx = _qualifying_transactions(transactions)
    company_sectors = companies.copy()
    company_sectors["ticker"] = company_sectors["ticker"].astype("string").str.strip().str.upper()
    if company_sectors["ticker"].dropna().duplicated().any():
        raise ValueError("companies must contain one sector row per ticker")
    sector_by_ticker = company_sectors.set_index("ticker")["sector"].to_dict()
    identity_map = insider_identity_by_transaction_id or {}

    metrics: list[dict[str, Any]] = []
    for _, event in events.iterrows():
        raw = _event_activity(event, events, tx, identity_map)
        metrics.append({
            "research_event_id": event["research_event_id"],
            "ticker": event["ticker"],
            "public_event_day": event["public_event_day"],
            "information_date": event["information_date"],
            **raw,
        })
    metric_frame = pd.DataFrame(metrics)

    output: list[dict[str, Any]] = []
    for _, current in metric_frame.iterrows():
        ticker = current["ticker"]
        information_date = current["information_date"]
        recent_start = information_date - pd.Timedelta(days=RECENT_DAYS - 1) if pd.notna(information_date) else pd.NaT
        historical_start = information_date - pd.Timedelta(days=RECENT_DAYS + HISTORICAL_DAYS - 1) if pd.notna(information_date) else pd.NaT
        historical_end = recent_start - pd.Timedelta(days=1) if pd.notna(recent_start) else pd.NaT
        earlier = metric_frame.loc[
            metric_frame["ticker"].eq(ticker)
            & metric_frame["information_date"].lt(information_date)
        ] if pd.notna(information_date) else metric_frame.iloc[0:0]
        reference_rule: str | None = None
        reference = metric_frame.iloc[0:0]
        if len(earlier) >= MIN_ACTIVITY_REFERENCE:
            reference_rule = "company"
            reference = earlier
        else:
            sector = sector_by_ticker.get(ticker)
            if sector is not None and not pd.isna(sector) and str(sector).strip():
                sector_tickers = set(company_sectors.loc[
                    company_sectors["sector"].eq(sector), "ticker"
                ].dropna().astype("string").str.upper())
                reference = metric_frame.loc[
                    metric_frame["ticker"].isin(sector_tickers)
                    & metric_frame["information_date"].lt(information_date)
                ]
                reference_rule = "sector"

        reasons = list(current["missing_reasons"] or [])
        buyer_refs = pd.to_numeric(reference["buyers_30d"], errors="coerce").dropna() if len(reference) else pd.Series(dtype=float)
        ratio_refs = pd.to_numeric(reference["rate_ratio"], errors="coerce").dropna() if len(reference) else pd.Series(dtype=float)
        buyer_percentile = None
        ratio_percentile = None
        if pd.notna(current["buyers_30d"]) and len(buyer_refs) >= MIN_ACTIVITY_REFERENCE:
            buyer_percentile = _empirical_percentile(float(current["buyers_30d"]), buyer_refs)
        elif pd.isna(current["buyers_30d"]):
            if "missing_canonical_insider_identifier" not in reasons:
                reasons.append("buyers_30d_unavailable")
        else:
            reasons.append("insufficient_buyer_reference_values")

        if pd.notna(current["rate_ratio"]) and len(ratio_refs) >= MIN_ACTIVITY_REFERENCE:
            ratio_percentile = _empirical_percentile(float(current["rate_ratio"]), ratio_refs)
        elif pd.isna(current["rate_ratio"]):
            if "zero_historical_rate" not in reasons:
                reasons.append("rate_ratio_unavailable")
        else:
            reasons.append("insufficient_rate_ratio_reference_values")

        score = None
        if buyer_percentile is not None and ratio_percentile is not None:
            score = float(0.5 * buyer_percentile + 0.5 * ratio_percentile)
        if len(earlier) < MIN_ACTIVITY_REFERENCE and (
            reference_rule != "sector" or len(reference) < MIN_ACTIVITY_REFERENCE
        ):
            reasons.append("insufficient_company_and_sector_reference_history")
        if sector_by_ticker.get(ticker) is None and len(earlier) < MIN_ACTIVITY_REFERENCE:
            reasons.append("missing_sector_for_reference_fallback")
        status = "complete" if score is not None else (
            "zero_historical_rate" if "zero_historical_rate" in reasons else "insufficient_data"
        )
        output.append({
            "research_event_id": current["research_event_id"],
            "ticker": ticker,
            "information_date": information_date,
            "recent_window_start": recent_start,
            "recent_window_end": information_date,
            "historical_window_start": historical_start,
            "historical_window_end": historical_end,
            "buyers_30d": current["buyers_30d"],
            "recent_event_count": current["recent_event_count"],
            "recent_rate": current["recent_rate"],
            "historical_event_count": current["historical_event_count"],
            "historical_rate": current["historical_rate"],
            "rate_ratio": current["rate_ratio"],
            "reference_rule": reference_rule,
            "reference_sample_size": int(len(reference)),
            "buyer_reference_size": int(len(buyer_refs)),
            "rate_ratio_reference_size": int(len(ratio_refs)),
            "buyer_count_percentile": buyer_percentile,
            "rate_ratio_percentile": ratio_percentile,
            "activity_score": score,
            "status": status,
            "missing_reasons": sorted(set(reasons)),
        })
    return pd.DataFrame(output)
