"""Synthetic fixtures; these are not recovered production-run evidence."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
import json
import socket

import numpy as np
import pandas as pd
import pytest
import sqlalchemy

from app.quant.activity_diagnostics import (
    DIAGNOSTIC_FIELDS, activity_diagnostics_json, build_activity_diagnostics,
)


def record(**values):
    return {"research_event_id": "SYNTHETIC:1", **values}


def test_complete_record_preserves_all_fields():
    supplied = {
        "ticker": "SYNTHETIC", "public_event_day": "2025-01-03",
        "filing_date": "2025-01-02", "information_date": "2025-01-02",
        "recent_window_start": "2024-12-04", "recent_window_end": "2025-01-02",
        "historical_window_start": "2023-12-05", "historical_window_end": "2024-12-03",
        "recent_event_count": 2, "historical_event_count": 12,
        "recent_rate": 2 / 30, "historical_rate": 12 / 365,
        "buyers_30d": 2, "rate_ratio": (2 / 30) / (12 / 365),
        "company_reference_size": 12, "sector_reference_size": 40,
        "reference_sample_size": 40, "buyer_reference_size": 38,
        "rate_ratio_reference_size": 35,
        "buyer_count_percentile": 60.0, "rate_ratio_percentile": 51.0,
    }
    supplied.update(ticker="SYNTHETIC", status="complete", missing_reasons=[],
                    activity_score=55.5, reference_rule="sector",
                    canonical_identity_evidence_status="supported",
                    input_snapshot_id="synthetic-snapshot", scoring_policy_version="synthetic-v1",
                    source_provenance={"source": "synthetic"})
    fields = build_activity_diagnostics([record(**supplied)])[0]["fields"]
    assert set(fields) == set(DIAGNOSTIC_FIELDS)
    for name, value in supplied.items():
        assert fields[name] == {"state": "observed", "value": value, "source": "activity_records"}


@pytest.mark.parametrize("status,reasons,extra", [
    ("insufficient_data", ["missing_canonical_insider_identifier"], {"buyers_30d": None}),
    ("zero_historical_rate", ["zero_historical_rate", "rate_ratio_unavailable"],
     {"historical_rate": 0, "historical_event_count": 0, "rate_ratio": None}),
    ("insufficient_data", ["insufficient_rate_ratio_reference_values"],
     {"rate_ratio_reference_size": 9, "rate_ratio_percentile": None}),
])
def test_unavailable_score_preserves_reasons_and_metrics(status, reasons, extra):
    fields = build_activity_diagnostics([record(activity_score=None, status=status,
                                               missing_reasons=reasons, **extra)])[0]["fields"]
    assert fields["activity_score"]["state"] == "unavailable"
    assert fields["status"]["value"] == status
    assert fields["missing_reasons"]["value"] == reasons
    for name, value in extra.items():
        assert fields[name]["value"] == value
    assert fields["canonical_identity_evidence_status"]["state"] == "not_supplied"


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), -float("inf"), pd.NA, pd.NaT, np.nan])
def test_explicit_missing_differs_from_absent(value):
    fields = build_activity_diagnostics([record(activity_score=value)])[0]["fields"]
    assert fields["activity_score"] == {
        "state": "unavailable", "value": None, "source": "activity_records",
    }
    assert fields["source_provenance"] == {
        "state": "not_supplied", "value": None, "source": None,
    }
    assert fields["status"]["state"] == "not_supplied"


def test_metadata_and_nonmutation():
    rows = [record(activity_score=0, missing_reasons=[])]
    metadata = [record(public_event_day=date(2025, 1, 2),
                       source_provenance={"files": ["synthetic.json"]},
                       canonical_identity_evidence_status=None)]
    original = deepcopy((rows, metadata))
    fields = build_activity_diagnostics(rows, metadata_records=metadata)[0]["fields"]
    assert (rows, metadata) == original
    assert fields["public_event_day"]["value"] == "2025-01-02"
    assert fields["canonical_identity_evidence_status"]["state"] == "unavailable"
    assert fields["activity_score"]["state"] == "observed"
    fields["source_provenance"]["value"]["files"].append("changed")
    fields["missing_reasons"]["value"].append("changed")
    assert (rows, metadata) == original


@pytest.mark.parametrize("metadata", [False, True])
def test_duplicate_ids_rejected(metadata):
    rows = [record(), record()]
    with pytest.raises(ValueError, match="duplicate research_event_id"):
        build_activity_diagnostics([record()] if metadata else rows,
                                   metadata_records=rows if metadata else [])


@pytest.mark.parametrize("event_id", [None, "", " ", 1, pd.NA])
def test_invalid_ids_rejected(event_id):
    with pytest.raises(ValueError, match="nonempty string"):
        build_activity_diagnostics([{"research_event_id": event_id}])


def test_unmatched_and_conflicting_metadata_rejected():
    with pytest.raises(ValueError, match="IDs absent"):
        build_activity_diagnostics([], metadata_records=[record()])
    with pytest.raises(ValueError, match="Conflicting activity_score"):
        build_activity_diagnostics([record(activity_score=None)],
                                   metadata_records=[record(activity_score=12)])


def test_deterministic_json_without_external_io(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Exporter must not perform external IO")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(sqlalchemy, "create_engine", forbidden)
    monkeypatch.setattr("builtins.open", forbidden)
    rows = [{"research_event_id": "Z", "activity_score": np.float64(12.5)},
            {"research_event_id": "A", "recent_rate": Decimal("0.125"),
             "insider_name": "must not export", "canonical_insider_id": "must not export"}]
    serialized = activity_diagnostics_json(rows)
    assert serialized == activity_diagnostics_json(reversed(rows))
    output = json.loads(serialized)
    assert [row["research_event_id"] for row in output] == ["A", "Z"]
    assert output[0]["fields"]["recent_rate"]["value"] == "0.125"
    assert "must not export" not in serialized
    assert build_activity_diagnostics([]) == []


def test_unsupported_evidence_rejected():
    with pytest.raises(ValueError, match="Unsupported"):
        build_activity_diagnostics([record(source_provenance=object())])


@pytest.mark.parametrize("collection", ["activity_records", "metadata_records"])
@pytest.mark.parametrize("malformed", [None, 7, "sensitive-record-text", ["sensitive-record-text"]])
def test_nonmapping_rows_have_indexed_sanitized_errors(collection, malformed):
    rows = [record(), malformed]
    with pytest.raises(ValueError) as caught:
        if collection == "activity_records":
            build_activity_diagnostics(rows)
        else:
            build_activity_diagnostics([record()], metadata_records=rows)
    assert str(caught.value) == f"{collection}[1]: expected a mapping"
    assert "sensitive-record-text" not in str(caught.value)


def test_observed_is_presence_not_numeric_validation():
    fields = build_activity_diagnostics([record(activity_score="bad")])[0]["fields"]
    assert fields["activity_score"] == {
        "state": "observed", "value": "bad", "source": "activity_records",
    }
    assert fields["status"]["state"] == "not_supplied"
    assert fields["missing_reasons"]["state"] == "not_supplied"


def test_matching_metadata_and_pandas_timestamps():
    rows = [record(ticker="SYNTHETIC", information_date=pd.Timestamp("2025-01-02"))]
    metadata = [record(ticker="SYNTHETIC", information_date="2025-01-02T00:00:00",
                       public_event_day=pd.Timestamp("2025-01-03", tz="UTC"))]
    original = deepcopy((rows, metadata))
    result = json.loads(activity_diagnostics_json(rows, metadata_records=metadata))[0]["fields"]
    assert result["information_date"] == {
        "state": "observed", "value": "2025-01-02T00:00:00", "source": "activity_records",
    }
    assert result["public_event_day"]["value"] == "2025-01-03T00:00:00+00:00"
    assert result["public_event_day"]["source"] == "metadata_records"
    assert (rows, metadata) == original


def test_nonstring_nested_keys_rejected_without_disclosing_contents():
    with pytest.raises(ValueError) as caught:
        build_activity_diagnostics([record(source_provenance={"nested": {1: "sensitive"}})])
    assert str(caught.value) == "Diagnostic evidence object keys must be strings"


def test_nested_missing_values_serialize_deterministically_without_mutation():
    evidence = {"nested": [None, pd.NA, pd.NaT, np.nan, float("inf"),
                           {"value": Decimal("NaN")}], "count": 0}
    rows = [record(source_provenance=evidence)]
    text = activity_diagnostics_json(rows)
    assert text == activity_diagnostics_json(rows)
    field = json.loads(text)[0]["fields"]["source_provenance"]
    assert field["state"] == "observed"
    assert field["value"] == {"nested": [None, None, None, None, None, {"value": None}], "count": 0}
    assert evidence["nested"][1] is pd.NA
    assert evidence["nested"][2] is pd.NaT
    assert np.isnan(evidence["nested"][3])
    assert evidence["nested"][5]["value"].is_nan()
    detached = build_activity_diagnostics(rows)[0]["fields"]["source_provenance"]["value"]
    detached["nested"][5]["value"] = "changed"
    assert evidence["nested"][5]["value"].is_nan()
