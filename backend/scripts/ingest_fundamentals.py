"""Sequential SEC CompanyFacts ingestion; explicit --all required for the universe."""
import argparse
from datetime import date
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from app.db.session import Database
from app.services.companyfacts import CompanyFactsProvider, ingest
from app.services.sec.client import SecClient
from app.services.universe import Universe


def main():
    load_dotenv(Path(__file__).resolve().parents[2] / '.env', override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--ticker', action='append', help='Frozen-universe ticker; repeat for a subset')
    selection.add_argument('--all', action='store_true', help='Explicitly ingest the frozen universe')
    parser.add_argument('--through', type=date.fromisoformat, default=date.today(),
                        help='Inclusive filing-date cutoff; pre-2020 history retained for early events')
    parser.add_argument('--validate-only', action='store_true')
    parser.add_argument('--report', type=Path, default=Path('../data/fundamentals_report.json'))
    args = parser.parse_args()
    database = None
    try:
        if args.through > date.today():
            raise ValueError('Future cutoff')
        provider = CompanyFactsProvider(SecClient(os.environ.get('SEC_USER_AGENT', '')))
        database = None if args.validate_only else Database()
        report = ingest(provider, database, Universe.from_csv(), args.ticker, args.through, args.validate_only)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding='utf-8')
        for item in report:
            print(f'{item["ticker"]}: {item["status"]}; {item["rows"]} observations; {len(item["diagnostics"])} diagnostics')
        if any(item['status'] != 'ok' for item in report):
            raise SystemExit(1)
    except Exception:
        raise SystemExit('Fundamentals ingestion failed; check configuration, frozen tickers and connectivity.') from None
    finally:
        if database is not None:
            database.close()


if __name__ == '__main__':
    main()
