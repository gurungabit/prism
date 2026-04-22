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
    duration_seconds FLOAT,
    -- Threading: a thread is a chain of runs. thread_id is the root run's
    -- analysis_id (same value for every run in the chain). parent_analysis_id
    -- points at the immediately prior run.
    thread_id TEXT,
    parent_analysis_id TEXT,
    -- 'full' = ran the whole pipeline; 'chat' = lightweight follow-up answered
    -- from prior context only.
    kind TEXT NOT NULL DEFAULT 'full',
    -- One-paragraph memo written after the run completes. Follow-ups feed
    -- stale turns' rolling_summary back into context instead of the full
    -- report, so thread context stays bounded.
    rolling_summary TEXT NOT NULL DEFAULT ''
);

-- Self-healing for databases that existed before the threading columns.
ALTER TABLE analyses ADD COLUMN IF NOT EXISTS thread_id TEXT;
ALTER TABLE analyses ADD COLUMN IF NOT EXISTS parent_analysis_id TEXT;
ALTER TABLE analyses ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'full';
ALTER TABLE analyses ADD COLUMN IF NOT EXISTS rolling_summary TEXT NOT NULL DEFAULT '';
-- Back-fill thread_id for rows written before threading landed: each
-- pre-existing run is its own thread root.
UPDATE analyses SET thread_id = analysis_id WHERE thread_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_analyses_created_at ON analyses(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analyses_status ON analyses(status);
CREATE INDEX IF NOT EXISTS idx_analyses_thread_id ON analyses(thread_id);
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

    async def insert(
        self,
        analysis_id: str,
        requirement: str,
        *,
        thread_id: str | None = None,
        parent_analysis_id: str | None = None,
        kind: str = "full",
    ) -> None:
        # thread_id defaults to the run's own id -- each new root starts its
        # own thread. Follow-ups pass thread_id (usually inherited from the
        # parent's row) plus parent_analysis_id.
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO analyses (
                    analysis_id, requirement, status, created_at,
                    thread_id, parent_analysis_id, kind
                )
                VALUES ($1, $2, 'running', NOW(), $3, $4, $5)
                ON CONFLICT (analysis_id) DO NOTHING
                """,
                analysis_id,
                requirement,
                thread_id or analysis_id,
                parent_analysis_id,
                kind,
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

    async def update_rolling_summary(self, analysis_id: str, summary: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE analyses SET rolling_summary = $2 WHERE analysis_id = $1",
                analysis_id,
                summary,
            )

    async def list_thread(self, thread_id: str) -> list[dict]:
        """Return every run in a thread, oldest first."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT analysis_id, requirement, status, created_at, duration_seconds,
                       thread_id, parent_analysis_id, kind, rolling_summary, report
                FROM analyses
                WHERE thread_id = $1
                ORDER BY created_at ASC
                """,
                thread_id,
            )
            return [dict(r) for r in rows]

    async def list_threads(self, limit: int = 20, offset: int = 0) -> list[dict]:
        """One row per thread: the root requirement + turn count."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH thread_stats AS (
                    SELECT
                        thread_id,
                        COUNT(*) AS turn_count,
                        MIN(created_at) AS started_at,
                        MAX(created_at) AS last_turn_at
                    FROM analyses
                    GROUP BY thread_id
                )
                SELECT
                    ts.thread_id,
                    ts.turn_count,
                    ts.started_at,
                    ts.last_turn_at,
                    root.requirement,
                    root.status,
                    root.duration_seconds
                FROM thread_stats ts
                JOIN analyses root ON root.analysis_id = ts.thread_id
                ORDER BY ts.last_turn_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )
            return [dict(r) for r in rows]

    async def count_threads(self) -> int:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT COUNT(DISTINCT thread_id) FROM analyses"
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
