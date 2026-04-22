from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.agents.orchestrator import shutdown_compiled_app
from src.api.catalog_routes import router as catalog_router
from src.api.routes import router
from src.db import close_postgres_pool
from src.ingestion.indexer import close_opensearch_client
from src.observability.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    try:
        yield
    finally:
        await shutdown_compiled_app()
        await close_postgres_pool()
        close_opensearch_client()


app = FastAPI(
    title="PRISM API",
    description="Platform-aware Requirement Intelligence and Service Mapping",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(catalog_router)


def run():
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
