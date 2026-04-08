from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime

import asyncpg

from src.config import settings
from src.db import get_postgres_pool
from src.observability.logging import get_logger

log = get_logger("registry")

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS document_registry (
    document_id TEXT PRIMARY KEY,
    source_platform TEXT NOT NULL,
    source_path TEXT NOT NULL UNIQUE,
    content_hash TEXT NOT NULL,
    last_ingested_at TIMESTAMPTZ DEFAULT NOW(),
    chunk_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending'
);

CREATE INDEX IF NOT EXISTS idx_registry_source_path ON document_registry(source_path);
CREATE INDEX IF NOT EXISTS idx_registry_status ON document_registry(status);
"""


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
        await registry._init_schema()
        return registry

    async def _init_schema(self) -> None:
        if self.dsn in self._initialized_dsns:
            return

        async with self._get_schema_lock():
            if self.dsn in self._initialized_dsns:
                return

            async with self.pool.acquire() as conn:
                await conn.execute(CREATE_TABLE_SQL)

            self._initialized_dsns.add(self.dsn)
            log.info("registry_schema_initialized")

    async def get_by_path(self, source_path: str) -> dict | None:
        async with self.pool.acquire() as conn:
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
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO document_registry (document_id, source_platform, source_path, content_hash, chunk_count, status, last_ingested_at)
                VALUES ($1, $2, $3, $4, $5, $6, NOW())
                ON CONFLICT (source_path) DO UPDATE SET
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
            )

    async def mark_status(self, source_path: str, status: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE document_registry SET status = $1 WHERE source_path = $2",
                status,
                source_path,
            )

    async def get_all(self) -> list[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM document_registry ORDER BY last_ingested_at DESC")
            return [dict(r) for r in rows]

    async def close(self) -> None:
        if self.owns_pool:
            await self.pool.close()


def compute_content_hash(content: bytes | str) -> str:
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()
