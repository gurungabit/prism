"""Shared schema bootstrap for every catalog repository.

All four repos (``OrgRepository``, ``TeamRepository``, ``ServiceRepository``,
``SourceRepository``) inherit from ``CatalogRepo`` so they share one schema
initialization + migration path. Only the first ``.create()`` call against a
given DSN actually runs the DDL; subsequent callers get the cached flag.
"""

from __future__ import annotations

import asyncio

import asyncpg

from src.catalog.schema import (
    CATALOG_SCHEMA_SQL,
    DOCUMENT_SCHEMA_SQL,
    LEGACY_DETECTION_SQL,
    LEGACY_DOCUMENTS_RESET_SQL,
    LEGACY_DROP_SQL,
    PENDING_DEPENDENCIES_SQL,
    REGISTRY_SCHEMA_SQL,
)
from src.config import settings
from src.db import get_postgres_pool
from src.observability.logging import get_logger

log = get_logger("catalog")


class CatalogRepo:
    """Base class that owns the catalog schema lifecycle.

    Subclasses just need DAO methods; they get ``.pool``, ``.dsn``, and the
    ``.create()`` factory from here. Schema initialization is idempotent and
    cached per-DSN with an asyncio lock, matching the pattern in
    ``KnowledgeStore`` and ``DocumentRegistry``.
    """

    _schema_lock: asyncio.Lock | None = None
    _initialized_dsns: set[str] = set()

    def __init__(self, pool: asyncpg.Pool, *, owns_pool: bool = False, dsn: str | None = None) -> None:
        self.pool = pool
        self.owns_pool = owns_pool
        self.dsn = dsn or settings.postgres_url

    @classmethod
    def _get_schema_lock(cls) -> asyncio.Lock:
        if CatalogRepo._schema_lock is None:
            CatalogRepo._schema_lock = asyncio.Lock()
        return CatalogRepo._schema_lock

    @classmethod
    async def create(cls, dsn: str | None = None):  # type: ignore[no-untyped-def]
        dsn = dsn or settings.postgres_url
        owns_pool = dsn != settings.postgres_url
        pool = await get_postgres_pool(dsn)
        instance = cls(pool, owns_pool=owns_pool, dsn=dsn)
        await instance._init_schema()
        return instance

    async def _init_schema(self) -> None:
        if self.dsn in CatalogRepo._initialized_dsns:
            return

        async with self._get_schema_lock():
            if self.dsn in CatalogRepo._initialized_dsns:
                return

            async with self.pool.acquire() as conn:
                # Check which migration we need.
                # - has_legacy_tables: the inferred-ownership tables still exist
                # - kg_documents_has_scope: kg_documents has the new scope columns
                # - kg_dependencies_has_uuid: kg_dependencies uses UUID service FKs
                row = await conn.fetchrow(LEGACY_DETECTION_SQL)
                needs_legacy_drop = bool(row and row["has_legacy_tables"])
                needs_docs_reset = bool(
                    row
                    and (
                        not row["kg_documents_has_scope"]
                        or not row["kg_dependencies_has_uuid"]
                    )
                    and needs_legacy_drop  # only force a docs reset during a real migration
                )

                # 1. Create catalog tables first. kg_documents and
                #    kg_dependencies reference ``services`` by FK, so catalog
                #    tables must exist before we (re-)create them.
                await conn.execute(CATALOG_SCHEMA_SQL)

                # 2. Migrate: drop legacy ownership tables + reset doc tables
                #    whose schema has changed. These DROPs cascade through any
                #    stray FKs from the old schema.
                if needs_legacy_drop:
                    log.info("catalog_migration_dropping_legacy_tables")
                    await conn.execute(LEGACY_DROP_SQL)

                if needs_docs_reset:
                    log.info("catalog_migration_resetting_document_tables")
                    await conn.execute(LEGACY_DOCUMENTS_RESET_SQL)

                # 3. Create the fresh document / dependency / registry tables
                #    with the new scope-aware columns.
                await conn.execute(DOCUMENT_SCHEMA_SQL)
                await conn.execute(REGISTRY_SCHEMA_SQL)
                await conn.execute(PENDING_DEPENDENCIES_SQL)

            CatalogRepo._initialized_dsns.add(self.dsn)
            log.info("catalog_schema_initialized")

    async def close(self) -> None:
        if self.owns_pool:
            await self.pool.close()
