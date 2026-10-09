"""Lazy pooled database access and canonical frozen-universe request validation."""
from functools import lru_cache

from fastapi import HTTPException, Request

from app.db.session import Database
from app.services.universe import Universe


@lru_cache(maxsize=1)
def get_universe():
    return Universe.from_csv()


def known_company(ticker: str):
    company = get_universe().ticker_to_company(ticker)
    if company is None:
        raise HTTPException(status_code=404, detail='Unknown ticker')
    return company


def get_session(request: Request):
    try:
        with request.app.state.database_lock:
            if request.app.state.database is None:
                request.app.state.database = Database()
            database = request.app.state.database
        with database.session() as session:
            yield session
    except HTTPException:
        raise
    except Exception:
        # Never log raw environment, driver, validation or service exceptions.
        raise HTTPException(status_code=503, detail='Research data unavailable') from None
