"""Synthetic sources only: no live SEC, Yahoo or production database calls."""
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import xml.etree.ElementTree as ET

import pytest
from sqlalchemy import create_engine, event, inspect, select, func
from sqlalchemy.orm import Session
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.db.models import Base, Company, InsiderTransaction, ResearchEvent, Signal, Price
from app.services.events.build import build_dataset, ownership
from app.services.events.buyers import BuyerEvidence, cached_buyers
from app.services.events.repository import persist_dataset, build_from_database, model_dict
from app.services.sec.normalize import normalize, Report, assign_identities
from app.services.sec.edgar import parse_edgar
from app.services.universe import Universe, CompanyMetadata
from scripts.migrate_event_buyers import migrate


@pytest.fixture
def universe():
    return Universe([CompanyMetadata('TEST', '123', 'Synthetic Fixture Company', 'Technology'),
                     CompanyMetadata('CLASS.A', '999', 'Synthetic A'),
                     CompanyMetadata('CLASS.B', '999', 'Synthetic B')])


def transaction(index=1, **changes):
    raw = dict(accession_number=f'0000000123-24-{index:06d}', source_type='edgar',
               document_type='4', ticker='TEST', cik='123', company_name='Synthetic Fixture Company',
               insider_name='Synthetic Buyer', insider_role='DIRECTOR',
               transaction_date='2024-01-04', filing_date='2024-01-05',
               transaction_code='P', acquired_or_disposed='A', derivative_flag=False,
               shares='10', price='3', shares_owned_after='110', direct_or_indirect='D')
    raw.update(changes)
    row = normalize(raw, Report())
    assert row is not None
    assign_identities([row])
    return row


def prices(start=date(2023, 1, 1), end=date(2024, 1, 20)):
    days = []
    while start <= end:
        if start.weekday() < 5 and start != date(2024, 1, 15):
            days.append(start)
        start += timedelta(days=1)
    return [dict(ticker=ticker, date=day, analysis_price=Decimal('100'))
            for ticker in ('SPY', 'TEST') for day in days]


def evidence(rows, identities=None):
    identities = identities or ['0000000456'] * len(rows)
    return {row['transaction_id']: BuyerEvidence((identity,), 'synthetic verified evidence')
            for row, identity in zip(rows, identities)}


def test_successful_join_and_aggregation_preserves_sources(universe):
    rows = [transaction(), transaction(2, filing_date='2024-01-06', insider_role='OFFICER | CFO')]
    before = [dict(row) for row in rows]
    result = build_dataset(rows, prices(), universe, evidence(rows))
    assert rows == before
    assert len(result.events) == 1 and len(result.transactions) == 2
    event = result.events[0]
    assert event['research_event_id'] == 'TEST:2024-01-08'
    assert event['information_date'] == date(2024, 1, 6)
    assert event['source_transaction_count'] == event['source_filing_count'] == 2
    assert event['aggregate_purchase_value'] == Decimal('60')
    assert event['unique_buyer_count'] == 1
    assert event['has_executive'] and event['has_director'] and event['has_cfo']
    assert event['role_bucket'] == 'Executive'
    assert event['feature_metadata']['market_history']['estimation_paired_observations'] == 100
    assert event['feature_metadata']['market_history']['last_valid_stock_date'] == '2024-01-05'


@pytest.mark.parametrize('filing,expected', [('2024-01-05', '2024-01-08'),
                                           ('2024-01-06', '2024-01-08'),
                                           ('2024-01-07', '2024-01-08'),
                                           ('2024-01-12', '2024-01-16'),
                                           ('2024-01-15', '2024-01-16')])
def test_friday_weekend_holiday_dates(universe, filing, expected):
    row = transaction(filing_date=filing)
    result = build_dataset([row], prices(), universe)
    assert result.events[0]['public_event_day'].isoformat() == expected


