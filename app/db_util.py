"""Reliable DB connections on Windows (direct Neon; pool breaks under uvicorn reload)."""

from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from .db import get_pool
from .settings import DATABASE_URL

_WIN32 = sys.platform == "win32"


@asynccontextmanager
async def db_connection(timeout: float = 12.0) -> AsyncIterator[Any]:
    """Yield a psycopg async connection. On Windows always connect directly to Neon."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    if not _WIN32:
        pool = get_pool()
        if pool is not None:
            try:
                async with asyncio.timeout(timeout):
                    async with pool.connection() as conn:
                        yield conn
                        return
            except Exception:
                pass
    import psycopg

    async with await psycopg.AsyncConnection.connect(
        DATABASE_URL, connect_timeout=int(timeout)
    ) as conn:
        yield conn
