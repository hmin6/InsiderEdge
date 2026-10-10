"""Synthetic CompanyFacts tests; ordinary validation never contacts SEC/Tiger."""
from contextlib import contextmanager
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from app.db.models import Base, Company, Fundamental
from app.services.companyfacts import (
    CompanyFactsProvider, METRICS, as_of, current_ratio, ingest, normalize, persist,
)
from app.services.sec.client import SecClient, SecRequestError
from app.services.universe import Universe


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError('Unexpected live SEC request')
    monkeypatch.setattr(SecClient, 'get', fail)


@pytest.fixture
def universe():
    return Universe.from_csv()


def fact(value=100, **overrides):
    return {'val': value, 'end': '2020-06-30', 'filed': '2020-08-05',
            'form': '10-Q', 'accn': 'synthetic-q2', 'fy': 2020, 'fp': 'Q2', **overrides}


def payload(universe, tags=None, ticker='AAPL'):
    tags = tags or {'CashAndCashEquivalentsAtCarryingValue': [fact()]}
    return {'cik': int(universe.ticker_to_cik(ticker)), 'facts': {'us-gaap': {
        tag: {'units': {'USD': values}} for tag, values in tags.items()}}}


@pytest.fixture
def session():
    engine = create_engine('sqlite://')
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def store(session, universe, source):
    company = universe.ticker_to_company('AAPL')
    rows, diagnostics = normalize(source, company)
    persist(session, company, rows)
    session.flush()
    return rows, diagnostics


def test_known_concepts_units_provenance(universe):
    source = payload(universe, {
        'CashAndCashEquivalentsAtCarryingValue': [fact(100)],
        'StockholdersEquity': [fact(-10)],
        'AssetsCurrent': [fact(200)], 'LiabilitiesCurrent': [fact(50)],
        'DebtCurrent': [fact(30)], 'LongTermDebtNoncurrent': [fact(70)],
        'RevenueFromContractWithCustomerExcludingAssessedTax': [fact(400, start='2020-04-01')],
        'OperatingIncomeLoss': [fact(-20, start='2020-04-01')],
    })
    rows, diagnostics = normalize(source, universe.ticker_to_company('AAPL'))
    assert not diagnostics
    row = rows[0]
    assert [row[m] for m in METRICS] == list(map(Decimal, [100, 100, -10, 400, 200, 50, -20]))
    assert row['report_period'] == date(2020, 6, 30)
    assert row['filed_date'] == date(2020, 8, 5)
    assert row['currency'] == 'USD'
    assert row['unit_metadata']['metrics']['revenue']['start'] == '2020-04-01'


def test_missing_concept(universe):
    rows, issues = normalize(payload(universe), universe.ticker_to_company('AAPL'))
    assert rows[0]['revenue'] is None
    assert any(i['metric'] == 'revenue' and 'missing' in i['reason'] for i in issues)


@pytest.mark.parametrize('value', [True, None, 'bad', 'NaN', 'Infinity', -1, {}, []])
def test_malformed_values(universe, value):
    rows, issues = normalize(payload(universe, {'AssetsCurrent': [fact(value)]}),
                             universe.ticker_to_company('AAPL'))
    assert rows == []
    assert any('malformed' in i['reason'] for i in issues)


def test_unsupported_unit(universe):
    source = payload(universe)
    source['facts']['us-gaap']['CashAndCashEquivalentsAtCarryingValue']['units'] = {'EUR': [fact()]}
    rows, issues = normalize(source, universe.ticker_to_company('AAPL'))
    assert not rows
    assert any('unsupported unit EUR' in i['reason'] for i in issues)


def test_duplicates_conflicts_and_tag_priority(universe):
    source = payload(universe, {'Revenues': [fact(200, start='2020-04-01')] * 2,
                               'SalesRevenueNet': [fact(999, start='2020-04-01')]})
    rows, _ = normalize(source, universe.ticker_to_company('AAPL'))
    assert rows[0]['revenue'] == 200
    source['facts']['us-gaap']['Revenues']['units']['USD'].append(fact(300, start='2020-04-01'))
    rows, issues = normalize(source, universe.ticker_to_company('AAPL'))
    assert rows[0]['revenue'] is None  # Never choose the lower-priority fallback after conflict.
    assert any('ambiguous' in i['reason'] for i in issues)