@pytest.mark.parametrize('identities,count', [(['0000000456'], 1),
                                            (['0000000456', '0000000789'], 2),
                                            (['0000000456', '0000000456'], 1)])
def test_supported_buyer_counts(universe, identities, count):
    rows = [transaction(i + 1) for i in range(len(identities))]
    result = build_dataset(rows, prices(), universe, evidence(rows, identities))
    assert result.events[0]['unique_buyer_count'] == count


def test_joint_owner_names_are_not_buyer_evidence(universe):
    rows = [transaction(insider_name='Owner One | Owner Two'), transaction(2)]
    result = build_dataset(rows, prices(), universe, evidence(rows[1:]))
    event = result.events[0]
    assert event['unique_buyer_count'] is None
    assert event['feature_metadata']['buyer_identity_status'] == 'unknown'
    assert 'buyer_identity_unknown' in event['feature_metadata']['statuses']
    assert result.transactions[0]['insider_name'] == 'Owner One | Owner Two'
    assert any('buyer identity/count unknown' in issue['reason'] for issue in result.issues)


@pytest.mark.parametrize('role,bucket,executive,director,other', [
    ('OFFICER | DIRECTOR', 'Executive', True, True, False),
    ('DIRECTOR | TENPERCENTOWNER', 'Director', False, True, True),
    ('OTHER', 'Other', False, False, True),
    (None, 'Other', False, False, True),
])
def test_role_hierarchy(universe, role, bucket, executive, director, other):
    event = build_dataset([transaction(insider_role=role)], prices(), universe).events[0]
    assert (event['role_bucket'], event['has_executive'], event['has_director'], event['has_other']) == (
        bucket, executive, director, other)


@pytest.mark.parametrize('shares,after,prior,ratio,new', [
    ('10', '110', '100', '0.1', False),
    ('10', '10', '0', None, True),
    ('10', '9', None, None, None),
    (None, '110', None, None, None),
    ('10', None, None, None, None),
    ('-1', '10', None, None, None),
    ('NaN', '10', None, None, None),
])
def test_ownership_policy(shares, after, prior, ratio, new):
    actual = ownership(dict(shares=shares, shares_owned_after=after))
    assert actual['prior_shares'] == (Decimal(prior) if prior is not None else None)
    assert actual['ownership_change_pct'] == (Decimal(ratio) if ratio is not None else None)
    assert actual['new_position_flag'] is new


def test_event_ownership_max_and_three_state_new_position(universe):
    rows = [transaction(), transaction(2, shares_owned_after='30'), transaction(3, shares_owned_after=None)]
    event = build_dataset(rows, prices(), universe).events[0]
    assert event['max_valid_ownership_change_pct'] == Decimal('0.5')
    assert event['any_new_position_flag'] is None
    rows.append(transaction(4, shares_owned_after='10'))
    assert build_dataset(rows, prices(), universe).events[0]['any_new_position_flag'] is True
    assert build_dataset(rows[:2], prices(), universe).events[0]['any_new_position_flag'] is False


def test_duplicate_source_and_same_filing_counts(universe):
    row = transaction()
    another = transaction(shares='20')
    result = build_dataset([row, dict(row), another], prices(), universe)
    assert result.duplicate_inputs == 1
    assert result.events[0]['source_transaction_count'] == 2
    assert result.events[0]['source_filing_count'] == 1
    assert result.events[0]['aggregate_purchase_value'] == 90


def test_stable_event_identity_order_independent(universe):
    rows = [transaction(), transaction(2)]
    a = build_dataset(rows, prices(), universe, evidence(rows)).events
    b = build_dataset(list(reversed(rows)), list(reversed(prices())), universe, evidence(rows)).events
    assert a == b


@pytest.mark.parametrize('changes,reason', [
    ({'cik': '456', 'ticker': 'UNKNOWN'}, 'unmapped'),
    ({'cik': '999', 'ticker': None}, 'ambiguous'),
    ({'cik': '999'}, 'conflict'),
])
def test_mapping_failures_not_guessed(universe, changes, reason):
    result = build_dataset([transaction(**changes)], prices(), universe)
    assert not result.events
    assert any(reason in issue['reason'] for issue in result.issues)


