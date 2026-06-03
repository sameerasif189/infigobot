"""Parameterized DB access for ERP demo data, auth, and RAG search."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from psycopg.errors import UndefinedColumn

from .models import RetrievalChunk


def is_admin_user(user_id: str) -> bool:
    return str(user_id).strip().lower() == "admin"


def parse_customer_id(user_id: str) -> Optional[int]:
    try:
        return int(str(user_id).strip())
    except (TypeError, ValueError):
        return None


async def get_customer_row(pool: Any, customer_id: int) -> Optional[Dict[str, Any]]:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, name, email, tier, created_at FROM customers WHERE id = %s",
                (customer_id,),
            )
            row = await cur.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "name": row[1],
                "email": row[2],
                "tier": row[3],
                "created_at": row[4].isoformat() if row[4] else None,
            }


async def _highest_order_row(
    cur: Any, *, customer_id: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    if customer_id is not None:
        await cur.execute(
            """
            SELECT o.order_number, o.status, o.total, o.created_at, c.id, c.name
            FROM orders o
            JOIN customers c ON c.id = o.customer_id
            WHERE o.customer_id = %s
            ORDER BY o.total DESC NULLS LAST, o.id DESC
            LIMIT 1
            """,
            (customer_id,),
        )
    else:
        await cur.execute(
            """
            SELECT o.order_number, o.status, o.total, o.created_at, c.id, c.name
            FROM orders o
            JOIN customers c ON c.id = o.customer_id
            ORDER BY o.total DESC NULLS LAST, o.id DESC
            LIMIT 1
            """
        )
    row = await cur.fetchone()
    if not row:
        return None
    return {
        "order_number": row[0],
        "status": row[1],
        "total": float(row[2]) if row[2] is not None else 0,
        "created_at": row[3].isoformat() if row[3] else None,
        "customer_id": row[4],
        "customer_name": row[5],
    }


async def _highest_invoice_row(
    cur: Any, *, customer_id: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    if customer_id is not None:
        await cur.execute(
            """
            SELECT i.invoice_number, i.status, i.amount, i.due_date, o.order_number, c.id, c.name
            FROM invoices i
            JOIN orders o ON o.id = i.order_id
            JOIN customers c ON c.id = o.customer_id
            WHERE o.customer_id = %s
            ORDER BY i.amount DESC NULLS LAST, i.id DESC
            LIMIT 1
            """,
            (customer_id,),
        )
    else:
        await cur.execute(
            """
            SELECT i.invoice_number, i.status, i.amount, i.due_date, o.order_number, c.id, c.name
            FROM invoices i
            JOIN orders o ON o.id = i.order_id
            JOIN customers c ON c.id = o.customer_id
            ORDER BY i.amount DESC NULLS LAST, i.id DESC
            LIMIT 1
            """
        )
    row = await cur.fetchone()
    if not row:
        return None
    return {
        "invoice_number": row[0],
        "status": row[1],
        "amount": float(row[2]) if row[2] is not None else 0,
        "due_date": row[3].isoformat() if row[3] else None,
        "order_number": row[4],
        "customer_id": row[5],
        "customer_name": row[6],
    }


async def _order_totals_for_customer(cur: Any, customer_id: int) -> Dict[str, Any]:
    await cur.execute(
        """
        SELECT COUNT(*), COALESCE(SUM(total), 0)
        FROM orders WHERE customer_id = %s
        """,
        (customer_id,),
    )
    row = await cur.fetchone()
    return {
        "order_count": int(row[0]),
        "orders_total_sum": float(row[1]) if row[1] is not None else 0,
    }


async def get_customer_context_conn(conn: Any, user_id: str, query_text: str) -> Dict[str, Any]:
    if user_id.startswith("agent:"):
        return {
            "user_id": user_id,
            "role": "agent",
            "scope": "support",
            "data_note": (
                "Support agent account with no customer linked. "
                "Answer from the knowledge base only; do not state billing or order amounts."
            ),
            "query": query_text,
        }

    if is_admin_user(user_id):
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM customers")
            total_customers = int((await cur.fetchone())[0])
            await cur.execute("SELECT COUNT(*) FROM orders")
            total_orders = int((await cur.fetchone())[0])
            await cur.execute("SELECT COUNT(*) FROM invoices WHERE status <> 'paid'")
            unpaid_invoices = int((await cur.fetchone())[0])
            await cur.execute("SELECT COUNT(*) FROM support_tickets WHERE status IN ('open', 'pending')")
            open_tickets = int((await cur.fetchone())[0])
            await cur.execute(
                """
                SELECT o.order_number, o.status, o.total, o.created_at, c.name
                FROM orders o
                JOIN customers c ON c.id = o.customer_id
                ORDER BY o.created_at DESC
                LIMIT 5
                """
            )
            recent_orders = []
            for r in await cur.fetchall():
                recent_orders.append(
                    {
                        "order_number": r[0],
                        "status": r[1],
                        "total": float(r[2]) if r[2] is not None else 0,
                        "created_at": r[3].isoformat() if r[3] else None,
                        "customer_name": r[4],
                    }
                )
            highest_order = await _highest_order_row(cur)
            highest_invoice = await _highest_invoice_row(cur)
        return {
            "user_id": user_id,
            "resolved_customer_id": None,
            "customer_name": "Admin",
            "role": "admin",
            "scope": "global",
            "account_tier": "enterprise",
            "recent_orders": recent_orders,
            "highest_order_global": highest_order,
            "highest_invoice_global": highest_invoice,
            "open_tickets": open_tickets,
            "global_totals": {
                "customers": total_customers,
                "orders": total_orders,
                "unpaid_invoices": unpaid_invoices,
            },
            "data_note": (
                "Display names are not unique (e.g. multiple 'Taylor Singh' customers). "
                "For billing highs/lows use highest_order_global / highest_invoice_global with customer_id."
            ),
            "query": query_text,
        }

    cid = parse_customer_id(user_id)
    if cid is None:
        return {
            "user_id": user_id,
            "resolved_customer_id": None,
            "error": "invalid_customer_id",
            "query": query_text,
        }
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT id, name, email, tier FROM customers WHERE id = %s",
            (cid,),
        )
        crow = await cur.fetchone()
        if not crow:
            return {
                "user_id": user_id,
                "resolved_customer_id": cid,
                "error": "customer_not_found",
                "query": query_text,
            }

        await cur.execute(
            """
            SELECT order_number, status, total, created_at
            FROM orders
            WHERE customer_id = %s
            ORDER BY created_at DESC
            LIMIT 5
            """,
            (cid,),
        )
        recent_orders = []
        for r in await cur.fetchall():
            recent_orders.append(
                {
                    "order_number": r[0],
                    "status": r[1],
                    "total": float(r[2]) if r[2] is not None else 0,
                    "created_at": r[3].isoformat() if r[3] else None,
                }
            )

        await cur.execute(
            "SELECT COUNT(*) FROM support_tickets WHERE customer_id = %s AND status IN ('open', 'pending')",
            (cid,),
        )
        open_tickets = int((await cur.fetchone())[0])

        await cur.execute(
            """
            SELECT i.invoice_number, i.status, i.amount, i.due_date, o.order_number
            FROM invoices i
            JOIN orders o ON o.id = i.order_id
            WHERE o.customer_id = %s
            ORDER BY i.id DESC
            LIMIT 1
            """,
            (cid,),
        )
        inv_row = await cur.fetchone()
        last_invoice = None
        if inv_row:
            last_invoice = {
                "invoice_number": inv_row[0],
                "status": inv_row[1],
                "amount": float(inv_row[2]) if inv_row[2] is not None else 0,
                "due_date": inv_row[3].isoformat() if inv_row[3] else None,
                "order_number": inv_row[4],
            }

        last_order_id = recent_orders[0]["order_number"] if recent_orders else None
        highest_order = await _highest_order_row(cur, customer_id=cid)
        highest_invoice = await _highest_invoice_row(cur, customer_id=cid)
        order_totals = await _order_totals_for_customer(cur, cid)

        return {
            "user_id": user_id,
            "resolved_customer_id": cid,
            "customer_id": cid,
            "customer_name": crow[1],
            "account_tier": crow[3],
            "email": crow[2],
            "last_order_id": last_order_id,
            "recent_orders": recent_orders,
            "highest_order": highest_order,
            "highest_invoice": highest_invoice,
            "order_count": order_totals["order_count"],
            "orders_total_sum": order_totals["orders_total_sum"],
            "open_tickets": open_tickets,
            "last_invoice": last_invoice,
            "data_note": (
                f"Facts are scoped ONLY to customer_id={cid} ({crow[1]}). "
                "Do not use orders or bills belonging to other customers, even with the same name."
            ),
            "query": query_text,
        }


async def get_customer_context(pool: Any, user_id: str, query_text: str) -> Dict[str, Any]:
    async with pool.connection() as conn:
        return await get_customer_context_conn(conn, user_id, query_text)


async def create_support_ticket_conn(conn: Any, user_id: str, summary: str) -> str:
    if is_admin_user(user_id):
        raise ValueError("admin_ticket_requires_customer_id")
    cid = parse_customer_id(user_id)
    if cid is None:
        raise ValueError("invalid_customer_id")
    async with conn.transaction():
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO support_tickets (customer_id, subject, status, category)
                VALUES (%s, %s, 'open', 'general')
                RETURNING id
                """,
                (cid, summary[:300]),
            )
            tid = (await cur.fetchone())[0]
    return f"TKT-{tid}"


