"""Run from backend: python -m scripts.init_db."""
from app.db.models import Base
from app.db.session import Database


def main() -> None:
    database = None
    try:
        database = Database()
        Base.metadata.create_all(database.engine)
    except Exception:
        # Driver exceptions can contain connection details. Keep CLI output safe.
        raise SystemExit('Database initialization failed; verify configuration and connectivity.') from None
    finally:
        if database is not None:
            database.close()


if __name__ == '__main__':
    main()
