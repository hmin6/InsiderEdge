"""Event-level ML inputs, observed labels, and chronological partitions.

No fitting or imputation occurs here. Frozen-universe inputs retain the project's
survivorship/selection bias; these utilities do not reconstruct membership.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from app.quant.event_study import (
    _normalized_dates, _prepare_expected_sessions, _prepare_inputs, _returns_for_pair,
)

KEY = "research_event_id"
MARKET_FEATURES = (
    "prior_return_5d", "prior_return_30d", "prior_return_90d",
    "prior_volatility_30d", "drawdown_90d", "volume_zscore_30d",
    "spy_relative_return_30d", "sector_relative_return_30d",
)
BUYER_FEATURES = ("unique_buyers_7d", "unique_buyers_30d")
INSIDER_FEATURES = (
    "aggregate_purchase_value", "log_aggregate_purchase_value",
    "max_valid_ownership_change_pct", "any_new_position_flag", "has_executive",
    "has_cfo", "has_director", "purchase_value_7d", "purchase_value_30d",
    "recent_purchase_rate", "historical_purchase_rate",
)
FEATURE_GROUPS = {
    "market": MARKET_FEATURES, "insider": INSIDER_FEATURES,
    "buyers": BUYER_FEATURES, "categories": ("sector", "role_bucket"),
}
FEATURE_COLUMNS = tuple(name for names in FEATURE_GROUPS.values() for name in names)


@dataclass(frozen=True)
class MLDataset:
    """Aligned DataFrames indexed by event ID; only ``features`` is predictive.

    ``availability`` contains one reasons list per predictor and feature_status.
    Missing predictors remain null. Targets and metadata must never enter X.
    """
    metadata: pd.DataFrame
    features: pd.DataFrame
    targets: pd.DataFrame
    availability: pd.DataFrame


@dataclass(frozen=True)
class TemporalSplit:
    """Supervised event-ID indices, all-row exclusion audit, and split counts."""
    partitions: dict[str, pd.Index]
    audit: pd.DataFrame
    summary: pd.DataFrame
    boundaries: dict[str, pd.Timestamp]


def _ids(frame: pd.DataFrame, name: str, event_ids: pd.Index | None = None,
         *, complete: bool = False) -> None:
    if KEY not in frame or frame[KEY].isna().any() or frame[KEY].astype(str).str.strip().eq("").any():
        raise ValueError(f"{name} requires non-null, nonempty {KEY}")
    if frame[KEY].duplicated().any():
        raise ValueError(f"{name} contains duplicate {KEY}")
    if event_ids is not None:
        unknown = frame.loc[~frame[KEY].isin(event_ids), KEY].tolist()
        if unknown:
            raise ValueError(f"{name} contains unmatched event IDs: {unknown[:5]}")
        if complete and not event_ids.isin(frame[KEY]).all():
            raise ValueError(f"{name} is missing rows for research events")


def _events(events: pd.DataFrame) -> pd.DataFrame:
    required = {KEY, "ticker", "information_date", "public_event_day"}
    if not required.issubset(events):
        raise ValueError(f"events missing columns: {sorted(required - set(events.columns))}")
    _ids(events, "events")
    result = events[[KEY, "ticker", "information_date", "public_event_day"]].copy()
    result["ticker"] = result["ticker"].astype("string").str.strip().str.upper()
    for column in ("information_date", "public_event_day"):
        result[column] = _normalized_dates(result[column])
    if result[["ticker", "information_date", "public_event_day"]].isna().any().any() or result["ticker"].eq("").any():
        raise ValueError("events require valid ticker and dates")
    if result.duplicated(["ticker", "public_event_day"]).any():
        raise ValueError("events contain duplicate ticker/public_event_day")
    if result["public_event_day"].le(result["information_date"]).any():
        raise ValueError("public_event_day must be after information_date")
    return result.sort_values(["information_date", "ticker", KEY], kind="stable").set_index(KEY)


def build_outperformance_labels(
    events: pd.DataFrame, prices: pd.DataFrame, expected_sessions: Sequence[object],
    *, observation_cutoff: object,
) -> pd.DataFrame:
    """Compound 30 adjacent returns t=0..29, including the t=-1 price.

    Cutoff is an inclusive completed-session date supplied by the caller. All
    31 prices per symbol must be positive/finite and present on the trusted
    expected calendar. Invalid prices become missing; duplicate/malformed keys
    raise ValueError, following event_study. Unavailable outcomes have null Y,
    null returns, an endpoint when known, and explicit missing_reasons.
    """
    ordered = _events(events)
    cutoff = _normalized_dates(pd.Series([observation_cutoff])).iloc[0]
    if pd.isna(cutoff):
        raise ValueError("observation_cutoff must be a valid completed-session date")
    sessions = _prepare_expected_sessions(expected_sessions)
    _, market = _prepare_inputs(events, prices)
    market = market.loc[market["date"].le(cutoff)]
    positions = {day: index for index, day in enumerate(sessions)}
    pair_cache = {}
    price_lookup = market.set_index(["ticker", "date"])["analysis_price"]
    rows = []
    for event_id, event in ordered.iterrows():
        index = positions.get(event.public_event_day)
        reasons = []
        endpoint = None
        stock_return = spy_return = label = None
        if event.ticker == "SPY":
            reasons.append("event_ticker_is_benchmark")
        if index is None or index < 1 or index + 29 >= len(sessions):
            reasons.append("insufficient_expected_session_coverage")
        else:
            endpoint = sessions[index + 29]
            if sessions[index - 1] > event.information_date:
                reasons.append("public_event_day_is_not_first_session_after_information_date")
            if endpoint > cutoff:
                reasons.append("outcome_not_observed_by_cutoff")
            if not reasons:
                if event.ticker not in pair_cache:
                    pair_cache[event.ticker] = _returns_for_pair(market, event.ticker, sessions)[1]
                pairs = pair_cache[event.ticker]
                window = [pairs.get(day, (None, None)) for day in sessions[index:index + 30]]
                for offset, pair in enumerate(window):
                    if pair[0] is None or pair[1] is None:
                        reasons.append(f"missing_paired_return_t{offset}")
                if not reasons:
                    # The compounded product telescopes to P[t29]/P[t-1].
                    # After validating EVERY return, use that equivalent form
                    # so equal endpoint ratios remain ties despite path rounding.
                    previous = sessions[index - 1]
                    with np.errstate(over="ignore", invalid="ignore"):
                        compounded = np.asarray([
                            price_lookup.loc[(symbol, endpoint)] / price_lookup.loc[(symbol, previous)] - 1.0
                            for symbol in (event.ticker, "SPY")
                        ], dtype=float)
                    if not np.isfinite(compounded).all():
                        reasons.append("nonfinite_compounded_return")
                    else:
                        stock_return, spy_return = map(float, compounded)
                        label = int(stock_return > spy_return)
        rows.append({KEY: event_id, "Y": label, "stock_return_30d": stock_return,
                     "spy_return_30d": spy_return, "outcome_end": endpoint,
                     "observation_cutoff": cutoff, "label_status": "complete" if label is not None else "unavailable",
                     "missing_reasons": reasons})
    columns = [KEY, "Y", "stock_return_30d", "spy_return_30d", "outcome_end", "observation_cutoff", "label_status", "missing_reasons"]
    result = pd.DataFrame(rows, columns=columns)
    result["Y"] = pd.array(result["Y"], dtype="Int64")
    return result


def prepare_inference_features(events: pd.DataFrame, event_features: pd.DataFrame,
                               feature_provenance: pd.DataFrame, *, strict: bool = True) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return metadata, allowed X and availability without requiring labels.

    Same information-time rules as training. Strict production mode rejects
    invalid provenance/available numeric values; training retains its existing
    missing-group masking behavior. Provenance remains a trusted attestation.
    Extra raw columns are excluded from X, including outcomes and identifiers.
    """
    metadata = _events(events)
    _ids(event_features, "event_features", metadata.index, complete=True)
    if event_features.columns.has_duplicates:
        raise ValueError("duplicate feature columns")
    required_provenance = {KEY, "feature_group", "source_date", "verified"}
    if not required_provenance.issubset(feature_provenance):
        raise ValueError(f"feature_provenance missing columns: {sorted(required_provenance - set(feature_provenance.columns))}")
    provenance = feature_provenance.copy()
    _ids(provenance[[KEY]].drop_duplicates(), "feature_provenance", metadata.index)
    if provenance.duplicated([KEY, "feature_group"]).any():
        raise ValueError("duplicate event/feature_group provenance")
    if not provenance["feature_group"].isin(FEATURE_GROUPS).all():
        raise ValueError("unknown feature_group in provenance")
    provenance["source_date"] = _normalized_dates(provenance["source_date"])
    sources = event_features.set_index(KEY).reindex(metadata.index)
    features = pd.DataFrame(index=metadata.index, columns=FEATURE_COLUMNS)
    availability = pd.DataFrame(index=metadata.index, columns=FEATURE_COLUMNS, dtype=object)
    records = {(row[KEY], row["feature_group"]): row for row in provenance.to_dict("records")}
    for event_id, event in metadata.iterrows():
        for group, names in FEATURE_GROUPS.items():
            record = records.get((event_id, group))
            reasons = []
            if record is None or pd.isna(record["source_date"]) or record["verified"] is not True:
                reasons.append("missing_or_unverified_provenance")
            if record is not None and pd.notna(record["source_date"]):
                future = record["source_date"] >= event.information_date if group == "market" else record["source_date"] > event.information_date
                if future:
                    raise ValueError(f"future feature source for {event_id}/{group}")
            if group == "buyers" and (record is None or record.get("canonical_identity_verified") is not True):
                reasons.append("canonical_buyer_identity_unverified")
            for name in names:
                value = sources.at[event_id, name] if name in sources else None
                missing = pd.isna(value)
                if not missing and group == "categories":
                    value = str(value).strip()
                    missing = not value or (name == "role_bucket" and value not in {"Executive", "Director", "Other"})
                if not missing and group != "categories":
                    try:
                        value = float(value)
                        missing = not np.isfinite(value)
                    except (TypeError, ValueError):
                        missing = True
                feature_reasons = reasons + (["missing_or_invalid_feature"] if missing else [])
                features.at[event_id, name] = np.nan if feature_reasons else value
                availability.at[event_id, name] = feature_reasons
    for name in (*MARKET_FEATURES, *INSIDER_FEATURES, *BUYER_FEATURES):
        features[name] = pd.to_numeric(features[name], errors="coerce")
    for name in ("sector", "role_bucket"):
        features[name] = features[name].astype("string")
    availability["feature_status"] = ["complete" if all(not reasons for reasons in row) else "partial" for row in availability.itertuples(index=False, name=None)]
    if strict:
        for field in ('ticker', 'information_date', 'public_event_day'):
            if field in sources:
                values = sources[field] if field == 'ticker' else _normalized_dates(sources[field])
                if values.isna().any() or not values.eq(metadata[field]).fillna(False).all():
                    raise ValueError(f'feature metadata mismatch: {field}')
        for event_id in metadata.index:
            for group in FEATURE_GROUPS:
                record = records.get((event_id, group))
                if record is None or pd.isna(record['source_date']) or record['verified'] is not True:
                    raise ValueError(f'invalid provenance for {event_id}/{group}')
                if group == 'buyers' and record.get('canonical_identity_verified') is not True:
                    raise ValueError(f'unverified canonical buyer identities for {event_id}')
                for name in FEATURE_GROUPS[group]:
                    value = sources.at[event_id, name] if name in sources else None
                    if name not in ('sector', 'role_bucket') and not pd.isna(value):
                        try:
                            valid = not isinstance(value, (bool, np.bool_)) and np.isfinite(float(value))
                        except (ValueError, TypeError, OverflowError):
                            valid = False
                        if not valid:
                            raise ValueError(f'invalid numeric feature {event_id}/{name}')
    return metadata, features, availability


