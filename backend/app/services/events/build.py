"""Build one event per ticker/session from normalized SEC provenance."""
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
import re

from .buyers import BuyerEvidence

BUILDER_VERSION = 'issue5-v1'


@dataclass
class Dataset:
    events: list[dict] = field(default_factory=list)
    transactions: list[dict] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)
    duplicate_inputs: int = 0

    def issue(self, row, reason):
        self.issues.append({'transaction_id': row.get('transaction_id'),
                            'accession_number': row.get('accession_number'), 'reason': reason})


def valid_number(value):
    try:
        number = Decimal(str(value))
        return number if number.is_finite() and number >= 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def ownership(row):
    shares, after = valid_number(row.get('shares')), valid_number(row.get('shares_owned_after'))
    if shares is None or after is None:
        return {'prior_shares': None, 'ownership_change_pct': None, 'new_position_flag': None}
    with localcontext() as context:
        context.prec = max(28, len(shares.as_tuple().digits) + len(after.as_tuple().digits) + 4)
        prior = after - shares
        if prior < 0:
            return {'prior_shares': None, 'ownership_change_pct': None, 'new_position_flag': None}
        return {'prior_shares': prior, 'ownership_change_pct': shares / prior if prior else None,
                'new_position_flag': prior == 0}


def role_flags(rows):
    parts = {part.strip().upper() for row in rows for part in (row.get('insider_role') or '').split('|') if part.strip()}
    executive = any(re.search(r'\b(OFFICER|CEO|CFO|COO|CTO|PRESIDENT|CHIEF)\b', part) for part in parts)
    director = any(re.search(r'\bDIRECTOR\b', part) for part in parts)
    other = any(re.search(r'\b(OTHER|TENPERCENTOWNER|10% OWNER)\b', part) for part in parts)
    other = other or not (executive or director)
    cfo = any(re.search(r'\bCFO\b|\bCHIEF FINANCIAL OFFICER\b', part) for part in parts)
    return dict(has_executive=executive, has_director=director, has_other=other,
                has_cfo=cfo if parts else None,
                role_bucket='Executive' if executive else ('Director' if director else 'Other'))


