"""Synthetic market observations; normal tests never contact Yahoo."""
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from unittest.mock import Mock

import pandas as pd
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.dialects import postgresql

from app.db.models import Base
from app.services.market.ingestion import ingest_prices, required_symbols, SECTOR_ETFS
from app.services.market.normalize import normalize_prices, session_date
from app.services.market.provider import YFinanceProvider, ProviderError, provider_symbol
from app.services.market.repository import persist_prices, read_prices
from app.services.universe import Universe

START, END = date(2024, 1, 1), date(2024, 1, 10)


def frame(days=('2024-01-03', '2024-01-02')):
    return pd.DataFrame({'Open': [100.] * len(days), 'High': [110.] * len(days),
                         'Low': [90.] * len(days), 'Close': [105.] * len(days),
                         'Adj Close': [95.] * len(days), 'Volume': [1000] * len(days)},
                        index=pd.to_datetime(list(days)))


@pytest.mark.parametrize('label,expected', [
    ('2024-01-02', date(2024, 1, 2)),
    ('2024-01-02T00:00:00-05:00', date(2024, 1, 2)),
    ('2024-01-02T05:00:00Z', date(2024, 1, 2)),
    ('2024-07-02T04:00:00Z', date(2024, 7, 2)),
])
def test_session_dates(label, expected):
    assert session_date(label) == expected


@pytest.mark.parametrize('label', [pd.NaT, 1, 'bad-date'])
def test_invalid_dates(label):
    with pytest.raises((ValueError, TypeError)):
        session_date(label)


@pytest.mark.parametrize('ticker', ['AAPL', 'SPY', *SECTOR_ETFS])
def test_sorting_and_consistent_adjustment(ticker):
    batch = normalize_prices(frame(), ticker, START, END)
    assert [row['date'] for row in batch.rows] == [date(2024, 1, 2), date(2024, 1, 3)]
    assert not batch.issues
    for row in batch.rows:
        assert row['ticker'] == ticker
        assert row['close'] == Decimal('105')
        assert row['analysis_price'] == row['adjusted_close'] == Decimal('95')


def test_duplicates_and_conflicts_are_not_arbitrarily_selected():
    data = frame(('2024-01-02',) * 3 + ('2024-01-03',) * 2)
    data.iloc[1, data.columns.get_loc('Close')] = 106
    batch = normalize_prices(data, 'AAPL', START, END)
    assert [row['date'] for row in batch.rows] == [date(2024, 1, 3)]
    assert batch.duplicates == 3
    assert any('conflicting duplicate' in issue['reason'] for issue in batch.issues)


def test_missing_adjustment_never_falls_back_to_raw_close():
    data = frame().drop(columns=['Adj Close', 'Volume'])
    batch = normalize_prices(data, 'SPY', START, END)
    assert len(batch.rows) == 2
    assert all(row['analysis_price'] is None and row['adjusted_close'] is None
               and row['volume'] is None and row['close'] == 105 for row in batch.rows)
    assert batch.issues


@pytest.mark.parametrize('column,value', [('Open', float('inf')), ('Close', -1),
                                         ('Volume', 1.5), ('Volume', -1),
                                         ('Volume', 2**63), ('Adj Close', float('nan'))])
def test_invalid_numbers_are_null(column, value):
    data = frame(('2024-01-02',)).astype(object)
    data.loc[data.index[0], column] = value
    row = normalize_prices(data, 'AAPL', START, END).rows[0]
    fields = {'Open': 'open', 'Close': 'close', 'Volume': 'volume', 'Adj Close': 'adjusted_close'}
    assert row[fields[column]] is None
    if column == 'Adj Close':
        assert row['analysis_price'] is None


def test_no_fabricated_history_and_exclusive_end():
    data = frame(('2023-12-31', '2024-01-02', '2024-01-10'))
    batch = normalize_prices(data, 'AAPL', START, END)
    assert [row['date'] for row in batch.rows] == [date(2024, 1, 2)]
    assert len(batch.issues) == 2
    assert not normalize_prices(frame().mul(float('nan')), 'AAPL', START, END).rows
    with pytest.raises(ValueError):
        normalize_prices(pd.DataFrame({'Unknown': [1]}), 'AAPL', START, END)


def test_provider_exact_configuration_and_symbol_identity():
    downloader = Mock(return_value=frame())
    provider = YFinanceProvider(downloader=downloader)
    provider.fetch('BRK.B', START, END)
    downloader.assert_called_once_with(
        tickers='BRK-B', start='2024-01-01', end='2024-01-10', interval='1d',
        auto_adjust=False, back_adjust=False, repair=False, actions=False,
        keepna=True, prepost=False, rounding=False, threads=False, progress=False,
        ignore_tz=False, multi_level_index=False, timeout=30)
    assert provider_symbol('GOOGL') == 'GOOGL'
    assert normalize_prices(frame(), 'BRK-B', START, END).rows[0]['ticker'] == 'BRK.B'


