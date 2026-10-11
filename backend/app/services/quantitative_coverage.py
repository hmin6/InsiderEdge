"""Read-only descriptive coverage; no model execution or serving-score mutation."""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import math

from sqlalchemy import select
from app.db.models import InsiderTransaction


WEIGHTS = {'A': .25, 'C': .15, 'M': .30, 'S': .15, 'D': .15}
FIELDS = {'A': 'anomaly_score', 'C': 'activity_score', 'M': 'model_probability',
          'S': 'statistical_score', 'D': 'dislocation_score'}


def estimated_activity_index(purchase_count, purchase_value):
    """Product heuristic, not calibrated inference; callers must validate lineage."""
    if isinstance(purchase_count, bool) or not isinstance(purchase_count, int) or purchase_count < 0:
        return None
    if isinstance(purchase_value, bool) or not isinstance(purchase_value, (int, float, Decimal)):
        return None
    try:
        value = Decimal(str(purchase_value))
        if not value.is_finite() or value < 0:
            return None
        # Saturate before float conversion, including very large valid Decimals.
        value_component = 1.0 if value >= Decimal('99999999') else math.log10(1 + float(value)) / 8
        count_component = min(5, purchase_count) / 5
        return max(0.0, min(100.0, 100 * (.70 * value_component + .30 * count_component)))
    except (InvalidOperation, OverflowError, ValueError):
        return None