def test_cik_only_unique_mapping_and_share_classes(universe):
    row = transaction(ticker=None)
    assert build_dataset([row], prices(), universe).events[0]['ticker'] == 'TEST'
    # An exact share class is retained even when issuer CIK is shared.
    class_prices = prices() + [dict(row, ticker='CLASS.B') for row in prices() if row['ticker'] == 'TEST']
    row = transaction(cik='999', ticker='CLASS.B')
    assert build_dataset([row], class_prices, universe).events[0]['ticker'] == 'CLASS.B'


@pytest.mark.parametrize('data', [[], prices(end=date(2024, 1, 5)),
                                prices(start=date(2024, 1, 8)),
                                prices(end=date(2023, 12, 1)) + prices(start=date(2024, 1, 18))])
def test_missing_calendar_does_not_invent_event_day(universe, data):
    result = build_dataset([transaction()], data, universe)
    assert not result.events
    assert any('calendar coverage' in issue['reason'] for issue in result.issues)


def test_history_and_missing_event_price_flagged_without_features(universe):
    data = [row for row in prices(start=date(2024, 1, 1))
            if not (row['ticker'] == 'TEST' and row['date'] == date(2024, 1, 8))]
    result = build_dataset([transaction()], data, universe)
    event = result.events[0]
    assert 'insufficient_market_history' in event['feature_metadata']['statuses']
    assert 'missing_stock_event_price' in event['feature_metadata']['statuses']
    assert not {'returns', 'volatility', 'car30', 'prediction', 'activity_score'} & event.keys()


def test_amendments_are_provenance_not_independent_event(universe):
    original, amended = transaction(), transaction(2, document_type='4/A')
    result = build_dataset([original, amended], prices(), universe)
    assert result.events[0]['source_transaction_count'] == 1
    assert any('amendment' in issue['reason'] for issue in result.issues)
    assert amended['is_amendment'] and amended['document_type'] == '4-A'


@pytest.mark.parametrize('changes', [{'transaction_code': 'S'}, {'acquired_or_disposed': 'D'},
                                     {'derivative_flag': True}, {'document_type': '4-A'},
                                     {'filing_date': '2019-12-31', 'transaction_date': '2019-12-30'},
                                     {'transaction_date': '2024-01-06'}])
def test_exact_qualification(universe, changes):
    if changes.get('filing_date', '').startswith('2019'):
        row = dict(transaction(), filing_date=date(2019, 12, 31), transaction_date=date(2019, 12, 30))
    else:
        row = transaction(**changes)
    assert not build_dataset([row], prices(), universe).events


def test_missing_values_sum_valid_only_no_fake_zero(universe):
    event = build_dataset([transaction(price=None)], prices(), universe).events[0]
    assert event['aggregate_purchase_value'] is None
    result = build_dataset([transaction(price=None), transaction(2)], prices(), universe)
    assert result.events[0]['aggregate_purchase_value'] == 30
    assert 'purchase_value_incomplete' in result.events[0]['feature_metadata']['statuses']


