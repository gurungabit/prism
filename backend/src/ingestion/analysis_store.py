from __future__ import annotations

import asyncio
import json

import asyncpg

from src.config import settings
from src.db import get_postgres_pool
from src.observability.logging import get_logger

log = get_logger("analysis_store")

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS analyses (
    analysis_id TEXT PRIMARY KEY,
    requirement TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    report JSONB,
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    duration_seconds FLOAT
);

CREATE INDEX IF NOT EXISTS idx_analyses_created_at ON analyses(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analyses_status ON analyses(status);
"""


class AnalysisRepository:
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
    async def create(cls, dsn: str | None = None) -> AnalysisRepository:
        dsn = dsn or settings.postgres_url
        owns_pool = dsn != settings.postgres_url
        pool = await get_postgres_pool(dsn)
        repo = cls(pool, owns_pool=owns_pool, dsn=dsn)
        await repo._init_schema()
        return repo

    async def _init_schema(self) -> None:
        if self.dsn in self._initialized_dsns:
            return

        async with self._get_schema_lock():
            if self.dsn in self._initialized_dsns:
                return

            async with self.pool.acquire() as conn:
                await conn.execute(CREATE_TABLE_SQL)

            self._initialized_dsns.add(self.dsn)
            log.info("analysis_schema_initialized")

    async def insert(self, analysis_id: str, requirement: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO analyses (analysis_id, requirement, status, created_at)
                VALUES ($1, $2, 'running', NOW())
                ON CONFLICT (analysis_id) DO NOTHING
                """,
                analysis_id,
                requirement,
            )

    async def update_complete(self, analysis_id: str, report_dict: dict, duration: float) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE analyses
                SET status = 'complete', report = $2::jsonb, duration_seconds = $3
                WHERE analysis_id = $1
                """,
                analysis_id,
                json.dumps(report_dict, default=str),
                duration,
            )

    async def update_failed(self, analysis_id: str, error: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE analyses
                SET status = 'failed', error = $2
                WHERE analysis_id = $1
                """,
                analysis_id,
                error,
            )

    async def get(self, analysis_id: str) -> dict | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM analyses WHERE analysis_id = $1",
                analysis_id,
            )
            return dict(row) if row else None

    async def list_recent(self, limit: int = 20, offset: int = 0) -> list[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT analysis_id, requirement, status, created_at, duration_seconds
                FROM analyses
                ORDER BY created_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )
            return [dict(r) for r in rows]

    async def delete(self, analysis_id: str) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM analyses WHERE analysis_id = $1",
                analysis_id,
            )
            return result == "DELETE 1"

    async def count(self) -> int:
        async with self.pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM analyses")

    async def close(self) -> None:
        if self.owns_pool:
            await self.pool.close()
