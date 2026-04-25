"""Per-document idempotency + content-hash tracking.

Each declared source feeds documents through the registry. The registry
uniqueness key is composite ``(source_id, source_path)`` so two sources
can each have their own ``README.md`` without colliding. Within a source
the content hash decides update-vs-skip:

- same path + same hash  -> skip (already indexed, content unchanged)
- same path + new hash   -> delete old chunks, re-index, update row
- new path               -> insert + index
- old path missing on
  the upstream listing    -> tombstone (delete row + chunks)

Schema lives in ``src.catalog.schema.REGISTRY_SCHEMA_SQL`` and is created
by ``CatalogRepo._init_schema``. The helper here reuses that bootstrap so
``DocumentRegistry.create()`` remains a one-call initializer.
"""

from __future__ import annotations

import asyncio
import hashlib
from uuid import UUID

import asyncpg

from src.config import settings
from src.db import get_postgres_pool
from src.observability.logging import get_logger

log = get_logger("registry")


class DocumentRegistry:
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
    async def create(cls, dsn: str | None = None) -> DocumentRegistry:
        dsn = dsn or settings.postgres_url
        owns_pool = dsn != settings.postgres_url
        pool = await get_postgres_pool(dsn)
        registry = cls(pool, owns_pool=owns_pool, dsn=dsn)
        await registry._ensure_catalog_schema()
        return registry

    async def _ensure_catalog_schema(self) -> None:
        if self.dsn in self._initialized_dsns:
            return

        async with self._get_schema_lock():
            if self.dsn in self._initialized_dsns:
                return

            from src.catalog.base_repo import CatalogRepo  # noqa: WPS433

            repo = CatalogRepo(self.pool, owns_pool=False, dsn=self.dsn)
            await repo._init_schema()

            self._initialized_dsns.add(self.dsn)
            log.info("registry_catalog_ready")

    async def get_by_path(
        self, source_path: str, *, source_id: UUID | None = None
    ) -> dict | None:
        # ``source_id`` is the proper lookup key (composite UNIQUE on
        # ``(source_id, source_path)``). The legacy global lookup is kept
        # for callers that never carried a source context, but new code
        # should always pass it.
        async with self.pool.acquire() as conn:
            if source_id is not None:
                row = await conn.fetchrow(
                    """
                    SELECT * FROM document_registry
                    WHERE source_id = $1 AND source_path = $2
                    """,
                    source_id,
                    source_path,
                )
            else:
                row = await conn.fetchrow(
                    "SELECT * FROM document_registry WHERE source_path = $1",
                    source_path,
                )
            return dict(row) if row else None

    async def upsert(
        self,
        document_id: str,
        source_platform: str,
        source_path: str,
        content_hash: str,
        chunk_count: int,
        status: str = "indexed",
        *,
        source_id: UUID | None = None,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO document_registry (
                    document_id, source_platform, source_path,
                    content_hash, chunk_count, status, last_ingested_at, source_id
                )
                VALUES ($1, $2, $3, $4, $5, $6, NOW(), $7)
                ON CONFLICT (source_id, source_path) DO UPDATE SET
                    document_id = $1,
                    content_hash = $4,
                    chunk_count = $5,
                    status = $6,
                    last_ingested_at = NOW()
                """,
                document_id,
                source_platform,
                source_path,
                content_hash,
                chunk_count,
                status,
                source_id,
            )

    async def mark_status(
        self, source_path: str, status: str, *, source_id: UUID | None = None
    ) -> None:
        async with self.pool.acquire() as conn:
            if source_id is not None:
                await conn.execute(
                    """
                    UPDATE document_registry
                    SET status = $1
                    WHERE source_id = $2 AND source_path = $3
                    """,
                    status,
                    source_id,
                    source_path,
                )
            else:
                await conn.execute(
                    "UPDATE document_registry SET status = $1 WHERE source_path = $2",
                    status,
                    source_path,
                )

    async def delete_by_paths(
        self, source_id: UUID, paths: list[str]
    ) -> list[str]:
        """Tombstone rows for paths no longer present upstream.

        Returns the ``document_id``s that were removed so the caller can
        clean up the matching OpenSearch chunks.
        """
        if not paths:
            return []
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                DELETE FROM document_registry
                WHERE source_id = $1 AND source_path = ANY($2::text[])
                RETURNING document_id
                """,
                source_id,
                paths,
            )
            return [r["document_id"] for r in rows]

    async def get_all(self) -> list[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM document_registry ORDER BY last_ingested_at DESC"
            )
            return [dict(r) for r in rows]

    async def get_for_source(self, source_id: UUID) -> list[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM document_registry
                WHERE source_id = $1
                ORDER BY last_ingested_at DESC
                """,
                source_id,
            )
            return [dict(r) for r in rows]

    async def close(self) -> None:
        if self.owns_pool:
            await self.pool.close()


def compute_content_hash(content: bytes | str) -> str:
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()