async def create_support_ticket(pool: Any, user_id: str, summary: str) -> str:
    async with pool.connection() as conn:
        return await create_support_ticket_conn(conn, user_id, summary)


def _legacy_kb_overlap_retrieval(rows: List[Tuple[Any, ...]], query: str, k: int) -> List[RetrievalChunk]:
    tokens = set(query.lower().split())
    if not tokens:
        return []
    scored: List[Tuple[float, RetrievalChunk]] = []
    for row in rows:
        doc_id, category, title, body = row
        text = f"{title} {body}"
        score = len(tokens.intersection(set(text.lower().split()))) / (len(tokens) + 1)
        scored.append(
            (
                score,
                RetrievalChunk(
                    id=f"kb-{doc_id}",
                    source=category,
                    text=f"{title}. {body}",
                    score=float(round(score, 3)),
                ),
            )
        )
    scored.sort(reverse=True, key=lambda x: x[0])
    return [c for _, c in scored[:k]]


async def _fts_search_table_conn(
    conn: Any, table: str, id_prefix: str, query: str, k: int
) -> List[RetrievalChunk]:
    q = query.strip()
    if not q:
        return []
    async with conn.cursor() as cur:
        try:
            await cur.execute(
                    f"""
                    SELECT id, category, title, body,
                           ts_rank_cd(search_vector, websearch_to_tsquery('english', %s)) AS rnk
                    FROM {table}
                    WHERE search_vector @@ websearch_to_tsquery('english', %s)
                    ORDER BY rnk DESC NULLS LAST
                    LIMIT %s
                    """,
                (q, q, k),
            )
            rows = await cur.fetchall()
        except UndefinedColumn:
            return []
    chunks: List[RetrievalChunk] = []
    for row in rows:
        doc_id, category, title, body, rnk = row
        rank_f = float(rnk) if rnk is not None else 0.0
        chunks.append(
            RetrievalChunk(
                id=f"{id_prefix}-{doc_id}",
                source=category,
                text=f"{title}. {body}",
                score=float(round(rank_f, 4)),
            )
        )
    return chunks


