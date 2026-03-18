"""Shared arq Redis pool for enqueueing background jobs."""

from __future__ import annotations

import logging

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

logger = logging.getLogger(__name__)

_pool: ArqRedis | None = None


async def connect(redis_url: str) -> None:
    """Create the Redis pool. Called once during app startup."""
    global _pool
    _pool = await create_pool(RedisSettings.from_dsn(redis_url))
    logger.info("Redis pool connected: %s", redis_url)


async def close() -> None:
    """Close the Redis pool. Called during app shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("Redis pool closed")


def get_pool() -> ArqRedis:
    """Return the active pool. Raises if connect() was not called."""
    if _pool is None:
        raise RuntimeError("Redis pool not initialized — call queue.connect() first")
    return _pool
