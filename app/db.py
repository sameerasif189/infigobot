"""Async Postgres access (Neon). On Windows uses direct connections (no psycopg pool)."""

from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator, Optional, Union

from .settings import DATABASE_URL, IS_SERVERLESS

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

if TYPE_CHECKING:
    from psycopg_pool import AsyncConnectionPool

_pool: Optional[Union["AsyncConnectionPool", "DirectConnectionPool"]] = None
_WIN32 = sys.platform == "win32"


class DirectConnectionPool:
    """Pool-compatible wrapper: one fresh Neon connection per `connection()` (Windows-safe)."""

    @asynccontextmanager
    async def connection(self, timeout: float | None = None) -> AsyncIterator[Any]:
        import psycopg

        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not set")
        wait = int(timeout or 12)
        async with await psycopg.AsyncConnection.connect(
            DATABASE_URL, connect_timeout=wait
        ) as conn:
            yield conn

    async def close(self) -> None:
        return None


async def init_db_pool() -> None:
    global _pool
    if not DATABASE_URL:
        return
    if _WIN32 or IS_SERVERLESS:
        _pool = DirectConnectionPool()
        return
    from psycopg_pool import AsyncConnectionPool

    _pool = AsyncConnectionPool(
        conninfo=DATABASE_URL,
        min_size=1,
        max_size=10,
        timeout=10.0,
        max_waiting=20,
        kwargs={"connect_timeout": 10},
        open=False,
    )
    await _pool.open(wait=True, timeout=15.0)


async def close_db_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> Optional[Union["AsyncConnectionPool", DirectConnectionPool]]:
    return _pool


def database_ready() -> bool:
    return bool(DATABASE_URL and _pool is not None)
