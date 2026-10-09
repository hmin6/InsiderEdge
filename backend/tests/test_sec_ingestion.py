from argparse import Namespace
from contextlib import contextmanager
import csv
from datetime import date
from decimal import Decimal
import io
from pathlib import Path
import zipfile
from urllib.error import HTTPError, URLError

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from app.db.models import Base, Company, InsiderTransaction, ResearchEvent
from app.services.sec.bulk import parse_bulk
from app.services.sec.client import SecClient, SecRequestError, discover_quarters, recent_filings
from app.services.sec.edgar import parse_edgar
from app.services.sec.normalize import InvalidRow, assign_identities, cik, accession
from app.services.sec.repository import persist
from scripts.ingest_sec import run

FIXTURES = Path(__file__).parent / 'fixtures' / 'sec'
ACCESSION = '0000000123-26-000001'
METADATA = {'accession_number': ACCESSION, 'filing_date': '2026-09-25',
            'document_type': '4', 'accepted_at': '2026-09-25T20:00:00Z'}


def bulk(**changes):
    tables = {}
    for path in FIXTURES.glob('*.tsv'):
        tables[path.stem] = list(csv.DictReader(io.StringIO(path.read_text()), delimiter='\t'))
    for table, values in changes.items():
        if isinstance(values, list):
            tables[table] = values
        else:
            tables[table][0].update(values)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, rows in tables.items():
            stream = io.StringIO()
            columns = rows[0].keys() if rows else ['ACCESSION_NUMBER', f'{name}_SK']
            writer = csv.DictWriter(stream, columns, delimiter='\t')
            writer.writeheader()
            writer.writerows(rows)
            archive.writestr(f'{name}.tsv', stream.getvalue())
    return buffer.getvalue()


def xml():
    return (FIXTURES / 'form4.xml').read_bytes()


def test_common_normalization_and_filing_time():
    historical = parse_bulk(bulk())
    recent = parse_edgar(xml(), METADATA)
    row = historical.records[0]
    assert row['is_p0_qualifying']
    assert row['transaction_date'] == date(2026, 9, 24)
    assert row['filing_date'] == date(2026, 9, 25)
    assert row['public_event_day'] is None
    assert row['cik'] == '0000000123'
    assert row['ticker'] == 'TEST'
    assert row['transaction_value'] == Decimal('30')
    assert row['security_title'] == 'Common Stock'
    assert row['aff10b5one'] is True
    assert 'CFO' in row['insider_role']
    assert 'Fixture Owner A' in row['insider_name'] and 'Fixture Owner B' in row['insider_name']
    assert len(historical.records) == 1  # Two owners must not double the transaction.
    assert row['canonical_transaction_key'] == recent.records[0]['canonical_transaction_key']
    assert recent.records[0]['accepted_at'].utcoffset().total_seconds() == 0


@pytest.mark.parametrize('code,direction,qualifies', [('P', 'A', True), ('S', 'D', False), ('P', 'D', False), ('A', 'A', False)])
def test_purchase_filter(code, direction, qualifies):
    row = parse_bulk(bulk(NONDERIV_TRANS={'TRANS_CODE': code, 'TRANS_ACQUIRED_DISP_CD': direction})).records[0]
    assert row['is_p0_qualifying'] is qualifies


def test_derivative_purchase_excluded():
    base = list(csv.DictReader(io.StringIO((FIXTURES / 'NONDERIV_TRANS.tsv').read_text()), delimiter='\t'))[0]
    base['DERIV_TRANS_SK'] = base.pop('NONDERIV_TRANS_SK')
    report = parse_bulk(bulk(DERIV_TRANS=[base]))
    assert len(report.records) == 2
    assert report.records[1]['derivative_flag']
    assert not report.records[1]['is_p0_qualifying']
    derivative_xml = xml().replace(b'nonDerivative', b'derivative')
    assert not parse_edgar(derivative_xml, METADATA).records[0]['is_p0_qualifying']


@pytest.mark.parametrize('value', ['', 'not-a-number', 'NaN', 'Infinity', '-1'])
def test_missing_or_malformed_price_does_not_invent_value(value):
    report = parse_bulk(bulk(NONDERIV_TRANS={'TRANS_PRICEPERSHARE': value}))
    assert report.records[0]['price'] is None
    assert report.records[0]['transaction_value'] is None
    assert bool(report.issues) == bool(value)


def test_missing_shares_and_optional_flags():
    report = parse_bulk(bulk(NONDERIV_TRANS={'TRANS_SHARES': ''}, SUBMISSION={'AFF10B5ONE': 'bad'}))
    assert report.records[0]['transaction_value'] is None
    assert report.records[0]['aff10b5one'] is None
    assert report.issues


