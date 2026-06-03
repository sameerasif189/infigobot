"""Optional runtime fetch of public website HTML (no database)."""

from __future__ import annotations

import logging
import time
from typing import Dict, Tuple

from .ingest import fetch_api_feed

logger = logging.getLogger(__name__)

_CACHE: Dict[str, Tuple[str, float]] = {}
_CACHE_TTL_SEC = 1800  # 30 min per serverless instance


async def fetch_site_text(url: str) -> str:
    """Fetch and strip a public URL; cached in-process for repeat chats on same instance."""
    u = url.strip()
    if not u:
        return ""
    now = time.time()
    hit = _CACHE.get(u)
    if hit and (now - hit[1]) < _CACHE_TTL_SEC:
        return hit[0]
    try:
        text = await fetch_api_feed(u)
        snippet = (text or "").strip()[:12_000]
        _CACHE[u] = (snippet, now)
        return snippet
    except Exception as exc:
        logger.warning("Site fetch failed for %s: %s", u, exc)
        return ""
