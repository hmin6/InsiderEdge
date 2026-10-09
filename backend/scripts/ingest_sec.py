"""SEC downloader/import CLI. Run from backend: python -m scripts.ingest_sec --help."""
import argparse
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from sqlalchemy import select

from app.db.models import Company
from app.db.session import Database
from app.services.sec.bulk import parse_bulk
from app.services.sec.client import BULK_PAGE, Quarter, SecClient, SecRequestError, discover_quarters, recent_filings
from app.services.sec.edgar import parse_edgar
from app.services.sec.normalize import InvalidRow, cik
from app.services.sec.repository import persist


def run(args, client=None, database=None):
    summary = {'bulk_quarters_used': [], 'sources': [], 'issues': [],
               'normalized': 0, 'inserted': 0, 'duplicates': 0, 'unmapped': 0,
               'excluded_before_2020': 0}
    args.cache.mkdir(parents=True, exist_ok=True)
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    if start < date(2020, 1, 1) or end < start:
        raise ValueError('Require 2020-01-01 <= start <= end')
    quarters = []
    if args.bulk_file:
        if args.mode != 'bulk':
            raise ValueError('--bulk-file is supported only with --mode bulk')
        for path in args.bulk_file:
            match = re.fullmatch(r'(\d{4})q([1-4])_form345\.zip', path.name, re.I)
            if not match or int(match[1]) < 2020:
                raise ValueError('Local archives must use official YYYYqN_form345.zip filenames (2020+)')
            quarters.append(Quarter(int(match[1]), int(match[2]), str(path)))
        quarters.sort()
    else:
        client = client or SecClient(os.environ.get('SEC_USER_AGENT', ''))
        quarters = discover_quarters(client.get(BULK_PAGE).decode('utf-8'))
    newest = max(quarters)
    summary['newest_bulk_quarter_detected'] = newest.label
    if args.mode == 'discover':
        summary['available_bulk_quarters'] = [quarter.label for quarter in quarters]
        return summary
    if database is None:
        raise ValueError('Database required for import')

    def save(report, source):
        # Each source is atomic; failed sources can be retried without duplicates.
        report.records[:] = [row for row in report.records if start <= row['filing_date'] <= end]
        with database.session() as session:
            counts = persist(session, report)
        summary['normalized'] += len(report.records)
        summary['excluded_before_2020'] += report.excluded_before_2020
        summary['issues'].extend(report.issues)
        for key, value in counts.items():
            summary[key] += value
        summary['sources'].append(source)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(summary, indent=2), encoding='utf-8')

    if args.mode in {'bulk', 'all'}:
        for quarter in quarters:
            if quarter.end < start or date(quarter.year, 3 * quarter.quarter - 2, 1) > end:
                continue
            if args.bulk_file:
                data = Path(quarter.url).read_bytes()
            else:
                path = args.cache / f'{quarter.year}q{quarter.quarter}_form345.zip'
                if not path.exists():
                    data = client.get(quarter.url)
                    # Validate before caching; interrupted requests never create files.
                    import zipfile
                    import io
                    if not zipfile.is_zipfile(io.BytesIO(data)):
                        raise InvalidRow('SEC quarterly download is not a ZIP archive')
                    path.write_bytes(data)
                data = path.read_bytes()
            parsed = parse_bulk(data)
            summary['bulk_quarters_used'].append(quarter.label)
            save(parsed, {'type': 'bulk', 'quarter': quarter.label, 'location': quarter.url})
    if args.mode in {'edgar', 'all'}:
        gap_start = max(start, newest.end + timedelta(days=1))
        # Include a boundary overlap for quarter cutoffs and late dissemination.
        retrieval_start = max(start, newest.end - timedelta(days=6))
        summary['edgar_gap_range'] = {'start': gap_start.isoformat(), 'end': end.isoformat()}
        summary['edgar_retrieval_range'] = {'start': retrieval_start.isoformat(), 'end': end.isoformat()}
        with database.session() as session:
            ciks = args.cik or list(session.scalars(select(Company.cik).where(Company.cik.is_not(None))))
        if not ciks:
            raise ValueError('Supply --cik or populate existing companies with issuer CIKs first')
        seen = set()
        if retrieval_start <= end:
            for issuer in sorted({cik(value) for value in ciks}):
                for metadata in recent_filings(client, issuer, retrieval_start, end):
                    if metadata['accession_number'] in seen:
                        continue
                    seen.add(metadata['accession_number'])
                    path = args.cache / f'{metadata["accession_number"]}.xml'
                    data = path.read_bytes() if path.exists() else client.get(metadata['url'])
                    report = parse_edgar(data, metadata)
                    path.write_bytes(data)
                    save(report, {'type': 'edgar', **metadata})
    return summary


def main():
    load_dotenv(Path(__file__).resolve().parents[2] / '.env', override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['discover', 'bulk', 'edgar', 'all'], default='discover')
    parser.add_argument('--bulk-file', type=Path, action='append', default=[])
    parser.add_argument('--cik', action='append', default=[])
    parser.add_argument('--start', default='2020-01-01')
    parser.add_argument('--end', default=datetime.now(ZoneInfo('America/New_York')).date().isoformat())
    parser.add_argument('--cache', type=Path, default=Path('../data/sec_cache'))
    parser.add_argument('--report', type=Path, default=Path('../data/sec_ingestion_report.json'))
    args = parser.parse_args()
    database = None
    try:
        if args.mode != 'discover':
            database = Database()
        result = run(args, database=database)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps({key: value for key, value in result.items() if key not in {'issues', 'sources'}}, indent=2))
        print(f'Diagnostics: {len(result["issues"])}; inspect the report file.')
    except (InvalidRow, SecRequestError) as error:
        raise SystemExit(f'SEC ingestion failed: {error}. Completed sources may be rerun safely.') from None
    except Exception:
        # Driver/environment errors may contain secrets. Do not print raw errors.
        raise SystemExit('SEC ingestion failed; check configuration, source format, and connectivity. Completed sources may be rerun safely.') from None
    finally:
        if database is not None:
            database.close()


if __name__ == '__main__':
    main()
