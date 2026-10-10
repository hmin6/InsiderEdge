"""Offline evidence export; never computes activity metrics or accesses storage.

Pass scorer DataFrames via ``to_dict(orient="records")``. Metadata is explicit,
per-event, and never substitutes for a field supplied by the scorer (even null).
Only listed diagnostic fields are exported; owner names/identifiers are excluded.
Provenance strings must be sanitized by the caller: this is not a secret scanner.
"""
from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd

DIAGNOSTIC_FIELDS = (
    "ticker", "public_event_day", "filing_date", "information_date",
    "activity_score", "status", "missing_reasons",
    "recent_window_start", "recent_window_end", "historical_window_start",
    "historical_window_end", "recent_event_count", "historical_event_count",
    "recent_rate", "historical_rate", "buyers_30d", "rate_ratio",
    "company_reference_size", "sector_reference_size", "reference_rule",
    "reference_sample_size", "buyer_reference_size", "rate_ratio_reference_size",
    "buyer_count_percentile", "rate_ratio_percentile",
    "canonical_identity_evidence_status", "input_snapshot_id",
    "scoring_policy_version", "source_provenance",
)


def _json_value(value: Any) -> Any:
    """Copy supplied evidence into strict JSON; missing scalars become null."""
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, np.generic):
        return _json_value(value.item())
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        # Preserve decimal evidence without a lossy float conversion.
        return str(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("Diagnostic evidence object keys must be strings")
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    raise ValueError(f"Unsupported diagnostic evidence type: {type(value).__name__}")


def _indexed(records: Iterable[Mapping[str, Any]], label: str) -> dict[str, Mapping[str, Any]]:
    result = {}
    for index, row in enumerate(records):
        location = f"{label}[{index}]"
        if not isinstance(row, Mapping):
            raise ValueError(f"{location}: expected a mapping")
        event_id = row.get("research_event_id")
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError(f"{location}: research_event_id must be a nonempty string")
        if event_id in result:
            raise ValueError(f"{location}: duplicate research_event_id")
        result[event_id] = row
    return result


def build_activity_diagnostics(
    activity_records: Iterable[Mapping[str, Any]],
    *,
    metadata_records: Iterable[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Return one diagnostic row per supplied activity record, sorted by ID.

    Each field has ``state``, ``value``, and ``source``. States: ``observed``
    (supplied non-null evidence, not necessarily type-valid), ``unavailable`` (explicit null/nonfinite/missing
    scalar), ``not_supplied`` (absent). States describe evidence presence, not
    scoring validity or independent verification. Empty lists and zero are
    observed. No reasons, counts, percentiles, or provenance are inferred.

    Metadata may supplement absent fields only; conflicting supplied values
    raise an error. Metadata IDs absent from activity_records are rejected.
    The result is detached from inputs and strict-JSON serializable.
    """
    activities = _indexed(activity_records, "activity_records")
    metadata = _indexed(metadata_records, "metadata_records")
    unmatched = sorted(metadata.keys() - activities.keys())
    if unmatched:
        raise ValueError("metadata_records IDs absent from activity_records")
    output = []
    for event_id in sorted(activities):
        activity, extra = activities[event_id], metadata.get(event_id, {})
        fields = {}
        for name in DIAGNOSTIC_FIELDS:
            if name in activity and name in extra:
                if _json_value(activity[name]) != _json_value(extra[name]):
                    raise ValueError(f"Conflicting {name} evidence between activity_records and metadata_records")
            source = "activity_records" if name in activity else (
                "metadata_records" if name in extra else None
            )
            value = _json_value((activity if name in activity else extra)[name]) if source else None
            state = "not_supplied" if source is None else (
                "unavailable" if value is None else "observed"
            )
            fields[name] = {"state": state, "value": value, "source": source}
        output.append({"research_event_id": event_id, "fields": fields})
    return output


def activity_diagnostics_json(
    activity_records: Iterable[Mapping[str, Any]],
    *,
    metadata_records: Iterable[Mapping[str, Any]] = (),
) -> str:
    """Serialize diagnostics; no files are read or written by this module."""
    return json.dumps(
        build_activity_diagnostics(activity_records, metadata_records=metadata_records),
        allow_nan=False, sort_keys=True, indent=2,
    ) + "\n"
