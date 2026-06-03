"""Persist chat sessions and messages separately from auth sessions."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from .repositories import (
    ensure_chat_session_conn,
    insert_chat_message_conn,
    touch_chat_session_conn,
)


async def persist_chat_turn_conn(
    conn: Any,
    *,
    session_id: Optional[str],
    user_id: Optional[int],
    erp_uid: str,
    channel: str,
    user_message: str,
    assistant_message: Optional[str] = None,
    llm_source: Optional[str] = None,
    confidence: Optional[float] = None,
    intent_class: Optional[str] = None,
    sources_used: int = 0,
    rag_document_id: Optional[int] = None,
) -> str:
    sid = (session_id or "").strip() or str(uuid.uuid4())
    await ensure_chat_session_conn(conn, sid, user_id, erp_uid, channel)
    await insert_chat_message_conn(conn, sid, "user", user_message)
    if assistant_message:
        await insert_chat_message_conn(
            conn,
            sid,
            "assistant",
            assistant_message,
            llm_source=llm_source,
            confidence=confidence,
            intent_class=intent_class,
            sources_used=sources_used,
            rag_document_id=rag_document_id,
        )
    await touch_chat_session_conn(conn, sid)
    return sid
