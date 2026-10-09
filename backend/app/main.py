from fastapi import FastAPI

from app.api.health import router

app = FastAPI(title='InsiderEdge')
app.include_router(router)
