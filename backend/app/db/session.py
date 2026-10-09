"""Lazy PostgreSQL configuration; importing the app never opens a connection."""
import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker


class Database:
    def __init__(self) -> None:
        try:
            url = make_url(os.environ['DATABASE_URL'])
            if url.drivername not in {'postgres', 'postgresql', 'postgresql+psycopg'}:
                raise ValueError
            url = url.set(drivername='postgresql+psycopg')
        except Exception:
            # Do not include the supplied URL or original parser error.
            raise ValueError('DATABASE_URL must be a valid PostgreSQL URL') from None
        self.engine = create_engine(url, pool_pre_ping=True, echo=False, hide_parameters=True)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)

    @contextmanager
    def session(self):
        """Commit successful units of work; roll back errors and always close."""
        with self.sessions() as session:
            with session.begin():
                yield session

    def close(self) -> None:
        self.engine.dispose()
