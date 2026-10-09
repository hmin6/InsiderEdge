"""Source-independent normalization and deterministic transaction identities."""
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import hashlib
import json
import re


class InvalidRow(ValueError):
    """An essential source field is missing or invalid."""


@dataclass
class Report:
    records: list[dict] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)
    excluded_before_2020: int = 0

    def issue(self, accession: str | None, field: str, reason: str) -> None:
        # Intentionally omit source values and connection/request details.
        self.issues.append({'accession_number': accession, 'field': field, 'reason': reason})


def text(value) -> str | None:
    result = str(value).strip() if value is not None else ''
    return result or None


def cik(value) -> str:
    value = text(value)
    if value is None or not re.fullmatch(r'\d{1,10}', value) or int(value) == 0:
        raise InvalidRow('invalid CIK')
    return value.zfill(10)


def accession(value) -> str:
    value = (text(value) or '').replace('-', '')
    if not re.fullmatch(r'\d{18}', value):
        raise InvalidRow('invalid accession number')
    return f'{value[:10]}-{value[10:12]}-{value[12:]}'


def day(value) -> date:
    value = text(value)
    for pattern in ('%Y-%m-%d', '%d-%b-%Y'):
        try:
            return datetime.strptime(value or '', pattern).date()
        except ValueError:
            pass
    raise InvalidRow('invalid date')


def flag(value) -> bool | None:
    value = (text(value) or '').lower()
    if not value:
        return None
    if value in {'1', 'true', 'yes'}:
        return True
    if value in {'0', 'false', 'no'}:
        return False
    raise InvalidRow('invalid boolean')


def number(value, name: str, report: Report, source_id: str) -> Decimal | None:
    value = text(value)
    if value is None:
        return None
    try:
        result = Decimal(value)
        if not result.is_finite() or result < 0:
            raise InvalidOperation
        return result
    except InvalidOperation:
        report.issue(source_id, name, 'invalid numeric; stored as NULL')
        return None


def normalize(raw: dict, report: Report) -> dict | None:
    """Both source parsers emit this common field vocabulary."""
    source_id = None
    try:
        source_id = accession(raw.get('accession_number'))
        document = (text(raw.get('document_type')) or '').upper().replace('/', '-')
        if document not in {'4', '4-A'}:
            return None
        transaction_date = day(raw.get('transaction_date'))
        filing_date = day(raw.get('filing_date'))
        if transaction_date < date(2020, 1, 1) or filing_date < date(2020, 1, 1):
            report.excluded_before_2020 += 1
            return None
        issuer_cik = cik(raw.get('cik'))
        code = (text(raw.get('transaction_code')) or '').upper()
        direction = (text(raw.get('acquired_or_disposed')) or '').upper()
        if not re.fullmatch('[A-Z]', code) or direction not in {'A', 'D'}:
            raise InvalidRow('missing/invalid transaction code or acquisition/disposition')
        derivative = raw['derivative_flag']
        if not isinstance(derivative, bool):
            raise InvalidRow('invalid derivative flag')
        accepted_at = None
        if text(raw.get('accepted_at')):
            try:
                accepted_at = datetime.fromisoformat(raw['accepted_at'].replace('Z', '+00:00'))
                if accepted_at.tzinfo is None:
                    raise ValueError
            except (ValueError, TypeError):
                accepted_at = None
                report.issue(source_id, 'accepted_at', 'invalid or timezone-free timestamp; stored as NULL')
        try:
            aff = flag(raw.get('aff10b5one'))
        except InvalidRow:
            report.issue(source_id, 'aff10b5one', 'invalid boolean; stored as NULL')
            aff = None
        shares = number(raw.get('shares'), 'shares', report, source_id)
        price = number(raw.get('price'), 'price', report, source_id)
        transaction_value = None
        if shares is not None and price is not None:
            with localcontext() as context:
                context.prec = max(28, len(shares.as_tuple().digits) + len(price.as_tuple().digits))
                transaction_value = shares * price
        result = {
            'accession_number': source_id, 'source_type': raw['source_type'],
            'document_type': document, 'ticker': (text(raw.get('ticker')) or '').upper() or None,
            'cik': issuer_cik, 'company_name': text(raw.get('company_name')),
            'insider_name': text(raw.get('insider_name')), 'insider_role': text(raw.get('insider_role')),
            'transaction_date': transaction_date, 'filing_date': filing_date,
            'accepted_at': accepted_at, 'public_event_day': None,
            'transaction_code': code, 'acquired_or_disposed': direction,
            'derivative_flag': derivative, 'source_table': 'DERIV_TRANS' if derivative else 'NONDERIV_TRANS',
            'security_title': text(raw.get('security_title')), 'shares': shares, 'price': price,
            'transaction_value': transaction_value,
            'shares_owned_after': number(raw.get('shares_owned_after'), 'shares_owned_after', report, source_id),
            'direct_or_indirect': (text(raw.get('direct_or_indirect')) or '').upper() or None,
            'aff10b5one': aff, 'is_amendment': document == '4-A',
            'is_p0_qualifying': not derivative and code == 'P' and direction == 'A',
        }
        if not result['ticker']:
            report.issue(source_id, 'ticker', 'missing issuer symbol; requires existing company mapping')
        return result
    except (InvalidRow, ValueError, KeyError, TypeError) as error:
        reason = str(error) if isinstance(error, InvalidRow) else 'invalid required source field'
        report.issue(source_id, 'row', reason)
        return None


IDENTITY_FIELDS = ('accession_number', 'derivative_flag', 'transaction_date',
                   'transaction_code', 'acquired_or_disposed', 'security_title',
                   'shares', 'price', 'shares_owned_after', 'direct_or_indirect')


def assign_identities(records: list[dict]) -> None:
    """Preserve repeated identical rows using per-filing signature occurrence counts."""
    counts = Counter()
    for row in records:
        values = []
        for name in IDENTITY_FIELDS:
            value = row[name]
            if isinstance(value, Decimal):
                # SEC bulk numeric columns use scale 2; original XML can be more
                # precise. Match on bulk precision without rounding stored values.
                with localcontext() as context:
                    context.prec = max(28, len(value.as_tuple().digits), value.adjusted() + 3)
                    value = format(value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), '.2f')
            elif isinstance(value, date):
                value = value.isoformat()
            elif isinstance(value, str):
                value = ' '.join(value.split()).casefold()
            values.append(value)
        digest = hashlib.sha256(json.dumps(values, separators=(',', ':')).encode()).hexdigest()
        counts[digest] += 1
        key = f'{row["accession_number"]}:{digest}:{counts[digest]}'
        row['canonical_transaction_key'] = key
        row['transaction_id'] = hashlib.sha256(key.encode()).hexdigest()
