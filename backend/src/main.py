from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.agents.orchestrator import shutdown_compiled_app
from src.api.catalog_routes import router as catalog_router
from src.api.routes import router
from src.catalog import SourceRepository
from src.config import settings
from src.db import close_postgres_pool
from src.ingestion.indexer import close_opensearch_client
from src.observability.logging import get_logger, setup_logging

log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    try:
        source_repo = await SourceRepository.create()
        try:
            reset = await source_repo.reset_orphaned_syncing()
            if reset:
                log.info("orphaned_syncing_reset", count=reset)
        finally:
            await source_repo.close()
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

# CORS: parsed from ``settings.cors_origins`` (env: ``PRISM_CORS_ORIGINS``).
# Default is the local Vite dev hosts so a fresh checkout works without
# extra config. The previous ``allow_origins=["*"]`` + credentials combo
# was unsafe even pre-auth -- the wildcard would silently inherit into
# any future cookie/token browser flow. Per the CORS spec, credentials
# may only be enabled when origins are *not* the ``*`` sentinel; we
# downgrade ``allow_credentials`` to False in that branch so the
# middleware doesn't reject the response. ``PRISM_CORS_ORIGINS=*`` is
# kept as an explicit local-experiment escape hatch.
_origins = settings.cors_origin_list
_wildcard = _origins == ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False if _wildcard else True,
    allow_methods=["*"],
    allow_headers=["*"],
)
log.info(
    "cors_configured",
    origins=_origins,
    credentials=False if _wildcard else True,
)

app.include_router(router)
app.include_router(catalog_router)


def run():
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