@pytest.fixture
def engine():
    engine = create_engine('sqlite://')
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def test_nullable_schema_and_idempotent_persistence(engine, universe):
    assert next(c for c in inspect(engine).get_columns('research_events') if c['name'] == 'unique_buyer_count')['nullable']
    ddl = str(CreateTable(ResearchEvent.__table__).compile(dialect=postgresql.dialect()))
    assert 'unique_buyer_count INTEGER NOT NULL' not in ddl
    rows = [transaction(ticker=None), transaction(2)]
    with Session(engine) as session, session.begin():
        session.add(Company(ticker='TEST', cik='0000000123', company_name='Synthetic Fixture Company'))
        session.flush()
        session.add_all(InsiderTransaction(**row) for row in rows)
    dataset = build_dataset(rows, prices(), universe)
    with Session(engine) as session, session.begin():
        assert persist_dataset(session, dataset, universe)['events_inserted'] == 1
    with Session(engine) as session, session.begin():
        counts = persist_dataset(session, dataset, universe)
        assert counts['events_inserted'] == counts['events_updated'] == counts['transactions_enriched'] == 0
        assert counts['events_unchanged'] == 1
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ResearchEvent)) == 1
        assert session.scalar(select(func.count()).select_from(InsiderTransaction)) == 2
        assert session.scalar(select(ResearchEvent.unique_buyer_count)) is None
        stored = session.get(InsiderTransaction, rows[0]['transaction_id'])
        assert stored.ticker == 'TEST' and stored.public_event_day == date(2024, 1, 8)
        for name in ('transaction_date', 'filing_date', 'insider_name', 'shares', 'price', 'canonical_transaction_key'):
            assert getattr(stored, name) == rows[0][name]


def test_changed_event_with_signal_requires_review(engine, universe):
    rows = [transaction()]
    dataset = build_dataset(rows, prices(), universe)
    with Session(engine) as session, session.begin():
        session.add(Company(ticker='TEST', cik='0000000123', company_name='Synthetic Fixture Company'))
        session.flush()
        session.add(InsiderTransaction(**rows[0]))
        session.flush()
        persist_dataset(session, dataset, universe)
        session.add(Signal(signal_id='synthetic', research_event_id='TEST:2024-01-08', ticker='TEST',
                           public_event_day=date(2024, 1, 8), score_status='insufficient_data', unavailable_components=[]))
    dataset.events[0]['unique_buyer_count'] = 1
    with Session(engine) as session, session.begin():
        with pytest.raises(ValueError, match='downstream signals'):
            persist_dataset(session, dataset, universe)


def xml_source(tmp_path, single=False):
    root = ET.parse(Path(__file__).parent / 'fixtures/sec/form4.xml').getroot()
    if single:
        root.remove(root.findall('reportingOwner')[1])
    data = ET.tostring(root)
    metadata = {'accession_number': '0000000123-26-000001', 'filing_date': '2026-09-25', 'document_type': '4'}
    report = parse_edgar(data, metadata)
    (tmp_path / f'{metadata["accession_number"]}.xml').write_bytes(data)
    return report.records


def test_single_owner_cache_evidence_verified_against_transaction(tmp_path):
    rows = xml_source(tmp_path, single=True)
    mapping, issues = cached_buyers(tmp_path, rows)
    assert not issues and mapping[rows[0]['transaction_id']].identities == ('0000000456',)
    mismatch = dict(rows[0], canonical_transaction_key='not-in-source')
    assert not cached_buyers(tmp_path, [mismatch])[0]


def test_joint_filer_and_absent_cache_never_guessed(tmp_path):
    rows = xml_source(tmp_path)
    assert not cached_buyers(tmp_path, rows)[0]
    rows[0]['insider_name'] = 'Only One Name'
    assert not cached_buyers(tmp_path, rows)[0]
    assert not cached_buyers(tmp_path / 'missing', rows)[0]


def test_buyer_migration_guard_and_exact_change():
    engine = MagicMock()
    engine.dialect.name = 'postgresql'
    connection = engine.begin.return_value.__enter__.return_value
    inspector = Mock()
    with patch('scripts.migrate_event_buyers.inspect', return_value=inspector):
        inspector.get_columns.return_value = [{'name': 'unique_buyer_count', 'nullable': False}]
        migrate(engine)
        assert str(connection.execute.call_args.args[0]) == 'ALTER TABLE research_events ALTER COLUMN unique_buyer_count DROP NOT NULL'
        connection.execute.reset_mock()
        inspector.get_columns.return_value[0]['nullable'] = True
        migrate(engine)
        connection.execute.assert_not_called()


