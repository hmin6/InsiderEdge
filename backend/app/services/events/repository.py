"""Existing-table persistence for the merged research-event dataset."""
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.models import Company, InsiderTransaction, Price, ResearchEvent, Signal
from app.services.universe import normalize_cik
from .build import build_dataset
from .buyers import cached_buyers


def model_dict(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def overlap_guard(session, dataset):
    """Preflight retained-event associations before any dataset writes."""
    keys_by_id = {row['transaction_id']: row['canonical_transaction_key'] for row in dataset.transactions}
    proposed_keys = set(keys_by_id.values())
    # Resolve legacy retained metadata through the existing Issue #2 identities.
    # Include the proposal's IDs so a retained association survives source removal.
    keys = sorted(proposed_keys)
    for offset in range(0, len(keys), 500):
        keys_by_id.update(session.execute(select(
            InsiderTransaction.transaction_id, InsiderTransaction.canonical_transaction_key
        ).where(InsiderTransaction.canonical_transaction_key.in_(keys[offset:offset + 500]))).all())
    retained = {}
    for identifier, metadata in session.execute(select(ResearchEvent.research_event_id, ResearchEvent.feature_metadata)):
        metadata = metadata or {}
        canonical_keys = set(metadata.get('source_canonical_transaction_keys', []))
        canonical_keys.update(keys_by_id[identity] for identity in metadata.get('source_transaction_ids', [])
                              if identity in keys_by_id)
        for key in canonical_keys & proposed_keys:
            retained.setdefault(key, set()).add(identifier)
    blocked = set()
    for event in dataset.events:
        proposed = event['research_event_id']
        for identity in event['feature_metadata']['source_transaction_ids']:
            key = keys_by_id[identity]
            for existing in sorted(retained.get(key, set()) - {proposed}):
                blocked.add(proposed)
                dataset.issues.append({
                    'transaction_id': identity, 'canonical_transaction_key': key,
                    'existing_research_event_id': existing,
                    'proposed_research_event_id': proposed,
                    'reason': 'source transaction belongs to another retained research event; reconciliation required',
                })
    return blocked, keys_by_id


def persist_dataset(session, dataset, universe):
    dialect = session.get_bind().dialect.name
    if dialect not in {'postgresql', 'sqlite'}:
        raise ValueError('Unsupported event persistence dialect')
    insert = postgres_insert if dialect == 'postgresql' else sqlite_insert
    blocked, keys_by_id = overlap_guard(session, dataset)
    events = [event for event in dataset.events if event['research_event_id'] not in blocked]
    accepted_sources = {identity for event in events for identity in event['feature_metadata']['source_transaction_ids']}
    # The frozen Issue #3 snapshot is the company contract, not a second provider.
    for ticker in sorted({row['ticker'] for row in events}):
        company = universe.ticker_to_company(ticker)
        existing = session.get(Company, ticker)
        if existing is not None and existing.cik and normalize_cik(existing.cik) != company.cik:
            raise ValueError('Existing company CIK conflicts with frozen universe; review required')
        session.execute(insert(Company).values(ticker=ticker, cik=company.cik,
                                              company_name=company.company_name, sector=company.sector)
                        .on_conflict_do_nothing(index_elements=['ticker']))
    counts = {'events_inserted': 0, 'events_updated': 0, 'events_unchanged': 0,
              'events_blocked': len(blocked), 'transactions_enriched': 0}
    for event in events:
        # A different producer's identity needs review rather than silent replacement.
        existing = session.scalar(select(ResearchEvent).where(
            ResearchEvent.ticker == event['ticker'], ResearchEvent.public_event_day == event['public_event_day']))
        row = dict(event)
        if existing is not None:
            if existing.research_event_id != row['research_event_id']:
                raise ValueError('Existing research event uses a different identity; review required')
            row['feature_metadata'] = {**(existing.feature_metadata or {}), **row['feature_metadata']}
            changed = any(getattr(existing, name) != value for name, value in row.items())
            if not changed:
                counts['events_unchanged'] += 1
                continue
            if session.scalar(select(Signal.signal_id).where(Signal.research_event_id == existing.research_event_id)):
                raise ValueError('Changed event has downstream signals; explicit invalidation required')
            counts['events_updated'] += 1
        else:
            counts['events_inserted'] += 1
        row['feature_metadata'] = {
            **row['feature_metadata'],
            'source_canonical_transaction_keys': sorted(keys_by_id[identity]
                                                       for identity in row['feature_metadata']['source_transaction_ids']),
        }
        statement = insert(ResearchEvent).values(**row)
        session.execute(statement.on_conflict_do_update(
            index_elements=['ticker', 'public_event_day'],
            set_={name: getattr(statement.excluded, name) for name in row if name not in {'research_event_id', 'ticker', 'public_event_day'}}))
    for row in dataset.transactions:
        if row['transaction_id'] not in accepted_sources:
            continue
        stored = session.get(InsiderTransaction, row['transaction_id'])
        if stored is None or stored.canonical_transaction_key != row['canonical_transaction_key']:
            raise ValueError('Underlying canonical transaction is absent or inconsistent')
        if stored.ticker is not None and stored.ticker != row['ticker']:
            raise ValueError('Refusing to overwrite a valid source ticker')
        if stored.ticker is None or stored.public_event_day != row['public_event_day']:
            session.execute(update(InsiderTransaction).where(InsiderTransaction.transaction_id == row['transaction_id'])
                            .values(ticker=row['ticker'], public_event_day=row['public_event_day']))
            counts['transactions_enriched'] += 1
    return counts


def build_from_database(session, universe, cache, start, end, tickers=None, write=True):
    """Rebuild complete groups; the filing-date output window is inclusive.

    All persisted transactions through end are considered, preventing partial
    weekend groups when start falls between source filings for the same event.
    """
    query = select(InsiderTransaction).where(InsiderTransaction.filing_date <= end)
    transactions = [model_dict(row) for row in session.scalars(query.order_by(InsiderTransaction.transaction_id))]
    if tickers:
        allowed = set(tickers)
        transactions = [row for row in transactions
                        if universe.resolve_issuer(row['cik'], row['ticker']).ticker in allowed]
    prices = [model_dict(row) for row in session.scalars(select(Price).order_by(Price.ticker, Price.date))]
    evidence, issues = cached_buyers(cache, transactions)
    dataset = build_dataset(transactions, prices, universe, evidence)
    dataset.events[:] = [row for row in dataset.events if start <= row['information_date'] <= end]
    selected = {identity for event in dataset.events for identity in event['feature_metadata']['source_transaction_ids']}
    dataset.transactions[:] = [row for row in dataset.transactions if row['transaction_id'] in selected]
    dataset.issues.extend(issues)
    counts = persist_dataset(session, dataset, universe) if write else {}
    return dataset, counts
