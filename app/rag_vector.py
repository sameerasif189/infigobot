"""Chunk, embed, and vector-search knowledge stored in Neon (pgvector)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from psycopg.errors import UndefinedTable

from .chunking import _approx_tokens, chunk_text
from .embeddings import embed_query, embed_texts, embeddings_configured, vector_to_pg
from .models import RetrievalChunk
from .settings import (
    RAG_CHUNK_OVERLAP_TOKENS,
    RAG_CHUNK_SIZE_TOKENS,
    RAG_RETRIEVAL_MODE,
    RAG_VECTOR_ENABLED,
    RAG_VECTOR_TOP_K,
)

logger = logging.getLogger(__name__)

_SOURCE_KB = "kb_articles"
_SOURCE_RAG = "rag_documents"


def vector_index_ready() -> bool:
    return RAG_VECTOR_ENABLED and embeddings_configured()


async def _table_exists(conn: Any, table: str) -> bool:
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (table,),
        )
        return await cur.fetchone() is not None


async def delete_chunks_for_source_conn(
    conn: Any, source_table: str, source_id: int
) -> None:
    if not await _table_exists(conn, "knowledge_chunks"):
        return
    async with conn.cursor() as cur:
        await cur.execute(
            "DELETE FROM knowledge_chunks WHERE source_table = %s AND source_id = %s",
            (source_table, source_id),
        )


async def index_knowledge_source_conn(
    conn: Any,
    source_table: str,
    source_id: int,
    title: str,
    body: str,
) -> int:
    """Chunk + embed + store rows in knowledge_chunks. Returns chunk count."""
    if not vector_index_ready():
        return 0
    if not await _table_exists(conn, "knowledge_chunks"):
        logger.warning("knowledge_chunks missing — run scripts/migrate_pgvector_rag.sql")
        return 0

    full_text = f"{(title or '').strip()}\n\n{(body or '').strip()}".strip()
    if not full_text:
        await delete_chunks_for_source_conn(conn, source_table, source_id)
        return 0

    pieces = chunk_text(full_text)
    if not pieces:
        return 0

    try:
        vectors = await embed_texts(pieces)
    except Exception as exc:
        logger.warning("Embedding failed for %s:%s — %s", source_table, source_id, exc)
        return 0

    await delete_chunks_for_source_conn(conn, source_table, source_id)
    title_hint = (title or "")[:300]
    async with conn.cursor() as cur:
        for idx, (content, vec) in enumerate(zip(pieces, vectors)):
            await cur.execute(
                """
                INSERT INTO knowledge_chunks (
                    source_table, source_id, chunk_index, title_hint, content,
                    token_estimate, embedding
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::vector)
                """,
                (
                    source_table,
                    source_id,
                    idx,
                    title_hint,
                    content[:50000],
                    _approx_tokens(content),
                    vector_to_pg(vec),
                ),
            )
    logger.info(
        "Indexed %s chunks for %s id=%s (size=%s overlap=%s)",
        len(pieces),
        source_table,
        source_id,
        RAG_CHUNK_SIZE_TOKENS,
        RAG_CHUNK_OVERLAP_TOKENS,
    )
    return len(pieces)


async def vector_search_conn(
    conn: Any,
    query: str,
    k: int,
    *,
    source_tables: Optional[List[str]] = None,
) -> List[RetrievalChunk]:
    if not vector_index_ready() or not await _table_exists(conn, "knowledge_chunks"):
        return []

    tables = source_tables or [_SOURCE_KB, _SOURCE_RAG]
    try:
        qvec = await embed_query(query)
    except Exception as exc:
        logger.warning("Query embedding failed: %s", exc)
        return []

    vec_lit = vector_to_pg(qvec)
    placeholders = ",".join(["%s"] * len(tables))
    sql = f"""
        SELECT id, source_table, source_id, title_hint, content,
               1 - (embedding <=> %s::vector) AS similarity
        FROM knowledge_chunks
        WHERE source_table IN ({placeholders})
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    params: tuple = (vec_lit, *tables, vec_lit, k)
    async with conn.cursor() as cur:
        try:
            await cur.execute(sql, params)
            rows = await cur.fetchall()
        except UndefinedTable:
            return []

    chunks: List[RetrievalChunk] = []
    for row in rows:
        cid, src_table, src_id, title_hint, content, sim = row
        prefix = "kb" if src_table == _SOURCE_KB else "rag"
        label = f"{title_hint}. {content}" if title_hint else content
        chunks.append(
            RetrievalChunk(
                id=f"vchunk-{cid}",
                source=f"{prefix}-vec-{src_id}",
                text=label.strip()[:8000],
                score=float(round(float(sim or 0), 4)),
            )
        )
    return chunks