def test_missing_spy_session_detected_from_other_persisted_prices(universe):
    data = [row for row in prices() if not (row['ticker'] == 'SPY' and row['date'] == date(2024, 1, 8))]
    result = build_dataset([transaction()], data, universe)
    assert not result.events
    assert any('session missing from SPY' in issue['reason'] for issue in result.issues)


def test_database_window_keeps_complete_weekend_group_and_dry_run(engine, universe, tmp_path):
    rows = [transaction(), transaction(2, filing_date='2024-01-06')]
    with Session(engine) as session, session.begin():
        session.add(Company(ticker='TEST', cik='0000000123', company_name='Synthetic Fixture Company'))
        session.flush()
        session.add_all(InsiderTransaction(**row) for row in rows)
        session.add_all(Price(**row) for row in prices())
    with Session(engine) as session, session.begin():
        dataset, counts = build_from_database(session, universe, tmp_path, date(2024, 1, 6), date(2024, 1, 6), write=False)
        assert not counts and dataset.events[0]['source_transaction_count'] == 2
        assert dataset.events[0]['information_date'] == date(2024, 1, 6)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ResearchEvent)) == 0
        assert all(row.public_event_day is None for row in session.scalars(select(InsiderTransaction)))
    with Session(engine) as session, session.begin():
        dataset, counts = build_from_database(session, universe, tmp_path, date(2024, 1, 6), date(2024, 1, 6))
        assert counts['events_inserted'] == 1
    with Session(engine) as session, session.begin():
        _, counts = build_from_database(session, universe, tmp_path, date(2024, 1, 6), date(2024, 1, 6))
        assert counts['events_unchanged'] == 1


def test_corrected_aggregate_updates_same_event(engine, universe):
    rows = [transaction()]
    with Session(engine) as session, session.begin():
        session.add(Company(ticker='TEST', cik='0000000123', company_name='Synthetic Fixture Company'))
        session.flush()
        session.add(InsiderTransaction(**rows[0]))
        session.flush()
        persist_dataset(session, build_dataset(rows, prices(), universe), universe)
    rows.append(transaction(2))
    with Session(engine) as session, session.begin():
        session.add(InsiderTransaction(**rows[1]))
        session.flush()
        counts = persist_dataset(session, build_dataset(rows, prices(), universe, evidence(rows)), universe)
        assert counts['events_updated'] == 1
    with Session(engine) as session:
        event = session.scalar(select(ResearchEvent))
        assert event.research_event_id == 'TEST:2024-01-08'
        assert event.source_transaction_count == 2 and event.unique_buyer_count == 1
        assert event.aggregate_purchase_value == 60


def test_bulk_owner_evidence_single_and_joint(tmp_path):
    import io
    import zipfile
    row = transaction()
    path = tmp_path / '2024q1_form345.zip'
    header = 'ACCESSION_NUMBER\tRPTOWNERCIK\tRPTOWNERNAME\n'
    def write(owners):
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('REPORTINGOWNER.tsv', header + ''.join(
                f'{row["accession_number"]}\t{owner}\tSynthetic Name\n' for owner in owners))
    write(['456'])
    mapping, issues = cached_buyers(tmp_path, [row])
    assert not issues
    assert mapping[row['transaction_id']].identities == ('0000000456',)
    write(['456', '789'])
    assert not cached_buyers(tmp_path, [row])[0]
    write(['456', ''])
    assert not cached_buyers(tmp_path, [row])[0]


def test_invalid_cached_owner_source_reported(tmp_path):
    row = transaction()
    (tmp_path / f'{row["accession_number"]}.xml').write_text('<invalid>', encoding='utf-8')
    mapping, issues = cached_buyers(tmp_path, [row])
    assert not mapping and issues


