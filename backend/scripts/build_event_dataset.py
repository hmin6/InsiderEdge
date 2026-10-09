"""Build Issue #5 events offline from persisted SEC/market observations."""
import argparse
from datetime import date, datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from app.db.session import Database
from app.services.events.repository import build_from_database
from app.services.universe import Universe, normalize_ticker


def main():
    load_dotenv(Path(__file__).resolve().parents[2] / '.env', override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', type=date.fromisoformat, default=date(2020, 1, 1))
    parser.add_argument('--end', type=date.fromisoformat, default=datetime.now(ZoneInfo('America/New_York')).date())
    parser.add_argument('--ticker', action='append', help='Optional frozen-universe subset')
    parser.add_argument('--cache', type=Path, default=Path('../data/sec_cache'))
    parser.add_argument('--report', type=Path, default=Path('../data/event_dataset_report.json'))
    parser.add_argument('--dry-run', action='store_true', help='Read/build/report without writing database rows')
    args = parser.parse_args()
    database = None
    try:
        today = datetime.now(ZoneInfo('America/New_York')).date()
        if not date(2020, 1, 1) <= args.start <= args.end <= today:
            raise ValueError('Require 2020 <= start <= end <= today')
        universe = Universe.from_csv()
        tickers = sorted({normalize_ticker(ticker) for ticker in args.ticker}) if args.ticker else None
        if tickers and any(universe.ticker_to_company(ticker) is None for ticker in tickers):
            raise ValueError('Ticker outside frozen universe')
        database = Database()
        with database.session() as session:
            dataset, counts = build_from_database(session, universe, args.cache, args.start, args.end,
                                                   tickers, write=not args.dry_run)
        report = {'start': args.start.isoformat(), 'end_inclusive': args.end.isoformat(),
                  'dry_run': args.dry_run, 'events': dataset.events,
                  'joined_transaction_count': len(dataset.transactions),
                  'duplicate_input_count': dataset.duplicate_inputs,
                  'issues': dataset.issues, **counts}
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, default=str, indent=2), encoding='utf-8')
        print(json.dumps({key: value for key, value in report.items() if key not in {'events', 'issues'}}, indent=2))
        print(f'Events built: {len(dataset.events)}; diagnostics: {len(dataset.issues)}; inspect report.')
    except Exception:
        raise SystemExit('Event dataset build failed; verify configuration, nullable-buyer migration, source data, and downstream dependencies.') from None
    finally:
        if database is not None:
            database.close()


if __name__ == '__main__':
    main()
