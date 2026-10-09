"""Build a new offline snapshot from downloaded source files; never overwrite one."""
import argparse
import csv
from datetime import date, datetime
import hashlib
import io
import json
from pathlib import Path

from app.services.universe import normalize_cik, normalize_ticker

HOLDINGS_URL = 'https://www.ishares.com/us/products/239723/ishares-s-p-100-etf/latest-holdings.csv'
IDENTIFIERS_URL = 'https://www.sec.gov/files/company_tickers.json'


def freeze(holdings: bytes, identifiers: bytes, output: Path, freeze_date: date):
    if (output / 'universe.csv').exists() or (output / 'universe.provenance.json').exists():
        raise FileExistsError('Frozen universe already exists; refuse to refresh it')
    lines = holdings.decode('utf-8-sig').splitlines()
    metadata_line = next(line for line in lines if line.startswith('Fund Holdings as of,'))
    holdings_date = datetime.strptime(next(csv.reader([metadata_line]))[1], '%b %d, %Y').date()
    if holdings_date > freeze_date:
        raise ValueError('Holdings date is later than freeze date')
    start = next(index for index, line in enumerate(lines) if line.startswith('Ticker,Name,'))
    rows = [row for row in csv.DictReader(lines[start:]) if row.get('Asset Class') == 'Equity']
    lookup = {}
    for entry in json.loads(identifiers).values():
        try:
            ticker = normalize_ticker(entry['ticker'])
        except ValueError:
            continue  # Non-equity/unsupported SEC symbols cannot match our equity rows.
        lookup.setdefault(ticker, set()).add(normalize_cik(entry['cik_str']))
    normalized = []
    for row in rows:
        ticker = normalize_ticker(row['Ticker'])
        ciks = lookup.get(ticker, set())
        if len(ciks) != 1 or None in ciks:
            raise ValueError(f'Missing or ambiguous SEC mapping for {ticker}')
        normalized.append({'ticker': ticker, 'cik': next(iter(ciks)),
                           'company_name': row['Name'], 'sector': 'Communication Services'
                           if row['Sector'] == 'Communication' else row['Sector']})
    if not normalized or len({row['ticker'] for row in normalized}) != len(normalized):
        raise ValueError('Empty holdings or duplicate canonical tickers')
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, ['ticker', 'cik', 'company_name', 'sector'], lineterminator='\n')
    writer.writeheader()
    writer.writerows(sorted(normalized, key=lambda row: row['ticker']))
    data = stream.getvalue().encode('utf-8')
    manifest = {
        'freeze_date': freeze_date.isoformat(), 'holdings_as_of': holdings_date.isoformat(),
        'security_count': len(normalized), 'issuer_count': len({row['cik'] for row in normalized}),
        'membership_source': HOLDINGS_URL, 'identifiers_source': IDENTIFIERS_URL,
        'holdings_sha256': hashlib.sha256(holdings).hexdigest(),
        'sec_identifiers_sha256': hashlib.sha256(identifiers).hexdigest(),
        'universe_sha256': hashlib.sha256(data).hexdigest(),
        'transformations': ['Equity holdings only; non-equities excluded',
                            'BRK B and BRK-B canonicalized to BRK.B',
                            'Communication sector canonicalized to Communication Services',
                            'Exact canonical-ticker SEC match; ten-digit issuer CIK',
                            'OEF security names retained, including distinct share classes'],
        'unmapped_tickers': [],
    }
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'universe.csv').open('xb') as target:
        target.write(data)
    with (output / 'universe.provenance.json').open('x', encoding='utf-8') as target:
        target.write(json.dumps(manifest, indent=2) + '\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--holdings', required=True, type=Path)
    parser.add_argument('--sec-identifiers', required=True, type=Path)
    parser.add_argument('--output', type=Path, default=Path('../config'))
    parser.add_argument('--freeze-date', required=True, type=date.fromisoformat)
    args = parser.parse_args()
    manifest = freeze(args.holdings.read_bytes(), args.sec_identifiers.read_bytes(), args.output, args.freeze_date)
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