@pytest.mark.parametrize('field,value', [('TRANS_DATE', 'bad-date'), ('TRANS_CODE', ''), ('TRANS_ACQUIRED_DISP_CD', '')])
def test_malformed_required_transaction_fields_reported(field, value):
    report = parse_bulk(bulk(NONDERIV_TRANS={field: value}))
    assert not report.records
    assert report.issues


def test_orphan_transaction_reported():
    report = parse_bulk(bulk(NONDERIV_TRANS={'ACCESSION_NUMBER': '0000000123-26-000099'}))
    assert not report.records
    assert 'no matching SUBMISSION' in report.issues[0]['reason']


def test_pre_2020_excluded_and_form5_not_included():
    report = parse_bulk(bulk(NONDERIV_TRANS={'TRANS_DATE': '31-DEC-2019'}))
    assert not report.records and report.excluded_before_2020 == 1
    assert not parse_bulk(bulk(SUBMISSION={'DOCUMENT_TYPE': '5'})).records


def test_amendment_provenance_and_distinct_identity():
    original = parse_edgar(xml(), METADATA).records[0]
    amended = parse_edgar(xml().replace(b'<documentType>4<', b'<documentType>4/A<'),
                          {**METADATA, 'document_type': '4/A', 'accession_number': '0000000123-26-000002'}).records[0]
    assert amended['is_amendment']
    assert amended['document_type'] == '4-A'
    assert amended['canonical_transaction_key'] != original['canonical_transaction_key']
    assert parse_bulk(bulk(SUBMISSION={'DOCUMENT_TYPE': '4/A'})).records[0]['is_amendment']


def test_identical_legitimate_rows_keep_occurrences():
    row = parse_bulk(bulk()).records[0]
    rows = [row.copy(), row.copy()]
    assign_identities(rows)
    assert rows[0]['canonical_transaction_key'] != rows[1]['canonical_transaction_key']
    first_keys = [item['canonical_transaction_key'] for item in rows]
    assign_identities(rows)
    assert first_keys == [item['canonical_transaction_key'] for item in rows]


@pytest.fixture
def database():
    engine = create_engine('sqlite://')
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    class DatabaseFixture:
        @contextmanager
        def session(self):
            with Session(engine) as session, session.begin():
                yield session
    db = DatabaseFixture()
    with db.session() as session:
        session.add(Company(ticker='TEST', cik='0000000123', company_name='Synthetic Fixture Company'))
    yield db
    engine.dispose()


def test_repeat_and_cross_source_deduplication(database):
    with database.session() as session:
        assert persist(session, parse_bulk(bulk()))['inserted'] == 1
    with database.session() as session:
        assert persist(session, parse_bulk(bulk()))['duplicates'] == 1
        assert persist(session, parse_edgar(xml(), METADATA))['duplicates'] == 1
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(InsiderTransaction)) == 1
        row = session.scalar(select(InsiderTransaction))
        assert row.accepted_at is not None
        assert row.source_type == 'bulk'
        assert session.scalar(select(func.count()).select_from(ResearchEvent)) == 0


def test_unmapped_rows_surface_and_can_be_enriched(database):
    report = parse_bulk(bulk(SUBMISSION={'ISSUERCIK': '999', 'ISSUERTRADINGSYMBOL': 'UNKNOWN'}))
    with database.session() as session:
        assert persist(session, report)['unmapped'] == 1
        assert session.scalar(select(InsiderTransaction)).ticker is None
    assert report.issues


def test_identifier_validation():
    assert cik('123') == '0000000123'
    assert accession('000000012326000001') == ACCESSION
    with pytest.raises(InvalidRow):
        cik('not-a-cik')


def test_xml_validation():
    with pytest.raises(InvalidRow):
        parse_edgar(b'<!DOCTYPE x><ownershipDocument/>', METADATA)
    with pytest.raises(InvalidRow):
        parse_edgar(b'<html/>', METADATA)
    with pytest.raises(InvalidRow):
        parse_edgar(xml(), {**METADATA, 'document_type': '4/A'})


def test_latest_quarter_discovery_is_dynamic():
    quarters = discover_quarters('<a href="/files/2026q2_form345.zip">Q2</a><a href="/files/2026q3_form345.zip">Q3</a>')
    assert quarters[-1].label == '2026Q3'
    assert quarters[-1].end == date(2026, 9, 30)
    with pytest.raises(InvalidRow):
        discover_quarters('<html>blocked</html>')


