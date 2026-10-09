"""Parameterized daily-price writes and offline reads."""
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.models import Price
from app.services.universe import normalize_ticker

VALUE_COLUMNS = ('open', 'high', 'low', 'close', 'adjusted_close', 'analysis_price', 'volume')


def persist_prices(session, rows: list[dict]) -> int:
    dialect = session.get_bind().dialect.name
    if dialect not in {'postgresql', 'sqlite'}:
        raise ValueError('Unsupported market persistence dialect')
    insert = postgres_insert if dialect == 'postgresql' else sqlite_insert
    for offset in range(0, len(rows), 100):
        statement = insert(Price).values(rows[offset:offset + 100])
        statement = statement.on_conflict_do_update(
            index_elements=['ticker', 'date'],
            set_={name: getattr(statement.excluded, name) for name in VALUE_COLUMNS},
        )
        session.execute(statement)
    return len(rows)


def read_prices(session, ticker, start=None, end=None) -> list[dict]:
    """Query persisted data without contacting a provider; end is exclusive."""
    query = select(Price).where(Price.ticker == normalize_ticker(ticker))
    if start is not None:
        query = query.where(Price.date >= start)
    if end is not None:
        query = query.where(Price.date < end)
    return [{column.name: getattr(row, column.name) for column in Price.__table__.columns}
            for row in session.scalars(query.order_by(Price.date))]
