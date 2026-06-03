"""OpenAI-compatible embedding API for vector RAG."""

from __future__ import annotations

import logging
from typing import List, Optional

import httpx

from .settings import (
    EMBEDDING_API_BASE,
    EMBEDDING_API_KEY,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    EMBEDDING_TIMEOUT_SEC,
    LLM_API_BASE,
    LLM_API_KEY,
)

logger = logging.getLogger(__name__)

_BATCH = 64


def embeddings_configured() -> bool:
    key = (EMBEDDING_API_KEY or "").strip()
    if key and key != "replace-me":
        return True
    llm_key = (LLM_API_KEY or "").strip()
    if not llm_key or llm_key == "replace-me":
        return False
    same_host = EMBEDDING_API_BASE.rstrip("/") == LLM_API_BASE.rstrip("/")
    return same_host


def _api_key() -> str:
    key = (EMBEDDING_API_KEY or "").strip()
    if not key or key == "replace-me":
        if embeddings_configured():
            key = (LLM_API_KEY or "").strip()
    if not key or key == "replace-me":
        raise RuntimeError(
            "Set EMBEDDING_API_KEY (OpenAI text-embedding-3-small) for vector RAG on Neon. "
            "Groq keys only work for chat, not embeddings."
        )
    return key


async def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed a list of strings; returns vectors of length EMBEDDING_DIM."""
    if not texts:
        return []
    if not embeddings_configured():
        raise RuntimeError("Embeddings API key not configured")

    out: List[List[float]] = []
    batch_size = min(EMBEDDING_BATCH_SIZE, _BATCH)
    timeout = httpx.Timeout(EMBEDDING_TIMEOUT_SEC, connect=min(15.0, EMBEDDING_TIMEOUT_SEC))
    headers = {"Authorization": f"Bearer {_api_key()}"}
    base = EMBEDDING_API_BASE.rstrip("/")

    async with httpx.AsyncClient(timeout=timeout) as client:
        for i in range(0, len(texts), batch_size):
            batch = [t[:8000] for t in texts[i : i + batch_size]]
            payload = {"model": EMBEDDING_MODEL, "input": batch}
            if EMBEDDING_DIM == 512 and "text-embedding-3" in EMBEDDING_MODEL:
                payload["dimensions"] = 512

            resp = await client.post(f"{base}/embeddings", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            items = sorted(data.get("data") or [], key=lambda x: x.get("index", 0))
            for item in items:
                vec = item.get("embedding")
                if not isinstance(vec, list):
                    raise ValueError("Invalid embedding response")
                if len(vec) != EMBEDDING_DIM:
                    raise ValueError(
                        f"Expected {EMBEDDING_DIM}-dim vectors, got {len(vec)} "
                        f"(check EMBEDDING_MODEL / EMBEDDING_DIM)"
                    )
                out.append([float(x) for x in vec])
    return out


async def embed_query(text: str) -> List[float]:
    vecs = await embed_texts([text.strip() or " "])
    return vecs[0]


def vector_to_pg(vec: List[float]) -> str:
    """Literal for Postgres ::vector cast."""
    return "[" + ",".join(f"{x:.8f}" for x in vec) + "]"