def build_ml_dataset(events: pd.DataFrame, event_features: pd.DataFrame,
                     labels: pd.DataFrame, feature_provenance: pd.DataFrame) -> MLDataset:
    """Assemble explicit raw predictors; silently injected extra columns never enter X.

    Features/labels must each cover all events exactly once. Provenance is long
    format: event ID, feature_group (market/insider/buyers/categories),
    source_date (latest source availability), verified (boolean). Buyers also
    require canonical_identity_verified=True. Market dates must be strictly
    before information_date; other groups may equal it. Verified future dates
    and unverified future dates both raise. Missing groups, dates or verification
    mask the entire group. Provenance is an upstream attestation, not inferred
    from a feature value. Sector and role remain unencoded categorical values.
    """
    metadata = _events(events)
    for frame, name in ((event_features, "event_features"), (labels, "labels")):
        _ids(frame, name, metadata.index, complete=True)
    required_labels = ("Y", "outcome_end", "observation_cutoff", "label_status", "missing_reasons")
    if not set(required_labels).issubset(labels):
        raise ValueError(f"labels missing columns: {sorted(set(required_labels) - set(labels.columns))}")
    metadata, features, availability = prepare_inference_features(
        events, event_features, feature_provenance, strict=False)
    targets = labels.set_index(KEY).reindex(metadata.index).loc[:, list(required_labels)].copy()
    for name in ("outcome_end", "observation_cutoff"):
        targets[name] = _normalized_dates(targets[name])
    if not targets["label_status"].isin(["complete", "unavailable"]).all():
        raise ValueError("labels require complete or unavailable label_status")
    if not targets["missing_reasons"].map(lambda value: isinstance(value, list)).all():
        raise ValueError("labels require a missing_reasons list")
    complete = targets["label_status"].eq("complete")
    invalid = (~targets["Y"].isin([0, 1]) | targets["outcome_end"].isna()
               | targets["observation_cutoff"].isna()
               | targets["outcome_end"].lt(metadata["public_event_day"])
               | targets["outcome_end"].gt(targets["observation_cutoff"]))
    if (complete & (invalid | targets["missing_reasons"].map(bool))).any() or (~complete & targets["Y"].notna()).any():
        raise ValueError("labels contradict availability, outcome timing or observation cutoff")
    targets["Y"] = pd.array(targets["Y"], dtype="Int64")
    return MLDataset(metadata, features, targets, availability)


