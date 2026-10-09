"""Sequential, rate-limited SEC access. No API key is required."""
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from .normalize import InvalidRow, accession, cik, day

BULK_PAGE = 'https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets'


class SecRequestError(RuntimeError):
    pass


class SecClient:
    def __init__(self, user_agent: str, interval: float = 0.5, attempts: int = 3,
                 opener=urlopen, clock=time.monotonic, sleeper=time.sleep):
        if not user_agent or len(user_agent.strip()) < 10 or '\n' in user_agent or '\r' in user_agent:
            raise ValueError('Set SEC_USER_AGENT to a descriptive project name and contact')
        if interval < 0.5 or not 1 <= attempts <= 3:
            raise ValueError('SEC access requires interval >= 0.5 seconds and 1–3 attempts')
        self.user_agent, self.interval, self.attempts = user_agent, interval, attempts
        self.opener, self.clock, self.sleep = opener, clock, sleeper
        self.last_request = None

    def get(self, url: str) -> bytes:
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.hostname not in {'www.sec.gov', 'data.sec.gov'} or parsed.username or parsed.password:
            raise ValueError('Only official SEC HTTPS URLs are allowed')
        for attempt in range(self.attempts):
            if self.last_request is not None:
                self.sleep(max(0, self.interval - (self.clock() - self.last_request)))
            self.last_request = self.clock()
            request = Request(url, headers={'User-Agent': self.user_agent, 'Accept-Encoding': 'identity'})
            try:
                with self.opener(request, timeout=30) as response:
                    data = response.read(200 * 1024 * 1024 + 1)
                    if len(data) > 200 * 1024 * 1024:
                        raise SecRequestError('SEC response exceeds download limit')
                    return data
            except HTTPError as error:
                status = error.code
                if status not in {429, 500, 502, 503, 504} or attempt == self.attempts - 1:
                    raise SecRequestError(f'SEC request failed (HTTP {status})') from None
                try:
                    delay = float(error.headers.get('Retry-After', '0'))
                except (TypeError, ValueError):
                    delay = 0
                self.sleep(min(30, max(2 ** attempt, delay)))
            except (URLError, TimeoutError, OSError):
                if attempt == self.attempts - 1:
                    raise SecRequestError('SEC request failed (network/timeout)') from None
                self.sleep(2 ** attempt)
        raise SecRequestError('SEC retries exhausted')

    def json(self, url: str):
        try:
            return json.loads(self.get(url))
        except (ValueError, UnicodeError):
            raise SecRequestError('SEC returned invalid JSON') from None


@dataclass(frozen=True, order=True)
class Quarter:
    year: int
    quarter: int
    url: str

    @property
    def label(self):
        return f'{self.year}Q{self.quarter}'

    @property
    def end(self):
        from calendar import monthrange
        month = self.quarter * 3
        return date(self.year, month, monthrange(self.year, month)[1])


def discover_quarters(html: str) -> list[Quarter]:
    links = set()
    class Links(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag == 'a':
                href = dict(attrs).get('href')
                if href:
                    links.add(urljoin(BULK_PAGE, href))
    Links().feed(html)
    quarters = {}
    for url in links:
        match = re.search(r'/(\d{4})q([1-4])_form345\.zip$', url, re.I)
        if match and urlparse(url).hostname == 'www.sec.gov':
            year, quarter = map(int, match.groups())
            if year >= 2020:
                quarters[year, quarter] = Quarter(year, quarter, url)
    if not quarters:
        raise InvalidRow('SEC page has no recognized 2020+ quarterly downloads')
    return sorted(quarters.values())


def filing_rows(columns: dict):
    required = ('accessionNumber', 'filingDate', 'form', 'primaryDocument')
    if any(name not in columns for name in required):
        raise InvalidRow('SEC submissions missing required columns')
    length = len(columns['accessionNumber'])
    if any(len(values) != length for values in columns.values()):
        raise InvalidRow('SEC submissions columns have different lengths')
    for index in range(length):
        yield {name: values[index] for name, values in columns.items()}


def recent_filings(client: SecClient, issuer_cik: str, start: date, end: date):
    """Read recent and overlapping paginated submission metadata for a supplied CIK."""
    issuer_cik = cik(issuer_cik)
    root = client.json(f'https://data.sec.gov/submissions/CIK{issuer_cik}.json')
    blocks = [root['filings']['recent']]
    for history in root['filings'].get('files', []):
        if day(history['filingTo']) >= start and day(history['filingFrom']) <= end:
            name = history['name']
            if not re.fullmatch(r'CIK\d{10}-submissions-\d+\.json', name):
                raise InvalidRow('invalid submissions history filename')
            blocks.append(client.json(f'https://data.sec.gov/submissions/{name}'))
    seen = set()
    for columns in blocks:
        for row in filing_rows(columns):
            if row['form'] not in {'4', '4/A', '4-A'} or not start <= day(row['filingDate']) <= end:
                continue
            key = accession(row['accessionNumber'])
            if key in seen:
                continue
            seen.add(key)
            # primaryDocument can include an XSL rendering directory. Request raw XML.
            filename = row['primaryDocument'].split('/')[-1]
            if not re.fullmatch(r'[A-Za-z0-9_.-]+\.xml', filename, re.I) or filename.startswith('.'):
                raise InvalidRow('Form 4 primary document is not a supported XML filename')
            yield {
                'accession_number': key, 'filing_date': row['filingDate'],
                'document_type': row['form'], 'accepted_at': row.get('acceptanceDateTime'),
                'url': f'https://www.sec.gov/Archives/edgar/data/{int(issuer_cik)}/{key.replace("-", "")}/{filename}',
            }