def test_rate_limit_and_bounded_retries():
    calls, sleeps = [], []
    def opener(request, timeout):
        calls.append(request)
        assert timeout == 30
        if len(calls) < 3:
            raise HTTPError(request.full_url, 429, 'limited', {'Retry-After': '1'}, None)
        return io.BytesIO(b'ok')
    client = SecClient('Synthetic SEC Test test@example.invalid', opener=opener, clock=lambda: 0, sleeper=sleeps.append)
    assert client.get('https://www.sec.gov/test') == b'ok'
    assert len(calls) == 3 and sleeps == [1, 0.5, 2, 0.5]
    assert calls[0].get_header('User-agent').startswith('Synthetic SEC Test')


def test_403_not_retried_and_network_error_sanitized():
    calls = []
    def forbidden(request, timeout):
        calls.append(1)
        raise HTTPError(request.full_url, 403, 'private-source-value', {}, None)
    client = SecClient('Synthetic SEC Test test@example.invalid', opener=forbidden)
    with pytest.raises(SecRequestError, match='HTTP 403'):
        client.get('https://www.sec.gov/test')
    assert len(calls) == 1
    def disconnected(request, timeout):
        raise URLError('private-source-value')
    client = SecClient('Synthetic SEC Test test@example.invalid', attempts=1, opener=disconnected)
    with pytest.raises(SecRequestError, match=r'^SEC request failed \(network/timeout\)$'):
        client.get('https://www.sec.gov/test')
    with pytest.raises(ValueError):
        client.get('https://example.com/test')


def test_submission_history_and_raw_xml_url():
    columns = {'accessionNumber': [ACCESSION], 'filingDate': ['2026-09-25'], 'form': ['4'],
               'primaryDocument': ['xslF345X05/fixture.xml'], 'acceptanceDateTime': ['2026-09-25T20:00:00Z']}
    class Client:
        def json(self, url):
            if url.endswith('-submissions-001.json'):
                return columns
            return {'filings': {'recent': columns, 'files': [
                {'name': 'CIK0000000123-submissions-001.json', 'filingFrom': '2026-09-01', 'filingTo': '2026-09-30'}]}}
    result = list(recent_filings(Client(), '123', date(2026, 9, 24), date(2026, 10, 9)))
    assert len(result) == 1
    assert result[0]['url'] == 'https://www.sec.gov/Archives/edgar/data/123/000000012326000001/fixture.xml'


def test_local_bulk_cli_path_is_repeatable(tmp_path, database):
    path = tmp_path / '2026q3_form345.zip'
    path.write_bytes(bulk())
    args = Namespace(mode='bulk', bulk_file=[path], start='2020-01-01', end='2026-10-09',
                     cache=tmp_path / 'cache', report=tmp_path / 'report.json', cik=[])
    first = run(args, database=database)
    second = run(args, database=database)
    assert first['bulk_quarters_used'] == ['2026Q3']
    assert first['inserted'] == 1 and second['duplicates'] == 1


def test_gap_fill_cli_uses_overlap_without_generating_events(tmp_path, database):
    import json
    class Client:
        def get(self, url):
            if url.endswith('.xml'):
                return xml()
            return b'<a href="/files/2026q3_form345.zip">2026Q3</a>'
        def json(self, url):
            return {'filings': {'recent': {'accessionNumber': [ACCESSION], 'filingDate': ['2026-09-25'],
                'form': ['4'], 'primaryDocument': ['fixture.xml'], 'acceptanceDateTime': ['2026-09-25T20:00:00Z']}}}
    args = Namespace(mode='edgar', bulk_file=[], start='2020-01-01', end='2026-10-09',
                     cache=tmp_path / 'cache', report=tmp_path / 'report.json', cik=[])
    result = run(args, client=Client(), database=database)
    assert result['edgar_gap_range'] == {'start': '2026-10-01', 'end': '2026-10-09'}
    assert result['edgar_retrieval_range']['start'] == '2026-09-24'
    assert result['inserted'] == 1
    assert json.loads(args.report.read_text())['inserted'] == 1


def test_bulk_rounded_price_matches_full_precision_xml(database):
    historical = parse_bulk(bulk())
    recent = parse_edgar(xml().replace(b'<value>3.00</value>', b'<value>3.0049</value>'), METADATA)
    assert historical.records[0]['canonical_transaction_key'] == recent.records[0]['canonical_transaction_key']
    assert recent.records[0]['price'] == Decimal('3.0049')
    assert recent.records[0]['transaction_value'] == Decimal('30.0490000')
    with database.session() as session:
        assert persist(session, recent)['inserted'] == 1
        assert persist(session, historical)['duplicates'] == 1


def test_exact_large_decimal_product():
    report = parse_bulk(bulk(NONDERIV_TRANS={'TRANS_SHARES': '1234567890123456.12', 'TRANS_PRICEPERSHARE': '1234567890123456.12'}))
    assert report.records[0]['transaction_value'] == Decimal('1524157875323882023167215013565.4544')
