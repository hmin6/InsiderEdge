"""Issue #6 HTTP contract checks with isolated synthetic database records."""
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import re
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event, select, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_session
from app.api.schemas import (
    CompanyResponse, InsiderTransaction as TransactionResponse, InsidersResponse,
    PricePoint, PricesResponse, RadarItem, RadarResponse, ResearchEventSummary,
)
from app.db.models import Base, Company, InsiderTransaction, Price, ResearchEvent, Signal
from app.main import create_app


def research(ticker='AAPL', day=date(2026, 10, 2), **changes):
    values = dict(research_event_id=f'{ticker}:{day}', ticker=ticker, public_event_day=day,
                  information_date=date(2026, 10, 1), source_transaction_count=1,
                  source_filing_count=1, aggregate_purchase_value=Decimal('12.5'),
                  unique_buyer_count=None, role_bucket='Other', has_executive=False,
                  has_director=False, has_other=True)
    values.update(changes)
    return ResearchEvent(**values)


def transaction(identifier='synthetic-one', **changes):
    values = dict(transaction_id=identifier, canonical_transaction_key=identifier,
                  accession_number='0000000001-26-000001', source_type='edgar',
                  ticker='AAPL', cik='0000320193', document_type='4',
                  transaction_date=date(2026, 9, 29), filing_date=date(2026, 10, 1),
                  public_event_day=date(2026, 10, 2), transaction_code='P',
                  acquired_or_disposed='A', derivative_flag=False, source_table='NONDERIV_TRANS',
                  shares=Decimal('5'), price=Decimal('2.5'), transaction_value=Decimal('12.5'),
                  is_amendment=False, is_p0_qualifying=True)
    values.update(changes)
    return InsiderTransaction(**values)


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.delenv('CORS_ORIGINS', raising=False)
    monkeypatch.setattr('app.services.sec.client.SecClient.get', Mock(side_effect=AssertionError('No SEC requests allowed')))
    monkeypatch.setattr('app.services.market.provider.YFinanceProvider.fetch', Mock(side_effect=AssertionError('No Yahoo requests allowed')))
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    app = create_app()
    def session_override():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_session] = session_override
    with TestClient(app) as client:
        yield client, engine, app
    engine.dispose()


def seed(engine):
    with Session(engine) as session, session.begin():
        session.add(Company(ticker='AAPL', cik='0000320193', company_name='Synthetic Apple',
                            sector='Information Technology', industry=None))


def test_health_and_empty_radar(setup):
    client, _, app = setup
    assert client.get('/health').json() == {'status': 'ok'}
    response = client.get('/api/radar')
    assert response.status_code == 200 and response.json() == {'items': []}
    RadarResponse.model_validate(response.json())
    assert app.state.database is None


@pytest.mark.parametrize('ticker,canonical', [('aapl', 'AAPL'), ('%20aapl%20', 'AAPL'),
                                             ('BRK-B', 'BRK.B'), ('brk.b', 'BRK.B'),
                                             ('goog', 'GOOG'), ('googl', 'GOOGL')])
def test_company_normalization_and_frozen_fallback(setup, ticker, canonical):
    client, _, _ = setup
    response = client.get(f'/api/companies/{ticker}')
    assert response.status_code == 200
    data = response.json()
    assert data['ticker'] == canonical and data['company_name']
    assert data['latest_public_event_day'] is None and data['latest_signal'] is None
    assert data['industry'] is None
    assert set(data) == set(CompanyResponse.model_fields)


@pytest.mark.parametrize('suffix', ['', '/prices', '/insiders'])
@pytest.mark.parametrize('ticker', ['UNKNOWN', 'bad%24ticker', 'AAPL%27%20OR%201%3D1'])
def test_unknown_and_invalid_ticker_404(setup, ticker, suffix):
    client, _, _ = setup
    response = client.get(f'/api/companies/{ticker}{suffix}')
    assert response.status_code == 404
    assert response.json() == {'detail': 'Unknown ticker'}


