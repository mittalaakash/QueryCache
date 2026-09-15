"""FastAPI app factory: wires config, logging, DB schema, and routes together."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.db.connection import get_pool
from app.db.schema import init_schema
from app.observability.logging_config import configure_logging

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = get_pool()
    with pool.connection() as conn:
        init_schema(conn)
    app.state.db_pool = pool
    yield
    pool.close()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(router)