async def _fts_customer_memory_conn(
    conn: Any, customer_id: int, query: str, k: int
) -> List[RetrievalChunk]:
    q = query.strip()
    if not q or k <= 0:
        return []
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, category, fact,
                       ts_rank_cd(search_vector, plainto_tsquery('english', %s)) AS rnk
                FROM customer_memory
                WHERE customer_id = %s
                  AND search_vector @@ plainto_tsquery('english', %s)
                ORDER BY rnk DESC NULLS LAST, updated_at DESC
                LIMIT %s
                """,
                (q, customer_id, q, k),
            )
            rows = await cur.fetchall()
    except Exception:
        return []
    chunks: List[RetrievalChunk] = []
    for row in rows:
        mid, category, fact, rnk = row
        rank_f = float(rnk) if rnk is not None else 0.0
        chunks.append(
            RetrievalChunk(
                id=f"mem-{mid}",
                source=f"memory:{category}",
                text=fact,
                score=float(round(rank_f + 0.05, 4)),
            )
        )
    return chunks


async def _recent_customer_memory_conn(
    conn: Any, customer_id: int, limit: int = 5
) -> List[RetrievalChunk]:
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, category, fact
                FROM customer_memory
                WHERE customer_id = %s
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (customer_id, limit),
            )
            rows = await cur.fetchall()
    except Exception:
        return []
    return [
        RetrievalChunk(
            id=f"mem-{r[0]}",
            source=f"memory:{r[1]}",
            text=r[2],
            score=0.5,
        )
        for r in rows
    ]


async def _search_kb_fts_core_conn(
    conn: Any, query: str, k: int, *, customer_id: Optional[int] = None
) -> List[RetrievalChunk]:
    """FTS on kb_articles + rag_documents (no customer memory)."""
    q = query.strip()
    if not q:
        return []

    kb_chunks = await _fts_search_table_conn(conn, "kb_articles", "kb", q, k)
    rag_chunks = await _fts_search_table_conn(conn, "rag_documents", "rag", q, k)
    merged = kb_chunks + rag_chunks
    if merged:
        merged.sort(key=lambda c: c.score, reverse=True)
        return merged[:k]

    async with conn.cursor() as cur:
        await cur.execute("SELECT id, category, title, body FROM kb_articles")
        kb_rows = await cur.fetchall()
        rag_rows: List[Tuple[Any, ...]] = []
        try:
            await cur.execute("SELECT id, category, title, body FROM rag_documents")
            rag_rows = await cur.fetchall()
        except Exception:
            rag_rows = []

    kb_legacy = _legacy_kb_overlap_retrieval(kb_rows, q, k)
    rag_legacy = _legacy_kb_overlap_retrieval(rag_rows, q, k)
    combined = kb_legacy + rag_legacy
    combined.sort(key=lambda c: c.score, reverse=True)
    return combined[:k]


async def search_kb_conn(
    conn: Any,
    query: str,
    k: int,
    *,
    customer_id: Optional[int] = None,
) -> List[RetrievalChunk]:
    """RAG: hybrid vector (pgvector) + FTS on Neon, plus per-customer memory."""
    from .rag_vector import hybrid_search_kb_conn, vector_index_ready

    q = query.strip()
    if not q:
        return []

    if vector_index_ready():
        core = await hybrid_search_kb_conn(
            conn, q, k, _search_kb_fts_core_conn, customer_id=customer_id
        )
    else:
        core = await _search_kb_fts_core_conn(conn, q, k, customer_id=customer_id)

    merged = list(core)
    if customer_id is not None:
        mem_chunks = await _fts_customer_memory_conn(conn, customer_id, q, min(3, k))
        if not mem_chunks:
            mem_chunks = await _recent_customer_memory_conn(conn, customer_id, min(2, k))
        merged = mem_chunks + merged

    if merged:
        merged.sort(key=lambda c: c.score, reverse=True)
        return merged[:k]
    return core[:k]


async def search_kb(
    pool: Any, query: str, k: int, *, customer_id: Optional[int] = None
) -> List[RetrievalChunk]:
    async with pool.connection() as conn:
        return await search_kb_conn(conn, query, k, customer_id=customer_id)


async def get_customer_memory_lines_conn(
    conn: Any, customer_id: int, query: str, limit: int = 5
) -> List[str]:
    """Facts to inject into the LLM prompt (FTS + recent fallback)."""
    chunks = await _fts_customer_memory_conn(conn, customer_id, query, limit)
    if not chunks:
        chunks = await _recent_customer_memory_conn(conn, customer_id, limit)
    return [c.text for c in chunks[:limit]]


async def upsert_customer_memory_facts_conn(
    conn: Any,
    customer_id: int,
    facts: List[Dict[str, str]],
    *,
    app_user_id: Optional[int] = None,
    source_ref: Optional[str] = None,
) -> int:
    import hashlib

    saved = 0
    ref_base = source_ref or "chat"
    async with conn.cursor() as cur:
        for item in facts:
            fact = (item.get("fact") or "").strip()
            if len(fact) < 8:
                continue
            category = (item.get("category") or "note").strip().lower()
            if category not in ("preference", "issue", "note", "interaction"):
                category = "note"
            mkey = hashlib.md5(fact.lower().encode()).hexdigest()[:16]
            await cur.execute(
                """
                INSERT INTO customer_memory (
                    customer_id, app_user_id, memory_key, category, fact, source_ref
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (customer_id, memory_key) DO UPDATE SET
                    fact = EXCLUDED.fact,
                    category = EXCLUDED.category,
                    app_user_id = COALESCE(EXCLUDED.app_user_id, customer_memory.app_user_id),
                    source_ref = EXCLUDED.source_ref,
                    updated_at = NOW()
                """,
                (customer_id, app_user_id, mkey, category, fact[:2000], ref_base[:120]),
            )
            saved += 1
    return saved


async def get_recent_chat_for_prompt_conn(
    conn: Any, session_id: Optional[str], limit: int = 6
) -> List[Tuple[str, str]]:
    if not session_id:
        return []
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT role, content
            FROM chat_messages
            WHERE session_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (session_id, limit),
        )
        rows = await cur.fetchall()
    rows.reverse()
    return [(str(r[0]), str(r[1])) for r in rows]


async def get_user_by_username_conn(conn: Any, username: str) -> Optional[Dict[str, Any]]:
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT id, username, first_name, role, customer_id
            FROM app_users WHERE lower(username) = lower(%s)
            """,
            (username.strip(),),
        )
        row = await cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "username": row[1],
        "first_name": row[2],
        "role": row[3],
        "customer_id": row[4],
    }


