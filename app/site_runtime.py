"""Fetch public website content at chat time (no JSON file required)."""

from __future__ import annotations

import logging
import time
from typing import Dict, Tuple

from .ingest import fetch_api_feed

logger = logging.getLogger(__name__)

_CACHE: Dict[str, Tuple[str, float]] = {}
_CACHE_TTL_SEC = 1800


async def fetch_runtime_site(url: str) -> str:
    """HTTP GET → strip HTML or parse JSON URL. Cached per server instance ~30 min."""
    u = (url or "").strip()
    if not u:
        return ""
    now = time.time()
    cached = _CACHE.get(u)
    if cached and (now - cached[1]) < _CACHE_TTL_SEC:
        return cached[0]
    try:
        text = await fetch_api_feed(u)
        snippet = (text or "").strip()[:12_000]
        _CACHE[u] = (snippet, now)
        return snippet
    except Exception as exc:
        logger.warning("Runtime site fetch failed %s: %s", u, exc)
        return ""