def test_company_metadata_latest_day_and_precomputed_signal(setup):
    client, engine, _ = setup
    seed(engine)
    with Session(engine) as session, session.begin():
        row = research()
        session.add(row)
        session.flush()
        session.add(Signal(signal_id='synthetic-signal', research_event_id=row.research_event_id,
                           ticker='AAPL', public_event_day=row.public_event_day,
                           insider_edge_score=Decimal('42.5'), model_probability=Decimal('0.25'),
                           score_status='partial', unavailable_components=['S']))
    data = client.get('/api/companies/aapl').json()
    assert data['company_name'] == 'Synthetic Apple'
    assert data['latest_public_event_day'] == '2026-10-02'
    assert data['latest_signal']['insider_edge_score'] == 42.5
    assert data['latest_signal']['ml_outperformance_probability'] == 0.25
    assert data['latest_signal']['unavailable_components'] == ['S']
    CompanyResponse.model_validate(data)


def test_unscored_latest_event_does_not_reuse_older_signal(setup):
    client, engine, _ = setup
    seed(engine)
    with Session(engine) as session, session.begin():
        old, new = research(), research(day=date(2026, 10, 5))
        session.add_all([old, new])
        session.flush()
        session.add(Signal(signal_id='older', research_event_id=old.research_event_id,
                           ticker='AAPL', public_event_day=old.public_event_day,
                           insider_edge_score=99, score_status='complete', unavailable_components=[]))
    data = client.get('/api/companies/AAPL').json()
    assert data['latest_public_event_day'] == '2026-10-05' and data['latest_signal'] is None
    item = client.get('/api/radar').json()['items'][0]
    assert item['public_event_day'] == '2026-10-05' and item['insider_edge_score'] is None
    assert item['score_status'] == 'insufficient_data'
    assert set(item['unavailable_components']) == {'A', 'C', 'M', 'S', 'D'}


def test_radar_numeric_order_null_last_and_constant_query_count(setup):
    client, engine, _ = setup
    with Session(engine) as session, session.begin():
        for ticker in ('AAPL', 'CRM', 'MSFT', 'GOOG', 'GOOGL'):
            session.add(Company(ticker=ticker, company_name=f'Synthetic {ticker}'))
        session.flush()
        events = [research(ticker) for ticker in ('AAPL', 'CRM', 'MSFT', 'GOOG', 'GOOGL')]
        session.add_all(events)
        session.flush()
        for row, score in zip(events, [0, 80, 20]):
            session.add(Signal(signal_id=row.ticker, research_event_id=row.research_event_id,
                               ticker=row.ticker, public_event_day=row.public_event_day,
                               insider_edge_score=score, score_status='partial', unavailable_components=['S']))
    statements = []
    def record(connection, cursor, statement, parameters, context, many):
        statements.append(statement)
    event.listen(engine, 'before_cursor_execute', record)
    try:
        response = client.get('/api/radar')
    finally:
        event.remove(engine, 'before_cursor_execute', record)
    assert response.status_code == 200
    items = response.json()['items']
    assert [row['ticker'] for row in items] == ['CRM', 'MSFT', 'AAPL', 'GOOG', 'GOOGL']
    assert items[2]['insider_edge_score'] == 0 and items[3]['insider_edge_score'] is None
    assert all(set(row) == set(RadarItem.model_fields) for row in items)
    RadarResponse.model_validate(response.json())
    assert len(statements) == 1