async def get_user_by_username(pool: Any, username: str) -> Optional[Dict[str, Any]]:
    async with pool.connection() as conn:
        return await get_user_by_username_conn(conn, username)


async def create_session_conn(conn: Any, token: str, user_id: int, expires_at: datetime) -> None:
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO app_sessions (token, user_id, expires_at) VALUES (%s, %s, %s)",
            (token, user_id, expires_at),
        )


async def create_session(pool: Any, token: str, user_id: int, expires_at: datetime) -> None:
    async with pool.connection() as conn:
        await create_session_conn(conn, token, user_id, expires_at)


async def delete_session_conn(conn: Any, token: str) -> None:
    async with conn.cursor() as cur:
        await cur.execute("DELETE FROM app_sessions WHERE token = %s", (token,))


async def delete_session(pool: Any, token: str) -> None:
    async with pool.connection() as conn:
        await delete_session_conn(conn, token)


async def get_user_for_token_conn(conn: Any, token: str) -> Optional[Dict[str, Any]]:
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT u.id, u.username, u.first_name, u.role, u.customer_id, s.expires_at
            FROM app_sessions s
            JOIN app_users u ON u.id = s.user_id
            WHERE s.token = %s
            """,
            (token,),
        )
        row = await cur.fetchone()
    if not row:
        return None
    from datetime import timezone

    expires = row[5]
    now = datetime.now(timezone.utc)
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < now:
        await delete_session_conn(conn, token)
        return None
    return {
        "id": row[0],
        "username": row[1],
        "first_name": row[2],
        "role": row[3],
        "customer_id": row[4],
    }


async def get_user_for_token(pool: Any, token: str) -> Optional[Dict[str, Any]]:
    async with pool.connection() as conn:
        return await get_user_for_token_conn(conn, token)


async def insert_rag_document_conn(
    conn: Any,
    *,
    owner_user_id: Optional[int],
    title: str,
    body: str,
    source_type: str,
    source_ref: Optional[str],
    category: str = "user",
) -> Dict[str, Any]:
    from .rag_vector import index_knowledge_source_conn

    t = title[:300]
    b = body[:50000]
    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO rag_documents (owner_user_id, title, body, source_type, source_ref, category)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, title, source_type, source_ref, created_at
            """,
            (owner_user_id, t, b, source_type, source_ref, category),
        )
        row = await cur.fetchone()
    doc = {
        "id": row[0],
        "title": row[1],
        "source_type": row[2],
        "source_ref": row[3],
        "created_at": row[4].isoformat() if row[4] else None,
        "chunks_indexed": 0,
    }
    doc["chunks_indexed"] = await index_knowledge_source_conn(
        conn, "rag_documents", int(doc["id"]), t, b
    )
    return doc