def _known_chronology(value, cutoff):
    """Reject known source/outcome availability violations; absence proves nothing."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key == 'comparators':
                if not isinstance(item, list):
                    return False
                identities = []
                for comparator in item:
                    if not isinstance(comparator, dict):
                        return False
                    identity = comparator.get('research_event_id')
                    if not isinstance(identity, str) or not identity:
                        return False
                    identities.append(identity)
                    try:
                        if date.fromisoformat(comparator['information_date']) >= cutoff or date.fromisoformat(comparator['car30_end']) >= cutoff:
                            return False
                    except (KeyError, ValueError, TypeError):
                        return False
                if len(set(identities)) != len(identities):
                    return False
            if key in {'source_date', 'available_at', 'model_available_at', 'component_available_at', 'car30_end', 'last_valid_stock_date',
                       'training_cutoff', 'validation_outcome_end', 'selected_at', 'activated_at'} and item is not None:
                if isinstance(item, dict):
                    if not all(_known_chronology({'available_at': v}, cutoff) for v in item.values()):
                        return False
                else:
                    try:
                        text = str(item)
                        if len(text) == 10:
                            day = date.fromisoformat(text)
                        else:
                            timestamp = datetime.fromisoformat(text.replace('Z', '+00:00'))
                            if timestamp.tzinfo is None:
                                return False
                            day = timestamp.astimezone(timezone.utc).date()
                    except (ValueError, TypeError):
                        return False
                    if day > cutoff or (key in {'car30_end', 'last_valid_stock_date'} and day >= cutoff):
                        return False
            if isinstance(item, (dict, list)) and not _known_chronology(item, cutoff):
                return False
    elif isinstance(value, list):
        return all(_known_chronology(item, cutoff) for item in value)
    return True


def _provisional(event, signal, result):
    if signal is None:
        result['reasons'].append('no_persisted_component_evidence')
        return
    if (signal.research_event_id != event.research_event_id or signal.ticker != event.ticker
            or signal.public_event_day != event.public_event_day
            or signal.score_status not in {'partial', 'insufficient_data'}
            or event.information_date >= event.public_event_day or event.information_date >= date.today()):
        result['reasons'].append('invalid_signal_identity_status_or_timing')
        return
    if event.feature_metadata is not None and not isinstance(event.feature_metadata, dict):
        result['reasons'].append('malformed_event_evidence')
        return
    evidence = (event.feature_metadata or {}).get('signal_api_evidence_v1')
    if evidence is not None:
        from app.services.research_reads import signal_binding
        try:
            if (not isinstance(evidence, dict)
                    or evidence.get('binding') != signal_binding(signal)
                    or evidence.get('information_date') != event.information_date.isoformat()
                    or not _known_chronology(evidence, event.information_date)):
                raise ValueError
        except (ValueError, TypeError, AttributeError, OverflowError):
            result['reasons'].append('inconsistent_or_future_signal_evidence')
            return
    if not _known_chronology(event.feature_metadata, event.information_date):
        result['reasons'].append('invalid_or_future_component_availability')
        return
    unavailable = signal.unavailable_components
    if (not isinstance(unavailable, list) or any(not isinstance(k, str) or k not in WEIGHTS for k in unavailable)
            or len(set(unavailable)) != len(unavailable)):
        result['reasons'].append('invalid_missing_component_declaration')
        return
    values = {}
    for key, field in FIELDS.items():
        raw = getattr(signal, field)
        if raw is None:
            if key not in unavailable:
                result['reasons'].append('contradictory_missing_component_declaration')
                return
            continue
        if isinstance(raw, bool) or not isinstance(raw, (int, float, Decimal)):
            result['reasons'].append('invalid_component_value')
            return
        try:
            value = float(raw)
            valid = math.isfinite(value) and 0 <= raw <= (1 if key == 'M' else 100)
        except (ValueError, TypeError, OverflowError, InvalidOperation):
            valid = False
        if not valid or key in unavailable:
            result['reasons'].append('invalid_or_contradictory_component_value')
            return
        values[key] = value * 100 if key == 'M' else value
    result['available_components'] = list(values)
    result['missing_components'] = [key for key in WEIGHTS if key not in values]
    coverage = math.fsum(WEIGHTS[key] for key in values)
    result['coverage_weight'] = coverage
    if len(values) == 5:
        result['reasons'].append('all_components_available_use_canonical_score')
    elif len(values) < 2 or coverage < .50:
        result['reasons'].append('insufficient_component_count_or_weight')
    else:
        result['partial_index'] = math.fsum(WEIGHTS[key] * value for key, value in values.items()) / coverage
        result['status'] = 'provisional'


def quantitative_coverage(session, event, signal):
    """Validate retained event lineage against source rows, not aggregate presence.

    Filing dates attest public availability, not immutable input snapshot history.
    Provisional display explicitly accepts incomplete historical provenance.
    Known contradictions still invalidate the index; no prediction is invented.
    """
    if signal is not None and signal.score_status == 'complete':
        return None
    result = dict(status='unavailable', purchase_count=None, purchase_value=None,
                  information_date=event.information_date, partial_index=None,
                  estimated_activity_index=None, estimated_activity_method='fixed_activity_v1',
                  coverage_weight=0.0, available_components=[], missing_components=list('ACMSD'),
                  calculation_method='observed_weight_renormalization',
                  reasons=[], imputed_components=[], imputation_method=None,
                  provenance_limitations=['Persisted source records and caller-attested event lineage; not independently authenticated immutable evidence.'])
    _provisional(event, signal, result)
    metadata = event.feature_metadata
    ids = metadata.get('source_transaction_ids') if isinstance(metadata, dict) else None
    accessions = metadata.get('source_accessions') if isinstance(metadata, dict) else None
    if (not isinstance(ids, list) or not ids or any(not isinstance(i, str) or not i for i in ids)
            or len(set(ids)) != len(ids) or metadata.get('builder_version') != 'issue5-v1'
            or not isinstance(accessions, list) or not accessions
            or any(not isinstance(a, str) or not a for a in accessions)):
        result['reasons'].append('missing_or_invalid_event_source_lineage')
        return result
    rows = list(session.scalars(select(InsiderTransaction).where(InsiderTransaction.transaction_id.in_(ids))))
    if (len(rows) != len(ids) or len(rows) != event.source_transaction_count
            or set(accessions) != {row.accession_number for row in rows}
            or len(set(accessions)) != event.source_filing_count
            or event.information_date >= event.public_event_day or event.information_date >= date.today()
            or any(row.ticker != event.ticker or row.public_event_day != event.public_event_day
                   or not row.is_p0_qualifying or row.transaction_code != 'P'
                   or row.acquired_or_disposed != 'A' or row.derivative_flag or row.is_amendment
                   or row.document_type != '4' or row.source_table != 'NONDERIV_TRANS'
                   or row.filing_date is None or row.transaction_date is None
                   or row.transaction_date > row.filing_date or row.filing_date > event.information_date
                   for row in rows)
            or max(row.filing_date for row in rows) != event.information_date):
        result['reasons'].append('inconsistent_or_future_event_source_lineage')
        return result
    result['purchase_count'] = len(rows)
    if result['partial_index'] is None:
        result['status'] = 'descriptive_only'
    try:
        values = [Decimal(str(row.transaction_value)) for row in rows]
        if any(not value.is_finite() or value < 0 for value in values):
            raise InvalidOperation
        with localcontext() as context:
            context.prec = max([28] + [len(v.as_tuple().digits) + abs(v.as_tuple().exponent) + 10 for v in values])
            total = sum(values, Decimal(0))
        if not math.isfinite(float(total)) or event.aggregate_purchase_value is None or total != event.aggregate_purchase_value:
            raise InvalidOperation
        result['purchase_value'] = total
    except (InvalidOperation, ValueError, OverflowError):
        result['reasons'].append('purchase_value_missing_or_inconsistent')
    result['estimated_activity_index'] = estimated_activity_index(result['purchase_count'], result['purchase_value'])
    result['reasons'].extend(['canonical_buyer_mapping_not_retained', 'point_in_time_price_snapshot_not_retained'])
    return result
