"""Run from backend: python -m scripts.ingest_prices --help."""
import argparse
from datetime import date, datetime
from importlib.metadata import version
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from app.db.session import Database
from app.services.universe import Universe
from app.services.market.ingestion import ingest_prices
from app.services.market.provider import YFinanceProvider


def main():
    load_dotenv(Path(__file__).resolve().parents[2] / '.env', override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', type=date.fromisoformat, default=date(2019, 1, 1))
    parser.add_argument('--end', type=date.fromisoformat, default=datetime.now(ZoneInfo('America/New_York')).date(),
                        help='Exclusive end date; defaults to today to exclude incomplete current-day bars')
    parser.add_argument('--ticker', action='append', help='Optional subset; repeat for multiple project symbols')
    parser.add_argument('--validate-only', action='store_true', help='Download/normalize without database writes')
    parser.add_argument('--report', type=Path, default=Path('../data/market_ingestion_report.json'))
    args = parser.parse_args()
    database = None
    try:
        universe = Universe.from_csv()
        if not args.validate_only:
            database = Database()
        def checkpoint(summary):
            summary['yfinance_version'] = version('yfinance')
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(summary, indent=2), encoding='utf-8')
        result = ingest_prices(YFinanceProvider(), database, universe, args.start, args.end,
                               args.ticker, args.validate_only, checkpoint)
        print(json.dumps({key: value for key, value in result.items() if key != 'symbols'}, indent=2))
        for symbol in result['symbols']:
            print(f'{symbol["ticker"]}: {symbol["status"]}; {symbol["written_rows"]} rows written; {len(symbol["issues"])} diagnostics')
        if result['failures']:
            raise SystemExit(1)
    except Exception:
        raise SystemExit('Market ingestion failed; check dates, project symbols, configuration, and connectivity.') from None
    finally:
        if database is not None:
            database.close()


if __name__ == '__main__':
    main()