def test_null_buyer_count_never_converted_to_zero(universe):
    row = transaction(insider_name='Known-looking name', insider_role='OFFICER')
    invalid_evidence = {row['transaction_id']: BuyerEvidence((), 'empty source association')}
    event = build_dataset([row], prices(), universe, invalid_evidence).events[0]
    assert event['unique_buyer_count'] is None
    assert 'buyer_identity_unknown' in event['feature_metadata']['statuses']


def seed_event_sources(engine, universe, rows):
    with Session(engine) as session, session.begin():
        session.add(Company(ticker='TEST', cik='0000000123', company_name='Synthetic Fixture Company'))
        session.flush()
        session.add_all(InsiderTransaction(**row) for row in rows)
        session.flush()
        persist_dataset(session, build_dataset(rows, prices(), universe), universe)


def test_overlap_guard_allows_unchanged_mapping(engine, universe):
    row = transaction()
    seed_event_sources(engine, universe, [row])
    dataset = build_dataset([row], prices(), universe)
    with Session(engine) as session, session.begin():
        counts = persist_dataset(session, dataset, universe)
        assert counts['events_unchanged'] == 1
        assert counts['events_blocked'] == counts['events_inserted'] == counts['transactions_enriched'] == 0
        assert not any('reconciliation required' in issue['reason'] for issue in dataset.issues)


@pytest.mark.parametrize('linked', [False, True])
def test_calendar_remap_overlap_blocks_new_event_preserves_retained(engine, universe, linked):
    row = transaction()
    seed_event_sources(engine, universe, [row])
    with Session(engine) as session, session.begin():
        old = session.get(ResearchEvent, 'TEST:2024-01-08')
        # Exercise pre-guard retained metadata, which had only source IDs.
        old.feature_metadata = {k: v for k, v in old.feature_metadata.items()
                                if k != 'source_canonical_transaction_keys'}
        if linked:
            session.add(Signal(signal_id='retained-signal', research_event_id=old.research_event_id,
                               ticker='TEST', public_event_day=date(2024, 1, 8),
                               score_status='insufficient_data', unavailable_components=[]))
        session.flush()
        before = {column.name: getattr(old, column.name) for column in ResearchEvent.__table__.columns}
    changed_calendar = [price for price in prices() if price['date'] != date(2024, 1, 8)]
    dataset = build_dataset([row], changed_calendar, universe)
    assert dataset.events[0]['research_event_id'] == 'TEST:2024-01-09'
    with Session(engine) as session, session.begin():
        counts = persist_dataset(session, dataset, universe)
        assert counts['events_blocked'] == 1
        assert counts['events_inserted'] == counts['events_updated'] == counts['transactions_enriched'] == 0
    diagnostics = [issue for issue in dataset.issues if issue.get('existing_research_event_id')]
    assert diagnostics == [{
        'transaction_id': row['transaction_id'],
        'canonical_transaction_key': row['canonical_transaction_key'],
        'existing_research_event_id': 'TEST:2024-01-08',
        'proposed_research_event_id': 'TEST:2024-01-09',
        'reason': 'source transaction belongs to another retained research event; reconciliation required',
    }]
    with Session(engine) as session:
        old = session.get(ResearchEvent, 'TEST:2024-01-08')
        assert {column.name: getattr(old, column.name) for column in ResearchEvent.__table__.columns} == before
        assert session.get(ResearchEvent, 'TEST:2024-01-09') is None
        assert session.get(InsiderTransaction, row['transaction_id']).public_event_day == date(2024, 1, 8)
        assert session.scalar(select(func.count()).select_from(Signal)) == int(linked)