async def insert_rag_document(
    pool: Any,
    *,
    owner_user_id: Optional[int],
    title: str,
    body: str,
    source_type: str,
    source_ref: Optional[str],
    category: str = "user",
) -> Dict[str, Any]:
    async with pool.connection() as conn:
        return await insert_rag_document_conn(
            conn,
            owner_user_id=owner_user_id,
            title=title,
            body=body,
            source_type=source_type,
            source_ref=source_ref,
            category=category,
        )


async def list_rag_documents(pool: Any, limit: int = 50) -> List[Dict[str, Any]]:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, title, source_type, source_ref, category,
                       left(body, 200) AS preview, created_at
                FROM rag_documents
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = await cur.fetchall()
    return [
        {
            "id": r[0],
            "title": r[1],
            "source_type": r[2],
            "source_ref": r[3],
            "category": r[4],
            "preview": r[5],
            "created_at": r[6].isoformat() if r[6] else None,
        }
        for r in rows
    ]


async def update_rag_document_body(pool: Any, doc_id: int, title: str, body: str) -> None:
    from .rag_vector import index_knowledge_source_conn

    t = title[:300]
    b = body[:50000]
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE rag_documents SET title = %s, body = %s
                WHERE id = %s
                """,
                (t, b, doc_id),
            )
        await index_knowledge_source_conn(conn, "rag_documents", doc_id, t, b)


async def get_feed_by_url(pool: Any, url: str) -> Optional[Dict[str, Any]]:
    from .ingest import normalize_feed_url

    canonical = normalize_feed_url(url)
    variants = {
        canonical,
        canonical.rstrip("/"),
        url.strip(),
        url.strip().rstrip("/"),
        "http://localhost:8000/",
        "http://127.0.0.1:8000/",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    }
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, url, title, poll_interval_minutes, document_id, created_by, enabled
                FROM rag_feeds
                WHERE url = ANY(%s)
                ORDER BY id DESC
                LIMIT 1
                """,
                (list(variants),),
            )
            row = await cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "url": row[1],
        "title": row[2],
        "poll_interval_minutes": row[3],
        "document_id": row[4],
        "created_by": row[5],
        "enabled": row[6],
    }