def split_temporally(dataset: MLDataset, *, mode: str = "calendar",
                     boundaries: Mapping[str, object] | None = None) -> TemporalSplit:
    """Partition by information_date and purge outcomes touching the next split.

    Calendar defaults are starts 2020-01-01/2025-01-01/2026-01-01 and exclusive
    end 2027-01-01. Chronological mode chooses date-group boundaries nearest
    cumulative 70% and 85% of ALL rows, independent of labels and values.
    No automatic sparsity fallback. A next split's first information date is
    determined before excluding unavailable labels; an empty next split uses
    its configured start. At least three distinct dates are needed for fallback.
    """
    metadata, targets = dataset.metadata, dataset.targets
    if not metadata.index.equals(targets.index) or not metadata.index.equals(dataset.features.index):
        raise ValueError("dataset frames must have identical event indices")
    dates = metadata["information_date"]
    if dates.isna().any() or metadata.index.has_duplicates:
        raise ValueError("dataset needs unique event IDs and valid information dates")
    if mode == "calendar":
        raw = boundaries if boundaries is not None else {"train": "2020-01-01", "validation": "2025-01-01", "test": "2026-01-01", "end": "2027-01-01"}
        if set(raw) != {"train", "validation", "test", "end"}:
            raise ValueError("boundaries require train, validation, test and end")
        starts = {name: _normalized_dates(pd.Series([value])).iloc[0] for name, value in raw.items()}
    elif mode == "chronological":
        if boundaries is not None:
            raise ValueError("chronological mode calculates boundaries from date groups")
        counts = dates.value_counts().sort_index()
        if len(counts) < 3:
            raise ValueError("chronological split requires at least three information dates")
        cumulative = counts.cumsum().to_numpy()
        first = min(range(len(counts) - 2), key=lambda i: abs(cumulative[i] - len(dates) * 0.70))
        second = min(range(first + 1, len(counts) - 1), key=lambda i: abs(cumulative[i] - len(dates) * 0.85))
        starts = {"train": counts.index[0], "validation": counts.index[first + 1],
                  "test": counts.index[second + 1], "end": counts.index[-1] + pd.Timedelta(days=1)}
    else:
        raise ValueError("mode must be calendar or chronological")
    names = ["train", "validation", "test"]
    limits = [starts[name] for name in [*names, "end"]]
    if any(pd.isna(value) for value in limits) or any(a >= b for a, b in zip(limits, limits[1:])):
        raise ValueError("split boundaries must be valid and strictly increasing")
    assigned = pd.Series("out_of_range", index=metadata.index)
    for i, name in enumerate(names):
        assigned.loc[dates.ge(limits[i]) & dates.lt(limits[i + 1])] = name
    first_dates = {name: dates.loc[assigned.eq(name)].min() for name in names}
    rows = []
    for event_id in metadata.index:
        partition = assigned[event_id]
        reasons = []
        if partition == "out_of_range":
            reasons.append("out_of_range")
        label = targets.loc[event_id]
        if label["label_status"] != "complete" or pd.isna(label["Y"]):
            reasons.append("unavailable_label")
        elif partition in names[:-1]:
            next_name = names[names.index(partition) + 1]
            guard = first_dates[next_name] if pd.notna(first_dates[next_name]) else starts[next_name]
            if pd.isna(label["outcome_end"]) or label["outcome_end"] >= guard:
                reasons.append("purged_outcome_overlap")
        rows.append({KEY: event_id, "partition": partition, "included": not reasons, "exclusion_reasons": reasons})
    audit = pd.DataFrame(rows, columns=[KEY, "partition", "included", "exclusion_reasons"]).set_index(KEY)
    audit["included"] = audit["included"].astype(bool)
    partitions = {name: audit.index[audit["partition"].eq(name) & audit["included"]] for name in names}
    summary = []
    for name in [*names, "out_of_range"]:
        part = audit.loc[audit["partition"].eq(name)]
        selected = part.index[part["included"]]
        y = targets.loc[selected, "Y"]
        summary.append({"partition": name, "sample_count": len(selected), "positive_count": int(y.eq(1).sum()),
                        "negative_count": int(y.eq(0).sum()),
                        "unavailable_label_count": sum("unavailable_label" in r for r in part["exclusion_reasons"]),
                        "purged_count": sum("purged_outcome_overlap" in r for r in part["exclusion_reasons"]),
                        "out_of_range_count": len(part) if name == "out_of_range" else 0})
    return TemporalSplit(partitions, audit, pd.DataFrame(summary).set_index("partition"), starts)
