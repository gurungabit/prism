"""Document writer that honors the declared catalog.

Historically this module also owned the "who-owns-what" graph inferred
from document text. That role has moved to the declarative catalog
(see ``src.catalog``). What remains: writing ``kg_documents`` rows
(title/path/platform/scope pointers) each time the pipeline finishes a
document. Service-to-service dependencies are user-managed via the
catalog API, not extracted from doc text.

Team/service catalog tables and their schema bootstrap live in
``src.catalog.base_repo`` now. This class assumes the catalog schema has
already initialized (always true in practice because every entry point -- API
routes, ingestion pipeline -- opens a catalog repo before touching docs).
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import asyncpg

from src.config import settings
from src.db import get_postgres_pool
from src.models.document import RawDocument
from src.observability.logging import get_logger

log = get_logger("knowledge_store")


class KnowledgeStore:
    # Schema lock is retained for symmetry with the old contract, but all the
    # DDL that mattered has moved to ``CatalogRepo``. Left here to keep the
    # ``KnowledgeStore.create(dsn=...)`` factory signature stable.
    _schema_lock: asyncio.Lock | None = None
    _initialized_dsns: set[str] = set()

    def __init__(self, pool: asyncpg.Pool, *, owns_pool: bool = False, dsn: str | None = None) -> None:
        self.pool = pool
        self.owns_pool = owns_pool
        self.dsn = dsn or settings.postgres_url

    @classmethod
    def _get_schema_lock(cls) -> asyncio.Lock:
        if cls._schema_lock is None:
            cls._schema_lock = asyncio.Lock()
        return cls._schema_lock

    @classmethod
    async def create(cls, dsn: str | None = None) -> KnowledgeStore:
        dsn = dsn or settings.postgres_url
        owns_pool = dsn != settings.postgres_url
        pool = await get_postgres_pool(dsn)
        store = cls(pool, owns_pool=owns_pool, dsn=dsn)
        await store._ensure_catalog_schema()
        return store

    async def _ensure_catalog_schema(self) -> None:
        """Run the catalog bootstrap once per DSN.

        Importing here avoids a circular import (``catalog.base_repo`` imports
        ``src.db``, which is fine; but some callers import ``KnowledgeStore``
        before the catalog tables exist). Calling ``CatalogRepo.create`` is
        idempotent.
        """
        if self.dsn in self._initialized_dsns:
            return

        async with self._get_schema_lock():
            if self.dsn in self._initialized_dsns:
                return

            from src.catalog.base_repo import CatalogRepo  # noqa: WPS433

            # Bootstrap via a throwaway repo instance. Its constructor does
            # not care which subclass it is; ``_init_schema`` is defined on
            # the base.
            repo = CatalogRepo(self.pool, owns_pool=False, dsn=self.dsn)
            await repo._init_schema()

            self._initialized_dsns.add(self.dsn)
            log.info("knowledge_store_catalog_ready")

    # ----- kg_documents -----

    async def add_document(
        self,
        document_id: str,
        doc: RawDocument,
        *,
        source_id: UUID | None = None,
        org_id: UUID | None = None,
        team_id: UUID | None = None,
        service_id: UUID | None = None,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO kg_documents (
                    id, title, path, platform, last_modified, author,
                    source_url, source_id, org_id, team_id, service_id
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    path = EXCLUDED.path,
                    platform = EXCLUDED.platform,
                    last_modified = EXCLUDED.last_modified,
                    author = EXCLUDED.author,
                    source_url = EXCLUDED.source_url,
                    source_id = EXCLUDED.source_id,
                    org_id = EXCLUDED.org_id,
                    team_id = EXCLUDED.team_id,
                    service_id = EXCLUDED.service_id
                """,
                document_id,
                doc.metadata.title,
                doc.ref.source_path,
                doc.ref.source_platform,
                doc.metadata.last_modified,
                doc.metadata.author,
                doc.metadata.source_url or "",
                source_id,
                org_id,
                team_id,
                service_id,
            )

    # ----- kg_dependencies -----

    async def add_dependency(
        self,
        from_service_id: UUID,
        to_service_id: UUID,
        source_doc: str = "",
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO kg_dependencies (from_service_id, to_service_id, source, last_updated)
                VALUES ($1, $2, $3, now())
                ON CONFLICT (from_service_id, to_service_id) DO UPDATE SET
                    source = EXCLUDED.source,
                    last_updated = now()
                """,
                from_service_id,
                to_service_id,
                source_doc,
            )

    async def query_dependencies(self, service_id: UUID, depth: int = 2) -> list[dict]:
        """Deprecated wrapper -- prefer ``ServiceRepository.query_dependencies``.

        Kept here so any leftover ``KnowledgeStore`` callers in the agent layer
        continue to work while we migrate them.
        """
        from src.catalog import ServiceRepository  # noqa: WPS433

        repo = ServiceRepository(self.pool, owns_pool=False, dsn=self.dsn)
        return await repo.query_dependencies(service_id, depth)

    async def close(self) -> None:
        if self.owns_pool:
            await self.pool.close()