def test_prices_are_chronological_numeric_and_nullable(setup):
    client, engine, _ = setup
    with Session(engine) as session, session.begin():
        session.add_all([Price(ticker='AAPL', date=date(2026, 10, 2), close=Decimal('12.5'),
                               adjusted_close=Decimal('12'), analysis_price=Decimal('12'), volume=42),
                         Price(ticker='AAPL', date=date(2026, 10, 1))])
    response = client.get('/api/companies/aapl/prices')
    assert response.status_code == 200
    data = response.json()
    assert [row['date'] for row in data['prices']] == ['2026-10-01', '2026-10-02']
    assert data['prices'][0]['analysis_price'] is None and data['prices'][0]['volume'] is None
    assert data['prices'][1]['close'] == 12.5 and isinstance(data['prices'][1]['volume'], int)
    assert 'ticker' not in data['prices'][0]
    PricesResponse.model_validate(data)


def test_empty_known_company_collections(setup):
    client, _, _ = setup
    assert client.get('/api/companies/AAPL/prices').json() == {'ticker': 'AAPL', 'prices': []}
    assert client.get('/api/companies/AAPL/insiders').json() == {'ticker': 'AAPL', 'transactions': [], 'research_events': []}


def test_insider_provenance_dates_amendments_and_unknown_buyer_count(setup):
    client, engine, _ = setup
    seed(engine)
    with Session(engine) as session, session.begin():
        session.add_all([transaction(), transaction('amendment', document_type='4-A', is_amendment=True,
                                                    filing_date=date(2026, 10, 2)), research()])
    response = client.get('/api/companies/AAPL/insiders')
    assert response.status_code == 200
    data = response.json()
    first = data['transactions'][0]
    assert first['filing_date'] == '2026-10-01' and first['transaction_date'] == '2026-09-29'
    assert first['shares'] == 5 and first['price'] == 2.5 and first['transaction_value'] == 12.5
    assert first['insider_name'] is None and first['insider_role'] is None and first['aff10b5one'] is None
    assert set(first) == set(TransactionResponse.model_fields)
    assert data['transactions'][1]['is_amendment']
    assert len(data['research_events']) == 1
    assert data['research_events'][0]['unique_buyer_count'] is None
    assert data['research_events'][0]['information_date'] == '2026-10-01'
    InsidersResponse.model_validate(data)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ResearchEvent)) == 1
        assert session.get(InsiderTransaction, 'amendment').is_p0_qualifying is True


def test_timestamp_serialization_and_literal_validation():
    row = transaction(accepted_at=datetime(2026, 10, 1, 20, tzinfo=timezone.utc))
    model = TransactionResponse.model_validate(row)
    assert model.model_dump(mode='json')['accepted_at'] == '2026-10-01T20:00:00Z'
    row.source_type = 'unsupported'
    with pytest.raises(ValidationError):
        TransactionResponse.model_validate(row)


@pytest.mark.parametrize('path', ['/api/radar', '/api/companies/AAPL',
                                  '/api/companies/AAPL/prices', '/api/companies/AAPL/insiders'])
def test_database_failures_are_sanitized(setup, path):
    client, _, app = setup
    broken = Mock()
    broken.execute.side_effect = SQLAlchemyError('synthetic-private-database-url')
    broken.scalars.side_effect = SQLAlchemyError('synthetic-private-database-url')
    broken.get.side_effect = SQLAlchemyError('synthetic-private-database-url')
    app.dependency_overrides[get_session] = lambda: broken
    response = client.get(path)
    assert response.status_code == 503
    assert response.json() == {'detail': 'Research data unavailable'}
    assert 'synthetic-private' not in response.text


