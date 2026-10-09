"""Approved Issue #5 correction for existing PostgreSQL databases."""
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import inspect, text

from app.db.session import Database


def migrate(engine):
    if engine.dialect.name != 'postgresql':
        raise ValueError('This migration requires PostgreSQL')
    with engine.begin() as connection:
        columns = {column['name']: column for column in inspect(connection).get_columns('research_events')}
        if 'unique_buyer_count' not in columns:
            raise ValueError('Initialize the foundation schema first')
        if not columns['unique_buyer_count']['nullable']:
            connection.execute(text('ALTER TABLE research_events ALTER COLUMN unique_buyer_count DROP NOT NULL'))


def main():
    load_dotenv(Path(__file__).resolve().parents[2] / '.env', override=False)
    database = None
    try:
        database = Database()
        migrate(database.engine)
        print('Buyer-count nullable migration succeeded (or already applied).')
    except Exception:
        raise SystemExit('Buyer-count migration failed; check configuration and existing schema.') from None
    finally:
        if database is not None:
            database.close()


if __name__ == '__main__':
    main()
