"""Split documents into overlapping segments for embedding (~400 tokens each)."""

from __future__ import annotations

import re
from typing import List

from .settings import RAG_CHUNK_OVERLAP_TOKENS, RAG_CHUNK_SIZE_TOKENS

# Rough English: ~4 characters per token
_CHARS_PER_TOKEN = 4


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def chunk_text(
    text: str,
    *,
    chunk_tokens: int | None = None,
    overlap_tokens: int | None = None,
) -> List[str]:
    """Return overlapping text chunks; preserves paragraph boundaries when possible."""
    raw = (text or "").strip()
    if not raw:
        return []

    size_tok = chunk_tokens if chunk_tokens is not None else RAG_CHUNK_SIZE_TOKENS
    overlap_tok = overlap_tokens if overlap_tokens is not None else RAG_CHUNK_OVERLAP_TOKENS
    chunk_chars = max(200, size_tok * _CHARS_PER_TOKEN)
    overlap_chars = max(0, min(overlap_tok * _CHARS_PER_TOKEN, chunk_chars // 2))
    step = max(1, chunk_chars - overlap_chars)

    if len(raw) <= chunk_chars:
        return [raw]

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
    if not paragraphs:
        paragraphs = [raw]

    chunks: List[str] = []
    buf = ""

    def flush_buffer() -> None:
        nonlocal buf
        if buf.strip():
            chunks.append(buf.strip())
        buf = ""

    for para in paragraphs:
        if len(para) > chunk_chars:
            flush_buffer()
            start = 0
            while start < len(para):
                piece = para[start : start + chunk_chars].strip()
                if piece:
                    chunks.append(piece)
                start += step
            continue

        candidate = f"{buf}\n\n{para}".strip() if buf else para
        if len(candidate) <= chunk_chars:
            buf = candidate
        else:
            flush_buffer()
            buf = para

    flush_buffer()

    if len(chunks) <= 1:
        return chunks if chunks else [raw[: chunk_chars * 20]]

    # Sliding overlap merge for hard splits
    merged: List[str] = []
    i = 0
    while i < len(chunks):
        if i + 1 < len(chunks) and len(chunks[i]) < chunk_chars // 3:
            merged.append(f"{chunks[i]} {chunks[i + 1]}".strip()[: chunk_chars * 2])
            i += 2
        else:
            merged.append(chunks[i])
            i += 1
    return merged[:500]