async def insert_rag_feed(
    pool: Any,
    *,
    url: str,
    title: str,
    poll_interval_minutes: int,
    created_by: Optional[int],
) -> Dict[str, Any]:
    from .ingest import normalize_feed_url

    url = normalize_feed_url(url)
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO rag_feeds (url, title, poll_interval_minutes, created_by)
                VALUES (%s, %s, %s, %s)
                RETURNING id, url, title, poll_interval_minutes, enabled, last_synced_at
                """,
                (url[:500], title[:300], poll_interval_minutes, created_by),
            )
            row = await cur.fetchone()
    return {
        "id": row[0],
        "url": row[1],
        "title": row[2],
        "poll_interval_minutes": row[3],
        "enabled": row[4],
        "last_synced_at": row[5].isoformat() if row[5] else None,
    }


def _feed_kb_index_meta(
    *,
    document_id: Optional[int],
    body_chars: Optional[int],
    last_error: Optional[str],
    last_synced_at: Optional[Any],
) -> Dict[str, Any]:
    """Derive whether a feed's content is in rag_documents (searchable knowledge base)."""
    chars = int(body_chars or 0)
    if last_error:
        return {
            "kb_indexed": False,
            "kb_status": "sync_failed",
            "kb_status_label": "Not in knowledge base — sync failed",
        }
    if document_id is None:
        if last_synced_at:
            return {
                "kb_indexed": False,
                "kb_status": "no_document",
                "kb_status_label": "Not in knowledge base — no document linked",
            }
        return {
            "kb_indexed": False,
            "kb_status": "never_synced",
            "kb_status_label": "Not in knowledge base — never synced",
        }
    if chars < 20:
        return {
            "kb_indexed": False,
            "kb_status": "empty_document",
            "kb_status_label": "Not in knowledge base — synced but empty",
        }
    return {
        "kb_indexed": True,
        "kb_status": "indexed",
        "kb_status_label": f"In knowledge base · doc #{document_id} · {chars:,} chars (searchable)",
    }


async def list_rag_feeds(pool: Any, enabled_only: bool = False) -> List[Dict[str, Any]]:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            q = """
                SELECT f.id, f.url, f.title, f.poll_interval_minutes, f.enabled,
                       f.document_id, f.last_synced_at, f.last_error, f.created_at,
                       d.title AS doc_title,
                       length(d.body) AS body_chars,
                       d.source_type AS doc_source_type
                FROM rag_feeds f
                LEFT JOIN rag_documents d ON d.id = f.document_id
            """
            if enabled_only:
                q += " WHERE f.enabled = TRUE"
            q += " ORDER BY f.id DESC"
            await cur.execute(q)
            rows = await cur.fetchall()
    out: List[Dict[str, Any]] = []
    for r in rows:
        doc_id = r[5]
        last_synced = r[6]
        last_error = r[7]
        body_chars = r[10]
        meta = _feed_kb_index_meta(
            document_id=doc_id,
            body_chars=body_chars,
            last_error=last_error,
            last_synced_at=last_synced,
        )
        out.append(
            {
                "id": r[0],
                "url": r[1],
                "title": r[2],
                "poll_interval_minutes": r[3],
                "enabled": r[4],
                "document_id": doc_id,
                "last_synced_at": last_synced.isoformat() if last_synced else None,
                "last_error": last_error,
                "created_at": r[8].isoformat() if r[8] else None,
                "doc_title": r[9],
                "body_chars": int(body_chars) if body_chars is not None else 0,
                "doc_source_type": r[11],
                **meta,
            }
        )
    return out