def test_health_without_configuration_and_lazy_database_error(monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.delenv('CORS_ORIGINS', raising=False)
    with TestClient(create_app()) as client:
        assert client.get('/health').status_code == 200
        assert client.get('/api/companies/UNKNOWN').status_code == 404
        response = client.get('/api/radar')
        assert response.status_code == 503 and response.json() == {'detail': 'Research data unavailable'}


def test_cors_default_and_disallowed_origin(setup):
    client, _, _ = setup
    allowed = client.get('/health', headers={'Origin': 'http://localhost:5173'})
    assert allowed.headers['access-control-allow-origin'] == 'http://localhost:5173'
    denied = client.get('/health', headers={'Origin': 'https://unlisted.invalid'})
    assert 'access-control-allow-origin' not in denied.headers
    preflight = client.options('/api/radar', headers={'Origin': 'http://localhost:5173',
                                                    'Access-Control-Request-Method': 'GET'})
    assert preflight.status_code == 200


def test_cors_production_origin_configuration(monkeypatch):
    monkeypatch.setenv('CORS_ORIGINS', 'https://frontend.example.test')
    with TestClient(create_app()) as client:
        assert client.get('/health', headers={'Origin': 'https://frontend.example.test'}).headers[
            'access-control-allow-origin'] == 'https://frontend.example.test'
        assert 'access-control-allow-origin' not in client.get('/health', headers={
            'Origin': 'http://localhost:5173'}).headers
    monkeypatch.setenv('CORS_ORIGINS', '')
    with TestClient(create_app()) as client:
        assert 'access-control-allow-origin' not in client.get('/health', headers={
            'Origin': 'http://localhost:5173'}).headers


@pytest.mark.parametrize('origin', ['*', 'https://*.example.test', 'https://user:private@example.test',
                                    'https://example.test/path', 'not-a-url'])
def test_cors_rejects_unsafe_configuration(monkeypatch, origin):
    monkeypatch.setenv('CORS_ORIGINS', origin)
    with pytest.raises(ValueError, match='^CORS_ORIGINS must contain explicit HTTP'):
        create_app()


def test_database_pool_reused_and_closed(monkeypatch, setup):
    _, engine, _ = setup
    class LocalDatabase:
        closed = False
        @contextmanager
        def session(self):
            with Session(engine) as session:
                yield session
        def close(self):
            self.closed = True
    database = LocalDatabase()
    factory = Mock(return_value=database)
    monkeypatch.setattr('app.api.dependencies.Database', factory)
    with TestClient(create_app()) as client:
        assert client.get('/api/radar').status_code == 200
        assert client.get('/api/companies/AAPL').status_code == 200
        factory.assert_called_once()
        assert not database.closed
    assert database.closed


@pytest.mark.parametrize('model', [RadarItem, RadarResponse, CompanyResponse, PricePoint,
                                   PricesResponse, TransactionResponse, ResearchEventSummary, InsidersResponse])
def test_response_fields_nullability_and_enums_match_authoritative_contract(model):
    contract = (Path(__file__).resolve().parents[2] / 'docs/API_CONTRACT.md').read_text(encoding='utf-8')
    block = re.search(r'type ' + model.__name__ + r' = \{(.*?)\n\}', contract, re.S).group(1)
    declarations = dict(re.findall(r'^\s*(\w+): (.+)$', block, re.M))
    schema = model.model_json_schema()
    assert set(schema['properties']) == set(declarations) == set(schema['required'])
    for name, declaration in declarations.items():
        prop = schema['properties'][name]
        variants = prop.get('anyOf', [prop])
        assert any(value.get('type') == 'null' for value in variants) == ('null' in declaration)
        literals = re.findall(r'"([^"]+)"', declaration)
        if literals:
            assert prop['enum'] == literals


def test_invalid_persisted_signal_status_is_sanitized(setup):
    client, _, app = setup
    # Simulate an invalid service record without bypassing database constraints.
    row = research()
    signal = Signal(signal_id='invalid-status', research_event_id=row.research_event_id,
                    ticker='AAPL', public_event_day=row.public_event_day,
                    score_status='unexpected-status', unavailable_components=[])
    session = Mock()
    session.execute.return_value.all.return_value = [(row, signal, Company(ticker='AAPL', company_name='Synthetic Apple'))]
    app.dependency_overrides[get_session] = lambda: session
    response = client.get('/api/radar', headers={'Origin': 'http://localhost:5173'})
    assert response.status_code == 503
    assert response.json() == {'detail': 'Research data unavailable'}
    assert response.headers['access-control-allow-origin'] == 'http://localhost:5173'
