from datetime import date
import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, inspect, select, UniqueConstraint
from sqlalchemy.orm import Session

from app.db.models import Base, Company, InsiderTransaction
from app.services.universe import (
    AmbiguousCIKError, CompanyMetadata, Universe, normalize_cik, normalize_ticker,
)
from app.services.sec.normalize import Report
from app.services.sec.repository import persist
from scripts.freeze_universe import freeze


@pytest.fixture
def universe():
    return Universe.from_csv()


def test_frozen_snapshot_integrity(universe):
    config = Path(__file__).resolve().parents[2] / 'config'
    manifest = json.loads((config / 'universe.provenance.json').read_text())
    assert hashlib.sha256((config / 'universe.csv').read_bytes()).hexdigest() == manifest['universe_sha256']
    assert len(universe.companies) == manifest['security_count'] == 101
    assert len({company.cik for company in universe.companies}) == manifest['issuer_count'] == 100
    assert all(company.cik and len(company.cik) == 10 for company in universe.companies)
    assert all(company.company_name and company.sector for company in universe.companies)
    assert manifest['unmapped_tickers'] == []


def test_known_and_unknown_lookups(universe):
    assert universe.ticker_to_cik(' aapl ') == '0000320193'
    assert universe.cik_to_ticker(320193) == 'AAPL'
    assert universe.cik_to_ticker('0000320193') == 'AAPL'
    assert universe.ticker_to_company('GOOG').ticker == 'GOOG'
    assert universe.ticker_to_company('GOOGL').ticker == 'GOOGL'
    assert universe.ticker_to_company('GOOG') != universe.ticker_to_company('GOOGL')
    assert universe.ticker_to_cik('UNKNOWN') is None
    assert universe.ticker_to_company('UNKNOWN') is None
    assert universe.cik_to_ticker('9999999999') is None
    assert universe.cik_to_tickers('invalid') == ()


def test_share_class_ambiguity(universe):
    assert universe.ticker_to_cik('GOOG') == universe.ticker_to_cik('GOOGL') == '0001652044'
    assert universe.cik_to_tickers(1652044) == ('GOOG', 'GOOGL')
    with pytest.raises(AmbiguousCIKError) as error:
        universe.cik_to_ticker(1652044)
    assert error.value.tickers == ('GOOG', 'GOOGL')
    result = universe.resolve_issuer(1652044)
    assert result.status == 'ambiguous' and result.ticker is None
    assert result.tickers == ('GOOG', 'GOOGL')
    assert universe.resolve_issuer(1652044, 'GOOGL').ticker == 'GOOGL'
    assert universe.resolve_issuer(1652044, 'GOOG').ticker == 'GOOG'


@pytest.mark.parametrize('ticker', ['BRK.B', 'brk-b', ' BRK B '])
def test_special_ticker_convention(universe, ticker):
    assert normalize_ticker(ticker) == 'BRK.B'
    assert universe.ticker_to_cik(ticker) == '0001067983'
    assert universe.ticker_to_company(ticker).ticker == 'BRK.B'


def test_no_generic_class_collapse():
    assert normalize_ticker('GOOG') != normalize_ticker('GOOGL')
    assert normalize_ticker('TEST-A') != normalize_ticker('TEST.A')


def test_unmapped_and_conflicting_issuer(universe):
    assert universe.resolve_issuer('9999999999').status == 'unmapped'
    assert universe.resolve_issuer(None).status == 'unmapped'
    assert universe.resolve_issuer('bad-cik').status == 'invalid'
    conflict = universe.resolve_issuer(1652044, 'AAPL')
    assert conflict.status == 'conflict' and conflict.ticker is None
    assert universe.resolve_issuer(1652044, 'UNKNOWN').status == 'ambiguous'


def test_missing_cik_is_explicit():
    universe = Universe([CompanyMetadata('TEST', None, 'Synthetic fixture')])
    assert universe.ticker_to_company('TEST').cik is None
    assert universe.ticker_to_cik('TEST') is None
    assert universe.cik_to_tickers(None) == ()
    assert universe.resolve_issuer(None, 'TEST').ticker == 'TEST'


@pytest.mark.parametrize('value', [320193, '320193', '0000320193', ' 320193 '])
def test_cik_normalization(value):
    assert normalize_cik(value) == '0000320193'


@pytest.mark.parametrize('value', [True, 320193.0, '123.0', '0', '-1', '12345678901'])
def test_invalid_cik_not_guessed(value):
    with pytest.raises(ValueError):
        normalize_cik(value)


def test_duplicate_canonical_ticker_rejected():
    with pytest.raises(ValueError, match='Duplicate'):
        Universe([CompanyMetadata('BRK.B', '1067983', 'Fixture'),
                  CompanyMetadata('BRK-B', '1067983', 'Fixture')])


