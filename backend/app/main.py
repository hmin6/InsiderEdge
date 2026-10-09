from contextlib import asynccontextmanager
import os
from threading import Lock
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.api.health import router
from app.api.core import router as core_router


def cors_origins():
    origins = []
    for value in os.environ.get('CORS_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(','):
        value = value.strip()
        if not value:
            continue
        try:
            parsed = urlsplit(value)
            if (parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username
                    or parsed.password or parsed.path not in {'', '/'} or parsed.query or parsed.fragment
                    or '*' in value):
                raise ValueError
            parsed.port  # Validate the optional port without printing its value.
        except ValueError:
            raise ValueError('CORS_ORIGINS must contain explicit HTTP(S) origins') from None
        origins.append(f'{parsed.scheme}://{parsed.netloc.lower()}')
    return origins


@asynccontextmanager
async def lifespan(app):
    try:
        yield
    finally:
        if app.state.database is not None:
            app.state.database.close()
            app.state.database = None


def create_app():
    app = FastAPI(title='InsiderEdge', lifespan=lifespan)
    app.state.database = None
    app.state.database_lock = Lock()
    app.add_middleware(CORSMiddleware, allow_origins=cors_origins(), allow_credentials=False,
                       allow_methods=['GET'], allow_headers=['Accept'])

    async def unavailable(request, error):
        return JSONResponse(status_code=503, content={'detail': 'Research data unavailable'})
    app.add_exception_handler(SQLAlchemyError, unavailable)
    app.add_exception_handler(ValidationError, unavailable)
    app.include_router(router)
    app.include_router(core_router)
    return app


app = create_app()
