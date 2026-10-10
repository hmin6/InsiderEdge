"""Offline C-masking research only. No production imports, IO, fitting or writes.

M is an already-scaled component, not a probability. Provenance is supplied by
an authorized reviewer, never independently authenticated by this utility.
Minimum summary group size is explicit caller policy, not a research conclusion.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
import math
import re
from numbers import Real
from statistics import mean, median

WEIGHTS = {"A": .25, "C": .15, "M": .30, "S": .15, "D": .15}


def _day(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field}: expected ISO calendar date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{field}: expected ISO calendar date") from None
    if parsed.isoformat() != value:
        raise ValueError(f"{field}: expected ISO calendar date")
    return parsed


def _number(value, field):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{field}: expected finite numeric score in [0,100]")
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 100:
        raise ValueError(f"{field}: expected finite numeric score in [0,100]")
    return value


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}: expected nonempty string")
    return value


def _provenance_reasons(row, cutoff):
    """Missing provenance excludes; contradictory/future evidence is an error."""
    evidence = row.get("provenance")
    if evidence is None:
        return ["provenance_not_supplied"]
    if not isinstance(evidence, Mapping):
        raise ValueError("provenance: expected mapping")
    reasons = []
    if evidence.get("reviewed_no_lookahead") is not True:
        reasons.append("no_reviewed_temporal_attestation")
    for key in ("run_id", "artifact_id"):
        value = evidence.get(key)
        if value is None:
            reasons.append(f"missing_{key}")
        elif not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", value):
            raise ValueError(f"{key}: expected a bounded non-sensitive identifier")
    if evidence.get("model_available_at") is None:
        reasons.append("missing_model_availability")
    elif _day(evidence["model_available_at"], "model_available_at") > cutoff:
        raise ValueError("model availability is after information_date")
    components = evidence.get("components")
    if components is None:
        return reasons + ["missing_component_provenance"]
    if not isinstance(components, Mapping):
        raise ValueError("provenance components: expected mapping")
    for name in WEIGHTS:
        item = components.get(name)
        if item is None:
            reasons.append(f"{name}:missing_provenance")
            continue
        if not isinstance(item, Mapping):
            raise ValueError(f"{name}: expected component provenance mapping")
        if item.get("observed") is not True:
            reasons.append(f"{name}:not_attested_observed")
        if item.get("available_at") is None:
            reasons.append(f"{name}:missing_availability")
        elif _day(item["available_at"], f"{name}:available_at") > cutoff:
            raise ValueError(f"{name}: evidence availability is after information_date")
    return reasons


def _ranks(values):
    """Ascending average ranks; equal numerical values receive identical ranks."""
    return [1 + sum(other < value for other in values)
            + .5 * (sum(other == value for other in values) - 1) for value in values]


def _percentile(values, q):
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _metrics(rows):
    signed = [row["signed_error"] for row in rows]
    absolute = [abs(value) for value in signed]
    return {"n": len(rows), "mae": mean(absolute), "median_absolute_error": median(absolute),
            "rmse": math.sqrt(mean(value * value for value in signed)),
            "max_absolute_error": max(absolute), "p90_absolute_error": _percentile(absolute, .90),
            "p95_absolute_error": _percentile(absolute, .95), "signed_bias": mean(signed)}


def _ranking(rows, top_k):
    actual = [row["complete_score"] for row in rows]
    masked = [row["provisional_score"] for row in rows]
    x, y = _ranks(actual), _ranks(masked)
    mx, my = mean(x), mean(y)
    vx, vy = sum((v - mx)**2 for v in x), sum((v - my)**2 for v in y)
    rho = None if vx == 0 or vy == 0 else sum((a-mx)*(b-my) for a,b in zip(x,y)) / math.sqrt(vx*vy)
    inversions, comparable_count, tied_count = 0, 0, 0
    for i, a in enumerate(rows):
        for j in range(i + 1, len(rows)):
            b = rows[j]
            actual_delta = a["complete_score"] - b["complete_score"]
            masked_delta = a["provisional_score"] - b["provisional_score"]
            if actual_delta == 0 or masked_delta == 0:
                tied_count += 1
            else:
                comparable_count += 1
                inversions += actual_delta * masked_delta < 0
    def top(field):
        return {row["research_event_id"] for row in sorted(
            rows, key=lambda row: (-row[field], row["research_event_id"]))[:top_k]}
    return {"spearman": rho, "spearman_reason": "constant_ranks" if rho is None else None,
            "pairwise_inversions": inversions, "strictly_comparable_pairs": comparable_count,
            "tied_pairs_excluded": tied_count, "top_k": top_k,
            "top_k_overlap_count": len(top("complete_score") & top("provisional_score")),
            "top_k_overlap_fraction": len(top("complete_score") & top("provisional_score")) / top_k}


def evaluate_c_masking(records: Iterable[Mapping], *, minimum_group_size: int, top_k: int) -> dict:
    """Evaluate explicit complete vectors, grouped by context AND information date.

    Required: research_event_id, ticker, information_date, ranking_context,
    evidence_kind ('historical'/'synthetic'), components {A,C,M,S,D} on [0,100].
    Optional official_score must agree with formula (absolute tolerance 1e-9).
    Missing components are excluded, malformed values rejected. Missing historical
    provenance excludes primary inference. See report for attestation fields.
    Synthetic rows are never primary historical results. No cross-date ranks.
    Summary threshold and top-k must be predeclared by caller, not optimized here.
    Returned rows contain scalar copies only, never references to source mappings.
    """
    if type(minimum_group_size) is not int or minimum_group_size < 2:
        raise ValueError("minimum_group_size must be an integer >=2")
    if type(top_k) is not int or not 1 <= top_k < minimum_group_size:
        raise ValueError("top_k must be an integer below minimum_group_size")
    output, excluded, seen = [], [], set()
    for index, row in enumerate(records):
        if not isinstance(row, Mapping):
            raise ValueError(f"records[{index}]: expected mapping")
        identity = _text(row.get("research_event_id"), "research_event_id")
        if identity in seen:
            raise ValueError("duplicate research_event_id")
        seen.add(identity)
        ticker = _text(row.get("ticker"), "ticker")
        cutoff = _day(row.get("information_date"), "information_date")
        context = _text(row.get("ranking_context"), "ranking_context")
        kind = row.get("evidence_kind")
        if kind not in ("historical", "synthetic"):
            raise ValueError("evidence_kind must be historical or synthetic")
        components = row.get("components")
        if not isinstance(components, Mapping) or set(components) != set(WEIGHTS):
            raise ValueError("components must contain exactly A,C,M,S,D")
        missing = [name for name in WEIGHTS if components[name] is None]
        values = {name: _number(value, name) for name,value in components.items() if value is not None}
        if missing:
            excluded.append({"research_event_id": identity, "reasons": [f"{n}:missing" for n in missing],
                             "evidence_kind": kind, "ranking_context": context,
                             "information_date": cutoff.isoformat()})
            continue
        complete = sum(WEIGHTS[name]*values[name] for name in WEIGHTS)
        if row.get("official_score") is not None:
            official = _number(row["official_score"], "official_score")
            if not math.isclose(official, complete, rel_tol=0, abs_tol=1e-9):
                raise ValueError("official_score disagrees with complete formula")
        reasons = _provenance_reasons(row, cutoff)
        category = "synthetic" if kind == "synthetic" else (
            "historical_eligible" if not reasons else "historical_provenance_incomplete")
        provisional = sum(WEIGHTS[name]*values[name] for name in WEIGHTS if name != "C") / .85
        provenance_references = None
        if category == "historical_eligible":
            evidence = row["provenance"]
            provenance_references = {
                "run_id": evidence["run_id"], "artifact_id": evidence["artifact_id"],
                "model_available_at": evidence["model_available_at"],
                "component_available_at": {
                    name: evidence["components"][name]["available_at"] for name in WEIGHTS},
            }
        output.append({"research_event_id": identity, "ticker": ticker,
                       "information_date": cutoff.isoformat(), "ranking_context": context,
                       "category": category, "exclusion_reasons": reasons,
                       "provenance_references": provenance_references,
                       "complete_score": complete, "provisional_score": provisional,
                       "observed_weight": .85, "masked_component": "C",
                       "signed_error": provisional-complete, "absolute_error": abs(provisional-complete)})
    output.sort(key=lambda row: row["research_event_id"])
    excluded.sort(key=lambda row: row["research_event_id"])
    primary = [row for row in output if row["category"] == "historical_eligible"]
    groups = {}
    for row in primary:
        groups.setdefault((row["ranking_context"],row["information_date"]), []).append(row)
    summaries = []
    for (context, day), rows in sorted(groups.items()):
        enough = len(rows) >= minimum_group_size
        summaries.append({"ranking_context":context, "information_date":day, "n":len(rows),
                          "status":"available" if enough else "insufficient_data",
                          "metrics":_metrics(rows) if enough else None,
                          "ranking":_ranking(rows,top_k) if enough else None})
    return {"rows":output, "excluded":excluded, "eligible_historical_count":len(primary),
            "minimum_group_size":minimum_group_size, "top_k":top_k,
            "status":"available" if any(g["status"]=="available" for g in summaries) else "insufficient_data",
            "groups":summaries, "theoretical_absolute_error_bound":15.0}
