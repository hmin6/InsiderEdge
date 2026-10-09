from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql

from app.main import app
from app.db.models import Base, Company, Price, ResearchEvent, Signal, InsiderTransaction
from app.db.session import Database


def test_health_without_database(monkeypatch, caplog):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    with TestClient(app) as client:
        response = client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def test_database_environment_and_secret_handling(monkeypatch, caplog):
    secret = 'synthetic-test-password'
    monkeypatch.setenv('DATABASE_URL', f'postgresql://tester:{secret}@localhost/test')
    database = Database()
    try:
        assert database.engine.url.password == secret
        assert database.engine.url.drivername == 'postgresql+psycopg'
        assert database.engine.hide_parameters
        assert not database.engine.echo
        assert secret not in repr(database)
        assert secret not in repr(database.engine)
        with TestClient(app) as client:
            response = client.get('/health')
        assert secret not in response.text
        assert secret not in caplog.text
    finally:
        database.close()


@pytest.mark.parametrize('url', [None, '', 'invalid-secret-value', 'sqlite:///secret.db'])
def test_bad_configuration_is_sanitized(monkeypatch, url):
    if url is None:
        monkeypatch.delenv('DATABASE_URL', raising=False)
    else:
        monkeypatch.setenv('DATABASE_URL', url)
    with pytest.raises(ValueError, match='^DATABASE_URL must be a valid PostgreSQL URL$'):
        Database()


@pytest.fixture
def engine():
    engine = create_engine('sqlite://', hide_parameters=True)
    @event.listens_for(engine, 'connect')
    def enable_foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def test_repeatable_schema_and_postgresql_compilation(engine):
    Base.metadata.create_all(engine)
    assert set(inspect(engine).get_table_names()) == {
        'companies', 'insider_transactions', 'research_events', 'prices', 'fundamentals', 'signals'
    }
    for table in Base.metadata.sorted_tables:
        assert str(CreateTable(table).compile(dialect=postgresql.dialect()))
    assert Base.metadata.tables['insider_transactions'].c.accepted_at.type.timezone


def test_price_primary_key_and_non_company_symbols(engine):
    with Session(engine) as session:
        session.add(Price(ticker='SPY', date=date(2026, 1, 2)))
        session.commit()
        session.add(Price(ticker='SPY', date=date(2026, 1, 2)))
        with pytest.raises(IntegrityError):
            session.commit()


def test_signal_requires_research_event(engine):
    with Session(engine) as session:
        session.add(Company(ticker='TEST', company_name='Synthetic test fixture'))
        session.commit()
        session.add(Signal(signal_id='test', research_event_id='missing', ticker='TEST',
                           public_event_day=date(2026, 1, 2), score_status='insufficient_data',
                           unavailable_components=['A', 'C', 'M', 'S', 'D']))
        with pytest.raises(IntegrityError):
            session.commit()


def test_session_commit_and_rollback(engine):
    # Exercise the production unit-of-work wrapper against an isolated database.
    from sqlalchemy.orm import sessionmaker
    database = Database.__new__(Database)
    database.engine = engine
    database.sessions = sessionmaker(bind=engine)
    with database.session() as session:
        session.add(Company(ticker='TEST', company_name='Synthetic test fixture'))
    with pytest.raises(RuntimeError):
        with database.session() as session:
            session.add(Company(ticker='ROLLBACK', company_name='Synthetic test fixture'))
            session.flush()
            raise RuntimeError('test rollback')
    with database.session() as session:
        assert session.get(Company, 'TEST') is not None
        assert session.get(Company, 'ROLLBACK') is None


def test_event_company_day_is_unique(engine):
    with Session(engine) as session:
        session.add(Company(ticker='TEST', company_name='Synthetic test fixture'))
        session.commit()
        for identifier in ['first', 'second']:
            session.add(ResearchEvent(
                research_event_id=identifier, ticker='TEST', public_event_day=date(2026, 1, 2),
                information_date=date(2026, 1, 1), source_transaction_count=1,
                source_filing_count=1, unique_buyer_count=1, role_bucket='Other',
                has_executive=False, has_director=False, has_other=True))
        with pytest.raises(IntegrityError):
            session.commit()


def test_raw_transaction_deduplication(engine):
    with Session(engine) as session:
        for identifier in ['bulk-record', 'edgar-record']:
            session.add(InsiderTransaction(
                transaction_id=identifier, canonical_transaction_key='same-source-row',
                accession_number='synthetic-accession', source_type='bulk',
                transaction_date=date(2026, 1, 1), filing_date=date(2026, 1, 2),
                transaction_code='P', acquired_or_disposed='A', derivative_flag=False,
                is_amendment=False, is_p0_qualifying=True))
        with pytest.raises(IntegrityError):
            session.commit()


def test_initialization_errors_do_not_disclose_credentials(monkeypatch, capsys):
    from scripts import init_db
    def fail():
        raise RuntimeError('synthetic-password-in-driver-error')
    monkeypatch.setattr(init_db, 'Database', fail)
    with pytest.raises(SystemExit) as caught:
        init_db.main()
    assert str(caught.value) == 'Database initialization failed; verify configuration and connectivity.'
    assert 'synthetic-password' not in capsys.readouterr().out
