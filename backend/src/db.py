from __future__ import annotations

import asyncio

import asyncpg

from src.config import settings
from src.observability.logging import get_logger

log = get_logger("db")

_shared_pool: asyncpg.Pool | None = None
_pool_lock: asyncio.Lock | None = None


def _get_pool_lock() -> asyncio.Lock:
    global _pool_lock
    if _pool_lock is None:
        _pool_lock = asyncio.Lock()
    return _pool_lock


async def get_postgres_pool(
    dsn: str | None = None,
    *,
    min_size: int = 2,
    max_size: int = 10,
) -> asyncpg.Pool:
    global _shared_pool

    dsn = dsn or settings.postgres_url
    use_shared_pool = dsn == settings.postgres_url

    if not use_shared_pool:
        return await asyncpg.create_pool(dsn, min_size=min_size, max_size=max_size)

    if _shared_pool is not None:
        return _shared_pool

    async with _get_pool_lock():
        if _shared_pool is None:
            _shared_pool = await asyncpg.create_pool(dsn, min_size=min_size, max_size=max_size)
            log.info("postgres_pool_initialized")

    return _shared_pool


async def close_postgres_pool() -> None:
    global _shared_pool

    if _shared_pool is None:
        return

    async with _get_pool_lock():
        if _shared_pool is not None:
            await _shared_pool.close()
            _shared_pool = None
            log.info("postgres_pool_closed")