@pytest.fixture
def engine():
    engine = create_engine('sqlite://')
    @event.listens_for(engine, 'connect')
    def enable_fk(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add_all([Company(ticker='GOOG', cik='0001652044', company_name='Alphabet Class C'),
                         Company(ticker='GOOGL', cik='0001652044', company_name='Alphabet Class A'),
                         Company(ticker='AAPL', cik='0000320193', company_name='Apple')])
    yield engine
    engine.dispose()


def test_database_allows_shared_cik_but_retains_index(engine):
    with Session(engine) as session:
        assert len(session.scalars(select(Company).where(Company.cik == '0001652044')).all()) == 2
    assert not any(constraint['column_names'] == ['cik'] for constraint in inspect(engine).get_unique_constraints('companies'))
    assert any(index['column_names'] == ['cik'] and not index['unique'] for index in inspect(engine).get_indexes('companies'))
    assert list(Company.__table__.primary_key.columns.keys()) == ['ticker']


@pytest.mark.parametrize('ticker,expected,status', [
    (None, None, 'ambiguous'), ('UNKNOWN', None, 'ambiguous'),
    ('GOOG', 'GOOG', None), ('GOOGL', 'GOOGL', None), ('AAPL', None, 'conflict'),
])
def test_sec_persistence_never_guesses_share_class(engine, ticker, expected, status):
    report = Report(records=[{
        'transaction_id': 'synthetic', 'canonical_transaction_key': 'synthetic',
        'accession_number': '0001652044-26-000001', 'source_type': 'edgar',
        'ticker': ticker, 'cik': '0001652044', 'transaction_date': date(2026, 10, 1),
        'filing_date': date(2026, 10, 2), 'transaction_code': 'P',
        'acquired_or_disposed': 'A', 'derivative_flag': False, 'is_amendment': False,
        'is_p0_qualifying': True,
    }])
    with Session(engine) as session, session.begin():
        counts = persist(session, report)
        assert session.scalar(select(InsiderTransaction)).ticker == expected
        assert counts['unmapped'] == (1 if expected is None else 0)
    if status:
        assert any(status in issue['reason'] for issue in report.issues)


def test_freezer_refuses_missing_identifiers_and_overwrite(tmp_path):
    holdings = b'Fund Holdings as of,"Oct 08, 2026"\nTicker,Name,Sector,Asset Class\nTEST,Synthetic fixture,Communication,Equity\nUSD,Cash,Cash,Cash\n'
    identifiers = b'{"0":{"ticker":"TEST","cik_str":123}}'
    with pytest.raises(ValueError, match='Missing or ambiguous'):
        freeze(holdings, b'{}', tmp_path, date(2026, 10, 9))
    manifest = freeze(holdings, identifiers, tmp_path, date(2026, 10, 9))
    assert manifest['security_count'] == 1
    universe = Universe.from_csv(tmp_path / 'universe.csv')
    assert universe.ticker_to_company('TEST').sector == 'Communication Services'
    with pytest.raises(FileExistsError):
        freeze(holdings, identifiers, tmp_path, date(2026, 10, 9))


def test_migration_targets_only_cik_uniqueness_and_is_repeatable(monkeypatch):
    from sqlalchemy import Column, Index, MetaData, Table, Text
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import DropConstraint, DropIndex
    from scripts import migrate_company_cik
    table = Table('companies', MetaData(), Column('ticker', Text, primary_key=True),
                  Column('cik', Text), Column('other', Text),
                  UniqueConstraint('cik', name='uq_companies_cik'),
                  UniqueConstraint('other', name='keep_other_unique'))
    Index('legacy_cik_unique', table.c.cik, unique=True)
    state = {'constraints': set(table.constraints), 'indexes': set(table.indexes)}
    operations = []
    class Connection:
        dialect = postgresql.dialect()
        def execute(self, statement):
            operations.append(str(statement.compile(dialect=self.dialect)))
            if isinstance(statement, DropConstraint):
                state['constraints'].remove(statement.element)
            elif isinstance(statement, DropIndex):
                state['indexes'].remove(statement.element)
    def reflect(*args, **kwargs):
        table.constraints = set(state['constraints'])
        table.indexes = set(state['indexes'])
        return table
    def create_index(index, connection, checkfirst):
        assert checkfirst
        if not any(existing.name == index.name for existing in state['indexes']):
            state['indexes'].add(index)
            operations.append(f'CREATE INDEX {index.name}')
    monkeypatch.setattr(migrate_company_cik, 'Table', reflect)
    monkeypatch.setattr(Index, 'create', create_index)
    connection = Connection()
    migrate_company_cik.migrate(connection)
    first = operations.copy()
    migrate_company_cik.migrate(connection)
    assert operations == first
    assert len(operations) == 3
    assert 'DROP CONSTRAINT uq_companies_cik' in operations[0]
    assert 'DROP INDEX IF EXISTS legacy_cik_unique' in operations[1]
    assert operations[2] == 'CREATE INDEX ix_companies_cik'
    assert any(constraint.name == 'keep_other_unique' for constraint in state['constraints'])
    assert table.primary_key in state['constraints']