@pytest.mark.parametrize('response,reason', [(pd.DataFrame(), 'empty_data'),
                                           (RuntimeError('synthetic-secret'), 'failure')])
def test_bounded_retry_safe_failure(response, reason):
    downloader = Mock(side_effect=response) if isinstance(response, Exception) else Mock(return_value=response)
    sleeps = []
    provider = YFinanceProvider(downloader, sleeper=sleeps.append, clock=lambda: 0)
    with pytest.raises(ProviderError) as error:
        provider.fetch('AAPL', START, END)
    assert error.value.reason == reason
    assert error.value.attempts == downloader.call_count == 3
    assert 'synthetic-secret' not in str(error.value)
    assert sleeps == [1, 0.5, 2, 0.5]


def test_recovery_and_rate_limiting():
    downloader = Mock(side_effect=[pd.DataFrame(), frame(), frame()])
    sleeps = []
    provider = YFinanceProvider(downloader, sleeper=sleeps.append, clock=lambda: 0)
    provider.fetch('AAPL', START, END)
    provider.fetch('SPY', START, END)
    assert downloader.call_count == 3
    assert sleeps == [1, 0.5, 0.5]


@pytest.fixture
def database():
    engine = create_engine('sqlite://')
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    class LocalDatabase:
        @contextmanager
        def session(self):
            with Session(engine) as session, session.begin():
                yield session
    yield LocalDatabase()
    engine.dispose()


def test_idempotent_persistence_corrections_and_offline_query(database):
    rows = normalize_prices(frame(), 'SPY', START, END).rows
    for _ in range(2):
        with database.session() as session:
            assert persist_prices(session, rows) == 2
    with database.session() as session:
        assert len(read_prices(session, 'spy')) == 2
        revised = dict(rows[0], adjusted_close=None, analysis_price=None, close=Decimal('106'))
        persist_prices(session, [revised])
    with database.session() as session:
        result = read_prices(session, 'SPY', date(2024, 1, 2), date(2024, 1, 3))
        assert len(result) == 1
        assert result[0]['close'] == 106
        assert result[0]['analysis_price'] is None


def test_full_frozen_batch_and_isolated_provider_failure(database):
    universe = Universe.from_csv()
    assert len(universe.companies) == 101
    assert len(required_symbols(universe)) == 113
    provider = Mock()
    def fetch(ticker, *_):
        if ticker == 'AAPL':
            raise ProviderError('empty_data', 3)
        return frame()
    provider.fetch.side_effect = fetch
    report = ingest_prices(provider, database, universe, START, END, today=END)
    assert report['target_count'] == provider.fetch.call_count == 113
    assert report['failures'] == 1
    assert report['written_rows'] == 224
    with database.session() as session:
        assert not read_prices(session, 'AAPL')
        assert len(read_prices(session, 'SPY')) == 2


def test_validate_only_subset_and_reject_invalid_requests():
    provider = Mock()
    provider.fetch.return_value = frame()
    universe = Universe.from_csv()
    report = ingest_prices(provider, None, universe, START, END,
                           tickers=['BRK-B', 'BRK.B'], validate_only=True, today=END)
    assert report['target_count'] == 1 and report['written_rows'] == 0
    assert report['symbols'][0]['ticker'] == 'BRK.B'
    provider.fetch.reset_mock()
    for tickers, end in [(['UNKNOWN'], END), (['SPY'], date(2025, 1, 1))]:
        with pytest.raises(ValueError):
            ingest_prices(provider, None, universe, START, end,
                          tickers=tickers, validate_only=True, today=END)
    provider.fetch.assert_not_called()


def test_database_failure_is_sanitized_and_next_symbol_continues(database):
    provider = Mock()
    provider.fetch.return_value = frame()
    original_session = database.session
    database.session = Mock(side_effect=[RuntimeError('synthetic-secret'), original_session()])
    report = ingest_prices(provider, database, Universe.from_csv(), START, END,
                           tickers=['AAPL', 'SPY'], today=END)
    assert report['failures'] == 1 and report['written_rows'] == 2
    assert report['symbols'][0]['status'] == 'ingestion_failure'
    assert 'synthetic-secret' not in str(report)


def test_postgresql_upsert_is_parameterized_and_chunked():
    session = Mock()
    session.get_bind.return_value.dialect.name = 'postgresql'
    rows = normalize_prices(frame(('2024-01-02',)), 'SPY', START, END).rows
    assert persist_prices(session, rows * 101) == 101
    assert session.execute.call_count == 2
    statement = session.execute.call_args_list[0].args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert 'ON CONFLICT (ticker, date) DO UPDATE SET' in sql
    assert 'analysis_price = excluded.analysis_price' in sql
    assert 'SPY' not in sql
    assert compiled.params['ticker_m0'] == 'SPY'


def test_ambiguous_provider_columns_rejected():
    data = frame()
    data.columns = pd.MultiIndex.from_product([data.columns, ['AAPL']])
    with pytest.raises(ValueError, match='single-symbol'):
        normalize_prices(data, 'AAPL', START, END)