def test_one_overlapping_source_blocks_entire_proposed_event(engine, universe):
    old, new = transaction(), transaction(2)
    seed_event_sources(engine, universe, [old])
    with Session(engine) as session, session.begin():
        session.add(InsiderTransaction(**new))
    changed_calendar = [price for price in prices() if price['date'] != date(2024, 1, 8)]
    dataset = build_dataset([old, new], changed_calendar, universe)
    assert dataset.events[0]['source_transaction_count'] == 2
    with Session(engine) as session, session.begin():
        counts = persist_dataset(session, dataset, universe)
        assert counts['events_blocked'] == 1 and counts['transactions_enriched'] == 0
    with Session(engine) as session:
        assert session.get(ResearchEvent, 'TEST:2024-01-09') is None
        assert session.get(ResearchEvent, 'TEST:2024-01-08') is not None
        assert session.get(InsiderTransaction, new['transaction_id']).public_event_day is None
        assert session.scalar(select(func.count()).select_from(InsiderTransaction)) == 2


def test_overlap_blocks_update_of_existing_target_event(engine, universe):
    old, target = transaction(), transaction(2, filing_date='2024-01-08')
    seed_event_sources(engine, universe, [old, target])
    changed_calendar = [price for price in prices() if price['date'] != date(2024, 1, 8)]
    dataset = build_dataset([old, target], changed_calendar, universe)
    assert len(dataset.events) == 1 and dataset.events[0]['source_transaction_count'] == 2
    with Session(engine) as session, session.begin():
        counts = persist_dataset(session, dataset, universe)
        assert counts['events_blocked'] == 1 and counts['events_updated'] == 0
    with Session(engine) as session:
        for identifier in ('TEST:2024-01-08', 'TEST:2024-01-09'):
            assert session.get(ResearchEvent, identifier).source_transaction_count == 1


def test_different_sources_in_different_events_are_not_false_positives(engine, universe):
    old, new = transaction(), transaction(2, filing_date='2024-01-08')
    seed_event_sources(engine, universe, [old])
    with Session(engine) as session, session.begin():
        session.add(InsiderTransaction(**new))
        session.flush()
        dataset = build_dataset([old, new], prices(), universe)
        counts = persist_dataset(session, dataset, universe)
        assert counts['events_blocked'] == 0
        assert counts['events_unchanged'] == counts['events_inserted'] == 1
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ResearchEvent)) == 2


def test_canonical_metadata_overlap_survives_source_row_removal(engine, universe):
    row = transaction()
    seed_event_sources(engine, universe, [row])
    with Session(engine) as session, session.begin():
        # Only synthetic isolated test data is removed. Retained metadata keeps
        # canonical identity even when the original source row is unavailable.
        session.delete(session.get(InsiderTransaction, row['transaction_id']))
    changed_calendar = [price for price in prices() if price['date'] != date(2024, 1, 8)]
    dataset = build_dataset([row], changed_calendar, universe)
    with Session(engine) as session, session.begin():
        counts = persist_dataset(session, dataset, universe)
        assert counts['events_blocked'] == 1
        assert session.get(ResearchEvent, 'TEST:2024-01-08') is not None
        assert session.get(ResearchEvent, 'TEST:2024-01-09') is None
    assert any(issue.get('canonical_transaction_key') == row['canonical_transaction_key'] for issue in dataset.issues)


def test_unchanged_legacy_event_with_signal_is_not_invalidated(engine, universe):
    row = transaction()
    seed_event_sources(engine, universe, [row])
    with Session(engine) as session, session.begin():
        retained = session.get(ResearchEvent, 'TEST:2024-01-08')
        retained.feature_metadata = {k: v for k, v in retained.feature_metadata.items()
                                     if k != 'source_canonical_transaction_keys'}
        session.add(Signal(signal_id='legacy-signal', research_event_id=retained.research_event_id,
                           ticker='TEST', public_event_day=date(2024, 1, 8),
                           score_status='insufficient_data', unavailable_components=[]))
    with Session(engine) as session, session.begin():
        counts = persist_dataset(session, build_dataset([row], prices(), universe), universe)
        assert counts['events_unchanged'] == 1
        assert counts['events_blocked'] == counts['events_updated'] == 0
        assert session.get(Signal, 'legacy-signal') is not None
