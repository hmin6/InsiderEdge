"""Issue #3 PostgreSQL correction: replace only CIK uniqueness with a normal index."""
from sqlalchemy import Index, MetaData, Table, UniqueConstraint
from sqlalchemy.schema import DropConstraint, DropIndex

from app.db.session import Database


def migrate(connection):
    if connection.dialect.name != 'postgresql':
        raise ValueError('This migration requires PostgreSQL')
    table = Table('companies', MetaData(), autoload_with=connection)
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint) and list(constraint.columns.keys()) == ['cik']:
            connection.execute(DropConstraint(constraint))
    for index in table.indexes:
        if index.unique and list(index.columns.keys()) == ['cik']:
            connection.execute(DropIndex(index, if_exists=True))
    Index('ix_companies_cik', table.c.cik).create(connection, checkfirst=True)


def main():
    database = None
    try:
        database = Database()
        with database.engine.begin() as connection:
            migrate(connection)
    except Exception:
        raise SystemExit('Company CIK migration failed; verify database configuration and schema.') from None
    finally:
        if database is not None:
            database.close()


if __name__ == '__main__':
    main()