async def get_rag_feed(pool: Any, feed_id: int) -> Optional[Dict[str, Any]]:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, url, title, poll_interval_minutes, document_id, created_by, enabled
                FROM rag_feeds WHERE id = %s
                """,
                (feed_id,),
            )
            row = await cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "url": row[1],
        "title": row[2],
        "poll_interval_minutes": row[3],
        "document_id": row[4],
        "created_by": row[5],
        "enabled": row[6],
    }


async def get_feeds_due_for_sync(pool: Any) -> List[Dict[str, Any]]:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, url, title, poll_interval_minutes, document_id, created_by
                FROM rag_feeds
                WHERE enabled = TRUE
                  AND (
                    last_synced_at IS NULL
                    OR last_synced_at < NOW() - (poll_interval_minutes || ' minutes')::INTERVAL
                  )
                ORDER BY last_synced_at NULLS FIRST
                LIMIT 20
                """
            )
            rows = await cur.fetchall()
    return [
        {
            "id": r[0],
            "url": r[1],
            "title": r[2],
            "poll_interval_minutes": r[3],
            "document_id": r[4],
            "created_by": r[5],
        }
        for r in rows
    ]


async def update_feed_after_sync(
    pool: Any, feed_id: int, document_id: Optional[int], error: Optional[str]
) -> None:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            if error:
                await cur.execute(
                    """
                    UPDATE rag_feeds
                    SET last_synced_at = NOW(), last_error = %s
                    WHERE id = %s
                    """,
                    (error, feed_id),
                )
            else:
                await cur.execute(
                    """
                    UPDATE rag_feeds
                    SET last_synced_at = NOW(), last_error = NULL, document_id = %s
                    WHERE id = %s
                    """,
                    (document_id, feed_id),
                )


async def purge_account_specific_learned_kb_conn(conn: Any) -> int:
    """Remove learned KB rows that embed one-off order/invoice data (often from admin chats)."""
    async with conn.cursor() as cur:
        await cur.execute(
            """
            DELETE FROM rag_documents
            WHERE source_type = 'learned'
              AND (
                body LIKE '%ORD-%'
                OR body LIKE '%INV-%'
                OR body ILIKE '%customer id%'
              )
            RETURNING id
            """
        )
        rows = await cur.fetchall()
    return len(rows)


async def upsert_learned_qa_conn(
    conn: Any,
    question: str,
    answer: str,
    *,
    title: Optional[str] = None,
    body: Optional[str] = None,
    owner_user_id: Optional[int] = None,
) -> Dict[str, Any]:
    import hashlib

    ref = "learned:" + hashlib.md5(question.strip().lower().encode()).hexdigest()[:20]
    doc_title = (title or f"Q: {question[:120]}").strip()[:300]
    doc_body = (body or f"Question: {question}\n\nAnswer: {answer}").strip()[:50000]
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT id FROM rag_documents WHERE source_type = 'learned' AND source_ref = %s",
            (ref,),
        )
        existing = await cur.fetchone()
        if existing:
            doc_id = existing[0]
            await cur.execute(
                """
                UPDATE rag_documents
                SET title = %s, body = %s, owner_user_id = COALESCE(%s, owner_user_id)
                WHERE id = %s
                """,
                (doc_title, doc_body, owner_user_id, doc_id),
            )
        else:
            await cur.execute(
                """
                INSERT INTO rag_documents (owner_user_id, title, body, source_type, source_ref, category)
                VALUES (%s, %s, %s, 'learned', %s, 'learned')
                RETURNING id
                """,
                (owner_user_id, doc_title, doc_body, ref),
            )
            doc_id = (await cur.fetchone())[0]
    from .rag_vector import index_knowledge_source_conn

    chunks_indexed = await index_knowledge_source_conn(
        conn, "rag_documents", doc_id, doc_title, doc_body
    )
    return {
        "id": doc_id,
        "title": doc_title,
        "source_type": "learned",
        "chunks_indexed": chunks_indexed,
    }


