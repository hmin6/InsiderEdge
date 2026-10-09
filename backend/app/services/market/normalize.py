from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from numbers import Number

import pandas as pd

from app.services.universe import normalize_ticker

FIELDS = {'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close',
          'Adj Close': 'adjusted_close', 'Volume': 'volume'}


@dataclass
class PriceBatch:
    rows: list[dict] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)
    duplicates: int = 0

    def issue(self, field, reason, day=None):
        self.issues.append({'date': day.isoformat() if day else None, 'field': field, 'reason': reason})


def session_date(value) -> date:
    if isinstance(value, Number):
        raise ValueError('Numeric index is not a daily session label')
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        raise ValueError('Missing date')
    if stamp.tzinfo is not None:
        stamp = stamp.tz_convert('America/New_York')
    return stamp.date()


def numeric(value, name, batch, day):
    if value is None or pd.isna(value):
        return None
    try:
        result = Decimal(str(value))
        if not result.is_finite():
            raise InvalidOperation
        if name == 'volume':
            if result < 0 or result != result.to_integral_value() or result > 9223372036854775807:
                raise InvalidOperation
            return int(result)
        if result <= 0:
            raise InvalidOperation
        return result
    except (InvalidOperation, ValueError):
        batch.issue(name, 'invalid numeric value; stored as NULL', day)
        return None


def normalize_prices(frame, ticker: str, start: date, end: date) -> PriceBatch:
    """Daily labels use New York session dates; bounds are start inclusive/end exclusive."""
    ticker = normalize_ticker(ticker)
    batch = PriceBatch()
    if isinstance(frame.columns, pd.MultiIndex) or frame.columns.duplicated().any():
        raise ValueError('Expected unambiguous single-symbol columns')
    missing = set(FIELDS) - set(frame.columns)
    for column in sorted(missing):
        batch.issue(FIELDS[column], 'provider column missing; stored as NULL')
    if not set(FIELDS) & set(frame.columns):
        raise ValueError('Provider returned no price/volume columns')
    by_date, conflicting = {}, set()
    for label, values in frame.iterrows():
        try:
            day = session_date(label)
        except (ValueError, TypeError, OverflowError):
            batch.issue('date', 'invalid session label; row skipped')
            continue
        if not start <= day < end:
            batch.issue('date', 'outside requested completed-session range; row skipped', day)
            continue
        row = {'ticker': ticker, 'date': day}
        for column, name in FIELDS.items():
            row[name] = numeric(values.get(column), name, batch, day)
        row['analysis_price'] = row['adjusted_close']
        if row['analysis_price'] is None:
            batch.issue('analysis_price', 'adjusted close unavailable; no raw-close fallback', day)
        if all(row[name] is None for name in FIELDS.values()):
            batch.issue('row', 'no valid price or volume values; row skipped', day)
            continue
        if day in conflicting:
            batch.duplicates += 1
            continue
        if day in by_date:
            batch.duplicates += 1
            if row != by_date[day]:
                del by_date[day]
                conflicting.add(day)
                batch.issue('row', 'conflicting duplicate session; all observations for date skipped', day)
            continue
        by_date[day] = row
    batch.rows = [by_date[day] for day in sorted(by_date)]
    return batch
