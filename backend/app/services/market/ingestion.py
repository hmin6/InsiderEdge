from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.services.universe import normalize_ticker
from .normalize import normalize_prices
from .provider import ProviderError, provider_symbol
from .repository import persist_prices

SECTOR_ETFS = ('XLK', 'XLF', 'XLV', 'XLE', 'XLI', 'XLY', 'XLP', 'XLU', 'XLB', 'XLRE', 'XLC')


def required_symbols(universe) -> tuple[str, ...]:
    return tuple(sorted({company.ticker for company in universe.companies} | {'SPY'} | set(SECTOR_ETFS)))


def ingest_prices(provider, database, universe, start: date, end: date,
                  tickers=None, validate_only=False, on_progress=None, today=None):
    today = today or datetime.now(ZoneInfo('America/New_York')).date()
    if not date(2019, 1, 1) <= start < end <= today:
        raise ValueError('Require 2019-01-01 <= start < end <= today; end is exclusive')
    allowed = required_symbols(universe)
    symbols = sorted({normalize_ticker(ticker) for ticker in tickers}) if tickers else list(allowed)
    if set(symbols) - set(allowed):
        raise ValueError('Requested ticker is not in the frozen universe or benchmark set')
    if database is None and not validate_only:
        raise ValueError('Database is required for persistence')
    summary = {'start': start.isoformat(), 'end_exclusive': end.isoformat(),
               'validate_only': validate_only, 'target_count': len(symbols),
               'analysis_price_convention': 'Adj Close; NULL when unavailable; no raw Close fallback',
               'normalized_rows': 0, 'written_rows': 0, 'failures': 0, 'symbols': []}
    for ticker in symbols:
        result = {'ticker': ticker, 'provider_symbol': provider_symbol(ticker),
                  'status': 'ok', 'normalized_rows': 0, 'written_rows': 0, 'issues': []}
        try:
            frame = provider.fetch(ticker, start, end)
            batch = normalize_prices(frame, ticker, start, end)
            result.update(normalized_rows=len(batch.rows), issues=batch.issues,
                          duplicate_input_rows=batch.duplicates)
            if not batch.rows:
                result['status'] = 'no_valid_data'
            else:
                result['first_date'], result['last_date'] = batch.rows[0]['date'].isoformat(), batch.rows[-1]['date'].isoformat()
                if not validate_only:
                    with database.session() as session:
                        result['written_rows'] = persist_prices(session, batch.rows)
                if batch.issues:
                    result['status'] = 'partial'
        except ProviderError as error:
            result['status'] = error.reason
            result['attempts'] = error.attempts
        except ValueError:
            result['status'] = 'invalid_provider_data'
        except Exception:
            # Neither database URLs nor raw driver/provider exceptions enter reports.
            result['status'] = 'ingestion_failure'
        if result['status'] not in {'ok', 'partial'}:
            summary['failures'] += 1
        summary['normalized_rows'] += result['normalized_rows']
        summary['written_rows'] += result['written_rows']
        summary['symbols'].append(result)
        if on_progress:
            on_progress(summary)
    return summary