async def ensure_chat_session_conn(
    conn: Any,
    session_id: str,
    user_id: Optional[int],
    erp_uid: str,
    channel: str,
) -> None:
    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO chat_sessions (id, user_id, erp_uid, channel)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                updated_at = NOW(),
                user_id = COALESCE(EXCLUDED.user_id, chat_sessions.user_id),
                erp_uid = EXCLUDED.erp_uid,
                channel = EXCLUDED.channel
            """,
            (session_id, user_id, erp_uid, channel),
        )


async def get_chat_session_erp_uid_conn(conn: Any, session_id: str) -> Optional[str]:
    async with conn.cursor() as cur:
        await cur.execute("SELECT erp_uid FROM chat_sessions WHERE id = %s", (session_id,))
        row = await cur.fetchone()
    return str(row[0]) if row and row[0] is not None else None


async def touch_chat_session_conn(conn: Any, session_id: str) -> None:
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE chat_sessions SET updated_at = NOW() WHERE id = %s",
            (session_id,),
        )


async def insert_chat_message_conn(
    conn: Any,
    session_id: str,
    role: str,
    content: str,
    *,
    llm_source: Optional[str] = None,
    confidence: Optional[float] = None,
    intent_class: Optional[str] = None,
    sources_used: int = 0,
    rag_document_id: Optional[int] = None,
) -> int:
    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO chat_messages (
                session_id, role, content, llm_source, confidence,
                intent_class, sources_used, rag_document_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                session_id,
                role,
                content[:50000],
                llm_source,
                confidence,
                intent_class,
                sources_used,
                rag_document_id,
            ),
        )
        row = await cur.fetchone()
    return int(row[0])


async def list_chat_messages_conn(
    conn: Any, session_id: str, limit: int = 100
) -> List[Dict[str, Any]]:
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT id, role, content, llm_source, confidence, intent_class,
                   sources_used, rag_document_id, created_at
            FROM chat_messages
            WHERE session_id = %s
            ORDER BY created_at ASC
            LIMIT %s
            """,
            (session_id, limit),
        )
        rows = await cur.fetchall()
    return [
        {
            "id": r[0],
            "role": r[1],
            "content": r[2],
            "llm_source": r[3],
            "confidence": float(r[4]) if r[4] is not None else None,
            "intent_class": r[5],
            "sources_used": r[6],
            "rag_document_id": r[7],
            "created_at": r[8].isoformat() if r[8] else None,
        }
        for r in rows
    ]


async def upsert_learned_qa(pool: Any, question: str, answer: str) -> Dict[str, Any]:
    async with pool.connection() as conn:
        return await upsert_learned_qa_conn(conn, question, answer)


async def get_order_detail(pool: Any, order_id: int) -> Optional[Dict[str, Any]]:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT o.id, o.order_number, o.status, o.total, o.created_at,
                       o.customer_id, c.name, c.email
                FROM orders o
                JOIN customers c ON c.id = o.customer_id
                WHERE o.id = %s
                """,
                (order_id,),
            )
            orow = await cur.fetchone()
            if not orow:
                return None
            oid = orow[0]
            await cur.execute(
                """
                SELECT p.sku, p.name, oi.quantity, oi.unit_price
                FROM order_items oi
                JOIN products p ON p.id = oi.product_id
                WHERE oi.order_id = %s
                """,
                (oid,),
            )
            items = []
            for r in await cur.fetchall():
                items.append(
                    {
                        "sku": r[0],
                        "product_name": r[1],
                        "quantity": r[2],
                        "unit_price": float(r[3]) if r[3] is not None else 0,
                    }
                )
            return {
                "id": orow[0],
                "order_number": orow[1],
                "status": orow[2],
                "total": float(orow[3]) if orow[3] is not None else 0,
                "created_at": orow[4].isoformat() if orow[4] else None,
                "customer_id": orow[5],
                "customer_name": orow[6],
                "customer_email": orow[7],
                "items": items,
            }


async def list_orders_for_customer(pool: Any, customer_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, order_number, status, total, created_at
                FROM orders
                WHERE customer_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (customer_id, limit),
            )
            rows = await cur.fetchall()
    return [
        {
            "id": r[0],
            "order_number": r[1],
            "status": r[2],
            "total": float(r[3]) if r[3] is not None else 0,
            "created_at": r[4].isoformat() if r[4] else None,
        }
        for r in rows
    ]


async def list_unpaid_invoices(pool: Any, user_id: str) -> List[Dict[str, Any]]:
    if is_admin_user(user_id):
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT i.invoice_number, i.status, i.amount, i.due_date, o.order_number
                    FROM invoices i
                    JOIN orders o ON o.id = i.order_id
                    WHERE i.status NOT IN ('paid')
                    ORDER BY i.due_date ASC
                    """
                )
                rows = await cur.fetchall()
        return [
            {
                "invoice_number": r[0],
                "status": r[1],
                "amount": float(r[2]) if r[2] is not None else 0,
                "due_date": r[3].isoformat() if r[3] else None,
                "order_number": r[4],
            }
            for r in rows
        ]

    cid = parse_customer_id(user_id)
    if cid is None:
        return []
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT i.invoice_number, i.status, i.amount, i.due_date, o.order_number
                FROM invoices i
                JOIN orders o ON o.id = i.order_id
                WHERE o.customer_id = %s AND i.status NOT IN ('paid')
                ORDER BY i.due_date ASC
                """,
                (cid,),
            )
            rows = await cur.fetchall()
    return [
        {
            "invoice_number": r[0],
            "status": r[1],
            "amount": float(r[2]) if r[2] is not None else 0,
            "due_date": r[3].isoformat() if r[3] else None,
            "order_number": r[4],
        }
        for r in rows
    ]
