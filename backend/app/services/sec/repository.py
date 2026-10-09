"""Persist normalized rows without creating companies or derived events."""
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.models import Company, InsiderTransaction
from .normalize import Report
from app.services.universe import CompanyMetadata, Universe


def persist(session, report: Report) -> dict[str, int]:
    companies = session.execute(select(Company.ticker, Company.cik)).all()
    mapping = Universe(CompanyMetadata(ticker, company_cik, ticker) for ticker, company_cik in companies)
    dialect = session.get_bind().dialect.name
    if dialect not in {'postgresql', 'sqlite'}:
        raise ValueError('Unsupported database dialect for SEC persistence')
    insert = postgres_insert if dialect == 'postgresql' else sqlite_insert
    counts = {'inserted': 0, 'duplicates': 0, 'unmapped': 0}
    for record in report.records:
        row = record.copy()
        resolution = mapping.resolve_issuer(row['cik'], row['ticker'])
        mapped = resolution.ticker
        if mapped is None:
            report.issue(row['accession_number'], 'ticker', f'{resolution.status}: {resolution.reason}; ticker stored as NULL')
            counts['unmapped'] += 1
        row['ticker'] = mapped
        statement = insert(InsiderTransaction).values(**row).on_conflict_do_nothing(
            index_elements=['canonical_transaction_key']).returning(InsiderTransaction.transaction_id)
        inserted = session.execute(statement).scalar_one_or_none()
        if inserted is not None:
            counts['inserted'] += 1
        else:
            counts['duplicates'] += 1
            # An overlapping EDGAR import can add acceptance time to a bulk row.
            for name in ('accepted_at', 'ticker'):
                if row[name] is not None:
                    session.execute(update(InsiderTransaction).where(
                        InsiderTransaction.canonical_transaction_key == row['canonical_transaction_key'],
                        getattr(InsiderTransaction, name).is_(None)).values({name: row[name]}))
    return counts