def _rrf_merge(
    *ranked_lists: List[RetrievalChunk],
    k: int = 60,
    limit: int = 10,
) -> List[RetrievalChunk]:
    """Reciprocal rank fusion across retrieval lists."""
    scores: Dict[str, float] = {}
    by_id: Dict[str, RetrievalChunk] = {}
    for results in ranked_lists:
        for rank, chunk in enumerate(results):
            scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (k + rank + 1)
            by_id[chunk.id] = chunk
    if not scores:
        return []
    ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    out: List[RetrievalChunk] = []
    for cid, fused in ordered[:limit]:
        c = by_id[cid]
        out.append(
            RetrievalChunk(id=c.id, source=c.source, text=c.text, score=float(round(fused, 4)))
        )
    return out


async def hybrid_search_kb_conn(
    conn: Any,
    query: str,
    k: int,
    fts_fn,
    *,
    customer_id: Optional[int] = None,
) -> List[RetrievalChunk]:
    """Combine vector similarity (Neon pgvector) with existing FTS retrieval."""
    mode = (RAG_RETRIEVAL_MODE or "hybrid").lower()
    fetch_k = max(k, RAG_VECTOR_TOP_K)

    fts_chunks: List[RetrievalChunk] = []
    vec_chunks: List[RetrievalChunk] = []

    if mode in ("fts", "hybrid"):
        fts_chunks = await fts_fn(conn, query, fetch_k, customer_id=customer_id)

    if mode in ("vector", "hybrid"):
        vec_chunks = await vector_search_conn(conn, query, fetch_k)

    if mode == "vector":
        return vec_chunks[:k]
    if mode == "fts" or not vec_chunks:
        return fts_chunks[:k]
    if not fts_chunks:
        return vec_chunks[:k]

    return _rrf_merge(fts_chunks, vec_chunks, limit=k)


async def reindex_all_conn(conn: Any) -> Dict[str, int]:
    """Re-chunk and embed all kb_articles and rag_documents."""
    stats = {"kb_articles": 0, "rag_documents": 0, "chunks": 0}
    if not vector_index_ready():
        return stats

    async with conn.cursor() as cur:
        await cur.execute("SELECT id, title, body FROM kb_articles ORDER BY id")
        kb_rows = await cur.fetchall()
        await cur.execute("SELECT id, title, body FROM rag_documents ORDER BY id")
        rag_rows = await cur.fetchall()

    for row in kb_rows:
        n = await index_knowledge_source_conn(conn, _SOURCE_KB, row[0], row[1], row[2])
        stats["kb_articles"] += 1
        stats["chunks"] += n

    for row in rag_rows:
        n = await index_knowledge_source_conn(conn, _SOURCE_RAG, row[0], row[1], row[2])
        stats["rag_documents"] += 1
        stats["chunks"] += n

    return stats


async def chunk_count_conn(conn: Any) -> int:
    if not await _table_exists(conn, "knowledge_chunks"):
        return 0
    async with conn.cursor() as cur:
        await cur.execute("SELECT COUNT(*) FROM knowledge_chunks")
        row = await cur.fetchone()
    return int(row[0]) if row else 0