def test_duration_preference_and_period_retained(universe):
    source = payload(universe, {'Revenues': [fact(700, start='2020-01-01'), fact(300, start='2020-04-01')]})
    rows, _ = normalize(source, universe.ticker_to_company('AAPL'))
    assert rows[0]['revenue'] == 300
    assert rows[0]['unit_metadata']['metrics']['revenue']['start'] == '2020-04-01'


def test_provider_mapping_and_shared_cik(universe):
    class Client:
        def json(self, url):
            assert url == f'https://data.sec.gov/api/xbrl/companyfacts/CIK{universe.ticker_to_cik("GOOG")}.json'
            return payload(universe, ticker='GOOG')
    provider = CompanyFactsProvider(Client())
    result = ingest(provider, None, universe, ['GOOG', 'GOOGL'], validate_only=True)
    assert [(r['ticker'], r['status']) for r in result] == [('GOOG', 'ok'), ('GOOGL', 'ok')]
    a, _ = normalize(provider.fetch(universe.ticker_to_cik('GOOG')), universe.ticker_to_company('GOOG'))
    b, _ = normalize(provider.fetch(universe.ticker_to_cik('GOOGL')), universe.ticker_to_company('GOOGL'))
    assert a[0]['fundamental_id'] != b[0]['fundamental_id']


def test_unknown_rejected_before_provider(universe):
    with pytest.raises(ValueError, match='Unknown'):
        ingest(None, None, universe, ['UNKNOWN'], validate_only=True)


def test_wrong_issuer_rejected(universe):
    source = payload(universe)
    source['cik'] = 1
    with pytest.raises(ValueError, match='issuer'):
        normalize(source, universe.ticker_to_company('AAPL'))


def test_idempotency_and_temporal_revisions(session, universe):
    source = payload(universe, {'AssetsCurrent': [fact(100), fact(150, filed='2020-08-10', accn='synthetic-amend', form='10-Q/A')]})
    store(session, universe, source)
    store(session, universe, source)
    assert session.scalar(select(func.count()).select_from(Fundamental)) == 2
    assert as_of(session, universe, 'AAPL', 'current_assets', date(2020, 8, 1)) is None
    assert as_of(session, universe, 'aapl', 'current_assets', date(2020, 8, 5))['value'] == 100
    assert as_of(session, universe, 'AAPL', 'current_assets', date(2020, 8, 9))['value'] == 100
    assert as_of(session, universe, 'AAPL', 'current_assets', date(2020, 8, 10))['value'] == 150
    assert as_of(session, universe, 'AAPL', 'cash', date(2020, 8, 10)) is None


def test_no_backward_fill_pre2020_and_newest_period(session, universe):
    source = payload(universe, {'AssetsCurrent': [fact(10, end='2019-09-30', filed='2019-11-01'),
               fact(20), fact(15, end='2019-09-30', filed='2020-09-01', accn='synthetic-comparative')]})
    store(session, universe, source)
    assert as_of(session, universe, 'AAPL', 'current_assets', date(2020, 1, 1))['value'] == 10
    assert as_of(session, universe, 'AAPL', 'current_assets', date(2020, 9, 2))['value'] == 20


def test_ambiguous_revision_blocks_old_value(session, universe):
    source = payload(universe, {'AssetsCurrent': [fact(10), fact(20, filed='2020-08-10'), fact(30, filed='2020-08-10')]})
    store(session, universe, source)
    result = as_of(session, universe, 'AAPL', 'current_assets', date(2020, 8, 10))
    assert result['value'] is None
    assert result['provenance']['status'] == 'unknown'


@pytest.mark.parametrize('liability, accession, expected', [(50, 'synthetic-q2', Decimal(4)),
    (0, 'synthetic-q2', None), (50, 'other-filing', None), (None, 'synthetic-q2', None)])
