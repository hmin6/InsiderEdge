"""Small, conservative SEC CompanyFacts normalization; no P0 integration."""
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.models import Company, Fundamental
from app.services.universe import normalize_cik

# Ordered alternatives, never sums of overlapping taxonomy concepts.
TAGS = {
    'cash': ('CashAndCashEquivalentsAtCarryingValue',),
    'equity': ('StockholdersEquity',),
    'revenue': ('RevenueFromContractWithCustomerExcludingAssessedTax',
                'Revenues', 'SalesRevenueNet'),
    'current_assets': ('AssetsCurrent',),
    'current_liabilities': ('LiabilitiesCurrent',),
    'operating_income': ('OperatingIncomeLoss',),
    '_current_debt': ('DebtCurrent',),
    '_noncurrent_debt': ('LongTermDebtNoncurrent',),
}
METRICS = ('cash', 'total_debt', 'equity', 'revenue', 'current_assets',
           'current_liabilities', 'operating_income')
DURATION = {'revenue', 'operating_income'}
FORMS = {'10-K', '10-Q', '10-K/A', '10-Q/A'}


class CompanyFactsProvider:
    def __init__(self, client):
        self.client = client

    def fetch(self, cik):
        issuer = normalize_cik(cik)
        if issuer is None:
            raise ValueError('CompanyFacts requires a known issuer CIK')
        return self.client.json(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{issuer}.json')


def normalize(payload, company, through=None):
    """Return wide historical rows and safe diagnostics. Retain pre-2020 history."""
    through = through or date.today()
    if not isinstance(payload, dict) or normalize_cik(payload.get('cik')) != company.cik:
        raise ValueError('CompanyFacts issuer does not match frozen company')
    taxonomy = payload.get('facts', {}).get('us-gaap', {})
    if not isinstance(taxonomy, dict):
        raise ValueError('Malformed CompanyFacts taxonomy')
    candidates = defaultdict(lambda: defaultdict(list))
    diagnostics = []

    def issue(metric, reason):
        diagnostics.append({'metric': metric, 'reason': reason})

    for metric, tags in TAGS.items():
        for rank, tag in enumerate(tags):
            concept = taxonomy.get(tag)
            if concept is None:
                continue
            if not isinstance(concept, dict) or not isinstance(concept.get('units'), dict):
                issue(metric, f'{tag}: malformed units')
                continue
            units = concept['units']
            for unit in units.keys() - {'USD'}:
                issue(metric, f'{tag}: unsupported unit {unit}')
            facts = units.get('USD', [])
            if not isinstance(facts, list):
                issue(metric, f'{tag}: malformed observations')
                continue
            for fact in facts:
                try:
                    if not isinstance(fact, dict):
                        raise ValueError
                    if fact.get('form') not in FORMS:
                        continue
                    end = date.fromisoformat(fact['end'])
                    filed = date.fromisoformat(fact['filed'])
                    if filed > through:
                        continue
                    if end > filed:
                        raise ValueError
                    start = date.fromisoformat(fact['start']) if 'start' in fact else None
                    if metric in DURATION:
                        if start is None or not 60 <= (end - start).days <= 380:
                            raise ValueError
                    elif start is not None:
                        raise ValueError
                    raw = fact['val']
                    if isinstance(raw, bool) or not isinstance(raw, (int, float, str, Decimal)):
                        raise ValueError
                    value = Decimal(str(raw))
                    if not value.is_finite():
                        raise ValueError
                    # Losses/negative equity are legitimate, negative assets/debt are not.
                    if value < 0 and metric not in {'equity', 'operating_income'}:
                        raise ValueError
                    accn = fact['accn']
                    if not isinstance(accn, str) or not accn.strip():
                        raise ValueError
                    fp = fact.get('fp')
                    fy = fact.get('fy')
                    if fp not in {'FY', 'Q1', 'Q2', 'Q3', 'Q4', None}:
                        raise ValueError
                    if fy is not None and (type(fy) is not int or not 1900 <= fy <= 2200):
                        raise ValueError
                    provenance = {'taxonomy': 'us-gaap', 'tag': tag, 'unit': 'USD',
                                  'start': start.isoformat() if start else None,
                                  'end': end.isoformat(), 'filed': filed.isoformat(),
                                  'form': fact['form'], 'accession': accn,
                                  'fiscal_year': fy, 'fiscal_period': fp}
                    candidates[end, filed, fp][metric].append((rank, start, value, provenance))
                except (KeyError, TypeError, ValueError, InvalidOperation):
                    issue(metric, f'{tag}: malformed value/period/provenance')

    rows = []
    for (end, filed, fp), concepts in sorted(candidates.items(), key=lambda item: str(item[0])):
        selected = {}
        for metric, choices in concepts.items():
            rank = min(x[0] for x in choices)
            choices = [x for x in choices if x[0] == rank]
            # Preserve the shortest reported duration; no YTD-to-quarter arithmetic.
            start = max((x[1] for x in choices if x[1] is not None), default=None)
            choices = [x for x in choices if x[1] == start]
            signatures = {(x[2], json.dumps(x[3], sort_keys=True)) for x in choices}
            if len(signatures) != 1:
                issue(metric, f'ambiguous candidates at {end}/{filed}; skipped')
                continue
            selected[metric] = (choices[0][2], choices[0][3])
        # Debt is complete only when both non-overlapping components share provenance.
        current, noncurrent = selected.get('_current_debt'), selected.get('_noncurrent_debt')
        if current and noncurrent and all(current[1][key] == noncurrent[1][key]
                                         for key in ('accession', 'form', 'end', 'filed')):
            with localcontext() as context:
                context.prec = 50
                debt = current[0] + noncurrent[0]
            selected['total_debt'] = (debt, {'unit': 'USD', 'components': [current[1], noncurrent[1]]})
        elif current or noncurrent:
            issue('total_debt', f'incomplete/incompatible debt components at {end}/{filed}')
        meaningful = {key: value for key, value in selected.items() if key in METRICS}
        identity = json.dumps([company.ticker, end.isoformat(), filed.isoformat(), fp])
        years = {evidence['fiscal_year'] for _, evidence in meaningful.values()
                 if 'fiscal_year' in evidence}
        rows.append({'fundamental_id': 'cf1:' + hashlib.sha256(identity.encode()).hexdigest(),
                     'ticker': company.ticker, 'cik': company.cik, 'report_period': end,
                     'filed_date': filed, 'fiscal_period': fp,
                     'fiscal_year': years.pop() if len(years) == 1 else None,
                     **{metric: meaningful.get(metric, (None,))[0] for metric in METRICS},
                     'currency': 'USD', 'unit_metadata': {
                         'source': 'SEC CompanyFacts', 'identity_version': 'cf1',
                         'metrics': {
                             metric: meaningful[metric][1] if metric in meaningful else {'status': 'unknown'}
                             for metric in METRICS if metric in concepts or metric == 'total_debt'}}})
    for metric in METRICS:
        if not any(row[metric] is not None for row in rows):
            issue(metric, 'missing reliable concept')
    # Keep project-period disclosures plus only the eligible baseline snapshots
    # needed by early-2020 events, rather than backfilling all old fiscal history.
    baseline_ids = set()
    for metric in METRICS:
        older = [row for row in rows if row['filed_date'] < date(2020, 1, 1)
                 and metric in row['unit_metadata']['metrics']]
        if older:
            newest = max((row['report_period'], row['filed_date']) for row in older)
            baseline_ids.update(row['fundamental_id'] for row in older
                                if (row['report_period'], row['filed_date']) == newest)
    return [row for row in rows if row['filed_date'] >= date(2020, 1, 1)
            or row['fundamental_id'] in baseline_ids], diagnostics


def persist(session, company, rows):
    """Atomic caller-owned writes; reject incompatible existing ticker mappings."""
    existing = session.get(Company, company.ticker)
    if existing and normalize_cik(existing.cik) != company.cik:
        raise ValueError('Persisted company CIK conflicts with frozen universe')
    dialect = session.get_bind().dialect.name
    insert = {'postgresql': pg_insert, 'sqlite': sqlite_insert}.get(dialect)
    if insert is None:
        raise ValueError('Unsupported fundamentals database dialect')
    session.execute(insert(Company).values(ticker=company.ticker, cik=company.cik,
                    company_name=company.company_name, sector=company.sector)
                    .on_conflict_do_nothing(index_elements=['ticker']))
    for row in rows:
        if row['ticker'] != company.ticker or row['cik'] != company.cik:
            raise ValueError('Fundamental row identity mismatch')
        statement = insert(Fundamental).values(**row)
        # Replace whole normalized snapshots, including NULLs; no stale component merging.
        session.execute(statement.on_conflict_do_update(
            index_elements=['fundamental_id'],
            set_={key: getattr(statement.excluded, key) for key in row if key != 'fundamental_id'}))
    return len(rows)


def as_of(session, universe, ticker, metric, information_date):
    """Offline metric lookup; newest report end, then newest eligible disclosure."""
    company = universe.ticker_to_company(ticker)
    if company is None:
        raise ValueError('Unknown frozen-universe ticker')
    if metric not in METRICS:
        raise ValueError('Unsupported fundamental metric')
    query = select(Fundamental).where(
        Fundamental.ticker == company.ticker, Fundamental.filed_date <= information_date,
        Fundamental.report_period <= information_date,
    ).order_by(Fundamental.report_period.desc(), Fundamental.filed_date.desc(), Fundamental.fundamental_id)
    eligible = []
    for row in session.scalars(query):
        evidence = (row.unit_metadata or {}).get('metrics', {}).get(metric)
        if evidence is not None:
            eligible.append((row, evidence))
    if not eligible:
        return None
    first = eligible[0][0]
    tied = [(row, evidence) for row, evidence in eligible
            if (row.report_period, row.filed_date) == (first.report_period, first.filed_date)]
    signatures = {(getattr(row, metric), json.dumps(evidence, sort_keys=True)) for row, evidence in tied}
    if len(signatures) != 1:
        return {'value': None, 'report_period': first.report_period, 'filed_date': first.filed_date,
                'provenance': {'status': 'ambiguous eligible observations'}}
    row, evidence = tied[0]
    return {'value': getattr(row, metric), 'report_period': row.report_period,
            'filed_date': row.filed_date, 'provenance': evidence}


def current_ratio(session, universe, ticker, information_date):
    numerator = as_of(session, universe, ticker, 'current_assets', information_date)
    denominator = as_of(session, universe, ticker, 'current_liabilities', information_date)
    if not numerator or not denominator or numerator['value'] is None or denominator['value'] is None:
        return None
    a, b = numerator['provenance'], denominator['provenance']
    if any(a.get(key) != b.get(key) for key in ('accession', 'end', 'filed', 'unit')):
        return None
    if denominator['value'] <= 0:
        return None
    return numerator['value'] / denominator['value']


def ingest(provider, database, universe, tickers=None, through=None, validate_only=False):
    """Sequential issuer requests; shared CIK facts explicitly apply to each selected ticker."""
    companies = universe.companies if tickers is None else tuple(universe.ticker_to_company(t) for t in tickers)
    if any(company is None or company.cik is None for company in companies):
        raise ValueError('Unknown ticker or missing issuer CIK')
    companies = {company.ticker: company for company in companies}.values()
    cache, report = {}, []
    for company in companies:
        stage = 'retrieval'
        try:
            if company.cik not in cache:
                cache[company.cik] = provider.fetch(company.cik)
            stage = 'normalization'
            rows, issues = normalize(cache[company.cik], company, through)
            if not validate_only:
                stage = 'persistence'
                with database.session() as session:
                    persist(session, company, rows)
            report.append({'ticker': company.ticker, 'status': 'ok' if rows else 'unavailable',
                           'rows': len(rows), 'diagnostics': issues})
        except Exception:
            # Do not disclose provider/database exception strings or configuration.
            report.append({'ticker': company.ticker, 'status': 'failed', 'rows': 0,
                           'diagnostics': [{'reason': f'CompanyFacts {stage} failed'}]})
    return report