def build_dataset(transactions, prices, universe, buyer_evidence=None):
    """Inputs are existing model dictionaries; this function performs no I/O.

    Buyer evidence is an explicit transaction-id -> supported identities mapping.
    Names and filing-wide owner groups are never used to infer that mapping.
    """
    buyer_evidence = buyer_evidence or {}
    result = Dataset()
    price_rows = {(row['ticker'], row['date']): row for row in prices}
    calendar = sorted({row['date'] for row in prices if row['ticker'] == 'SPY'})
    observed_sessions = sorted({row['date'] for row in prices})
    groups, seen = {}, set()
    for source in transactions:
        row = dict(source)
        key = row['canonical_transaction_key']
        if key in seen:
            result.duplicate_inputs += 1
            result.issue(row, 'duplicate canonical source transaction skipped')
            continue
        seen.add(key)
        if row.get('is_amendment') or row.get('document_type') in {'4-A', '4/A'}:
            result.issue(row, 'amendment preserved; excluded from events pending explicit reconciliation')
            continue
        if not (row.get('document_type') == '4' and row.get('derivative_flag') is False
                and row.get('source_table') == 'NONDERIV_TRANS'
                and row.get('transaction_code') == 'P' and row.get('acquired_or_disposed') == 'A'):
            continue
        filing, transaction = row['filing_date'], row['transaction_date']
        if min(filing, transaction) < date(2020, 1, 1):
            result.issue(row, 'before 2020 event range')
            continue
        if transaction > filing:
            result.issue(row, 'transaction date after filing date; requires source review')
            continue
        resolution = universe.resolve_issuer(row.get('cik'), row.get('ticker'))
        if resolution.ticker is None:
            result.issue(row, f'company mapping {resolution.status}: {resolution.reason}')
            continue
        ticker = resolution.ticker
        index = bisect_right(calendar, filing)
        # A sparse/missing calendar must not silently jump weeks to a later bar.
        if (index == len(calendar) or index == 0
                or (calendar[index] - filing).days > 7
                or (filing - calendar[index - 1]).days > 7):
            result.issue(row, 'missing or insufficient persisted SPY calendar coverage; event day unknown')
            continue
        day = calendar[index]
        observed_index = bisect_right(observed_sessions, filing)
        if observed_index < len(observed_sessions) and observed_sessions[observed_index] < day:
            result.issue(row, 'persisted market session missing from SPY calendar; event day unknown')
            continue
        company = universe.ticker_to_company(ticker)
        row.update(ticker=ticker, public_event_day=day, **ownership(row),
                   company_metadata={'ticker': company.ticker, 'cik': company.cik,
                                     'company_name': company.company_name, 'sector': company.sector})
        result.transactions.append(row)
        groups.setdefault((ticker, day), []).append(row)
    for (ticker, day), rows in sorted(groups.items()):
        information = max(row['filing_date'] for row in rows)
        statuses, identities, evidence_sources = [], set(), set()
        unknown_buyer = False
        for row in rows:
            evidence = buyer_evidence.get(row['transaction_id'])
            if not isinstance(evidence, BuyerEvidence) or not evidence.identities or not evidence.source or any(
                    not isinstance(identity, str) or not identity.strip() for identity in evidence.identities):
                unknown_buyer = True
                result.issue(row, 'buyer identity/count unknown: no reliable transaction-associated evidence')
            else:
                identities.update(evidence.identities)
                evidence_sources.add(evidence.source)
        if unknown_buyer:
            statuses.append('buyer_identity_unknown')
            statuses.append('role_attribution_unverified')
        valid_values = [valid_number(row.get('transaction_value')) for row in rows]
        known_values = [value for value in valid_values if value is not None]
        if len(known_values) != len(rows):
            statuses.append('purchase_value_incomplete')
        # Sum exact decimal values without losing precision on large SEC amounts.
        with localcontext() as context:
            context.prec = max([28] + [len(v.as_tuple().digits) + abs(v.as_tuple().exponent) + 10 for v in known_values])
            total = sum(known_values, Decimal(0)) if known_values else None
        changes = [row['ownership_change_pct'] for row in rows if row['ownership_change_pct'] is not None]
        positions = [row['new_position_flag'] for row in rows]
        new_position = True if True in positions else (None if None in positions else False)
        if None in positions:
            statuses.append('ownership_incomplete')
        if any(not row.get('insider_role') for row in rows):
            statuses.append('role_information_incomplete')
        event_index = bisect_left(calendar, day)
        estimation_dates = [d for d in calendar[max(0, event_index - 120):max(0, event_index - 20)]
                            if d < information]
        def available(symbol, d):
            value = valid_number(price_rows.get((symbol, d), {}).get('analysis_price'))
            return value is not None and value > 0
        # Verify adjacent price inputs without calculating any returns.
        paired = 0
        for d in estimation_dates:
            i = bisect_left(calendar, d)
            if i > 0 and all(available(symbol, label)
                             for symbol in (ticker, 'SPY') for label in (calendar[i - 1], d)):
                paired += 1
        prior_dates = [d for d in calendar[:event_index] if d < information and available(ticker, d)]
        if paired < 60:
            statuses.append('insufficient_market_history')
        if not available(ticker, day):
            statuses.append('missing_stock_event_price')
        metadata = {
            'builder_version': BUILDER_VERSION, 'statuses': statuses,
            'source_transaction_ids': sorted(row['transaction_id'] for row in rows),
            'source_accessions': sorted({row['accession_number'] for row in rows}),
            'filing_dates': sorted({row['filing_date'].isoformat() for row in rows}),
            'buyer_identity_status': 'unknown' if unknown_buyer else 'supported',
            'buyer_evidence_sources': sorted(evidence_sources),
            'market_history': {'estimation_paired_observations': paired, 'minimum_required': 60,
                               'valid_stock_sessions_before_information_date': len(prior_dates),
                               'last_valid_stock_date': prior_dates[-1].isoformat() if prior_dates else None},
            'transaction_ownership': {
                row['transaction_id']: {name: str(row[name]) if isinstance(row[name], Decimal) else row[name]
                                        for name in ('prior_shares', 'ownership_change_pct', 'new_position_flag')}
                for row in rows},
        }
        for status in statuses:
            result.issues.append({'research_event_id': f'{ticker}:{day.isoformat()}', 'reason': status})
        result.events.append(dict(research_event_id=f'{ticker}:{day.isoformat()}', ticker=ticker,
                                  public_event_day=day, information_date=information,
                                  source_transaction_count=len(rows),
                                  source_filing_count=len({row['accession_number'] for row in rows}),
                                  aggregate_purchase_value=total,
                                  unique_buyer_count=None if unknown_buyer else len(identities),
                                  max_valid_ownership_change_pct=max(changes) if changes else None,
                                  any_new_position_flag=new_position, feature_metadata=metadata,
                                  **role_flags(rows)))
    return result