def test_ratio_compatibility(session, universe, liability, accession, expected):
    tags = {'AssetsCurrent': [fact(200)]}
    if liability is not None:
        tags['LiabilitiesCurrent'] = [fact(liability, accn=accession)]
    store(session, universe, payload(universe, tags))
    assert current_ratio(session, universe, 'AAPL', date(2020, 8, 5)) == expected
    assert current_ratio(session, universe, 'AAPL', date(2020, 8, 4)) is None


def test_debt_missing_component_never_zero(universe):
    rows, issues = normalize(payload(universe, {'DebtCurrent': [fact(10)]}), universe.ticker_to_company('AAPL'))
    assert rows[0]['total_debt'] is None
    assert any('incomplete' in i['reason'] for i in issues)


def test_provider_failure_sanitized(universe):
    class Provider:
        def fetch(self, cik):
            raise SecRequestError('synthetic secret must not appear')
    result = ingest(Provider(), None, universe, ['AAPL'], validate_only=True)
    assert result[0]['status'] == 'failed'
    assert 'synthetic secret' not in str(result)


def test_cutoff_and_invalid_periods(universe):
    rows, _ = normalize(payload(universe), universe.ticker_to_company('AAPL'), date(2020, 8, 4))
    assert not rows
    rows, issues = normalize(payload(universe, {'AssetsCurrent': [fact(end='2021-01-01')]}),
                             universe.ticker_to_company('AAPL'))
    assert not rows
    assert any('malformed' in i['reason'] for i in issues)


def test_batch_persistence_once_per_issuer(session, universe):
    class Provider:
        calls = 0
        def fetch(self, cik):
            self.calls += 1
            return payload(universe, ticker='GOOG')
    class Database:
        @contextmanager
        def session(self):
            yield session
    provider = Provider()
    result = ingest(provider, Database(), universe, ['GOOG', 'GOOGL'])
    assert provider.calls == 1
    assert all(r['status'] == 'ok' for r in result)
    assert session.scalar(select(func.count()).select_from(Fundamental)) == 2


def test_conflicting_company_mapping_not_overwritten(session, universe):
    session.add(Company(ticker='AAPL', cik='0000000001', company_name='Synthetic conflict'))
    session.flush()
    rows, _ = normalize(payload(universe), universe.ticker_to_company('AAPL'))
    with pytest.raises(ValueError, match='conflicts'):
        persist(session, universe.ticker_to_company('AAPL'), rows)
    assert session.get(Company, 'AAPL').cik == '0000000001'
    assert session.scalar(select(func.count()).select_from(Fundamental)) == 0


def test_cross_fiscal_period_ambiguity_is_not_guessed(session, universe):
    source = payload(universe, {'AssetsCurrent': [fact(100), fact(200, fp='FY')]})
    store(session, universe, source)
    result = as_of(session, universe, 'AAPL', 'current_assets', date(2020, 8, 5))
    assert result['value'] is None
    assert 'ambiguous' in result['provenance']['status']


def test_cli_validate_only_and_explicit_selection(monkeypatch, tmp_path, universe, capsys):
    from scripts import ingest_fundamentals
    import sys
    monkeypatch.setattr(CompanyFactsProvider, 'fetch', lambda self, cik: payload(universe))
    monkeypatch.setenv('SEC_USER_AGENT', 'Synthetic Fixture Contact')
    monkeypatch.setattr(ingest_fundamentals, 'load_dotenv', lambda *a, **kw: None)
    monkeypatch.setattr(sys, 'argv', ['ingest_fundamentals', '--ticker', 'AAPL',
                        '--validate-only', '--report', str(tmp_path / 'report.json')])
    ingest_fundamentals.main()
    assert 'AAPL: ok' in capsys.readouterr().out
    assert (tmp_path / 'report.json').exists()
    monkeypatch.setattr(sys, 'argv', ['ingest_fundamentals'])
    with pytest.raises(SystemExit) as failure:
        ingest_fundamentals.main()
    assert failure.value.code == 2
