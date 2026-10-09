"""Offline frozen-universe lookups; issuer CIKs do not identify share classes."""
import csv
from dataclasses import dataclass
from pathlib import Path
import re

DEFAULT_UNIVERSE = Path(__file__).resolve().parents[3] / 'config' / 'universe.csv'
TICKER_ALIASES = {'BRK-B': 'BRK.B', 'BRK B': 'BRK.B'}


def normalize_ticker(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError('Ticker must be text')
    value = value.strip().upper()
    value = TICKER_ALIASES.get(value, value)
    if not re.fullmatch(r'[A-Z0-9]+(?:[.-][A-Z0-9]+)*', value):
        raise ValueError('Invalid ticker')
    return value


def normalize_cik(value) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError('CIK must be integer or digit string')
    value = str(value).strip()
    if not re.fullmatch(r'\d{1,10}', value) or int(value) == 0:
        raise ValueError('Invalid CIK')
    return value.zfill(10)


@dataclass(frozen=True)
class CompanyMetadata:
    ticker: str
    cik: str | None
    company_name: str
    sector: str | None = None


@dataclass(frozen=True)
class IssuerResolution:
    status: str
    ticker: str | None
    tickers: tuple[str, ...]
    reason: str


class AmbiguousCIKError(ValueError):
    def __init__(self, cik: str, tickers: tuple[str, ...]):
        self.cik, self.tickers = cik, tickers
        super().__init__(f'Issuer CIK {cik} has multiple tickers: {", ".join(tickers)}')


class Universe:
    def __init__(self, companies):
        self._by_ticker = {}
        self._by_cik = {}
        for company in companies:
            ticker = normalize_ticker(company.ticker)
            issuer_cik = normalize_cik(company.cik)
            if ticker in self._by_ticker:
                raise ValueError('Duplicate canonical ticker in universe')
            if not company.company_name.strip():
                raise ValueError('Missing company name')
            normalized = CompanyMetadata(ticker, issuer_cik, company.company_name.strip(),
                                         company.sector.strip() if company.sector else None)
            self._by_ticker[ticker] = normalized
            if issuer_cik:
                self._by_cik.setdefault(issuer_cik, []).append(ticker)

    @classmethod
    def from_csv(cls, path=DEFAULT_UNIVERSE):
        with Path(path).open(newline='', encoding='utf-8-sig') as source:
            reader = csv.DictReader(source)
            if not {'ticker', 'cik', 'company_name', 'sector'} <= set(reader.fieldnames or []):
                raise ValueError('Universe CSV missing required columns')
            return cls(CompanyMetadata(row['ticker'], row['cik'], row['company_name'], row['sector']) for row in reader)

    @property
    def companies(self) -> tuple[CompanyMetadata, ...]:
        return tuple(self._by_ticker[key] for key in sorted(self._by_ticker))

    def ticker_to_company(self, ticker) -> CompanyMetadata | None:
        try:
            return self._by_ticker.get(normalize_ticker(ticker))
        except ValueError:
            return None

    def ticker_to_cik(self, ticker) -> str | None:
        company = self.ticker_to_company(ticker)
        return company.cik if company else None

    def cik_to_tickers(self, cik) -> tuple[str, ...]:
        try:
            return tuple(sorted(self._by_cik.get(normalize_cik(cik), ())))
        except ValueError:
            return ()

    def cik_to_ticker(self, cik) -> str | None:
        tickers = self.cik_to_tickers(cik)
        if len(tickers) > 1:
            raise AmbiguousCIKError(normalize_cik(cik), tickers)
        return tickers[0] if tickers else None

    def resolve_issuer(self, cik, ticker=None) -> IssuerResolution:
        """Report missing, conflicting, and ambiguous SEC issuer identifiers."""
        try:
            issuer_cik = normalize_cik(cik)
        except ValueError:
            return IssuerResolution('invalid', None, (), 'invalid issuer CIK')
        candidates = self.cik_to_tickers(issuer_cik)
        company = self.ticker_to_company(ticker)
        if company:
            if issuer_cik and company.cik and issuer_cik != company.cik:
                return IssuerResolution('conflict', None, candidates, 'ticker and issuer CIK disagree')
            return IssuerResolution('matched', company.ticker, (company.ticker,), 'exact ticker match')
        if len(candidates) == 1:
            return IssuerResolution('matched', candidates[0], candidates, 'unique issuer CIK match')
        if len(candidates) > 1:
            return IssuerResolution('ambiguous', None, candidates, 'issuer CIK maps to multiple share classes')
        return IssuerResolution('unmapped', None, (), 'issuer is absent or has no known mapping')
