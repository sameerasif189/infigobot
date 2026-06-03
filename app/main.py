"""Infigo website chat API — deploy to Vercel (root: infigobot/)."""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .chat_store import persist_chat_turn_conn
from .db import close_db_pool, database_ready, get_pool, init_db_pool
from .db_util import db_connection
from .ingest import extract_text_from_bytes, normalize_title
from .models import ChatResponse, KnowledgeTextRequest, PublicChatRequest
from .repositories import (
    get_chat_session_erp_uid_conn,
    get_recent_chat_for_prompt_conn,
    insert_rag_document,
)
from .services import BudgetTracker, IntentRouter, LLMClient, SimpleRetriever
from .settings import (
    CHAT_HISTORY_TURNS,
    CORS_ALLOWED_ORIGINS,
    DATABASE_URL,
    GUARDRAILS,
    INGEST_API_KEY,
    PUBLIC_CHAT_API_KEY,
    SITE_BOOKING_URL,
    SITE_BOT_ENABLED,
    SITE_COMPANY_NAME,
    SITE_CONTACT_EMAIL,
    SITE_CONTENT_ENABLED,
    SITE_CONTENT_JSON,
    SITE_FETCH_URL,
    SITE_JSON_URL,
    SITE_PROPOSAL_URL,
    SITE_RUNTIME_FETCH_ENABLED,
)
from .site_bot import (
    append_booking_link_if_needed,
    booking_reply,
    build_site_erp_context,
    build_site_system_prompt,
    build_site_user_prompt,
    site_public_erp_uid,
    site_response_meta,
)
from .site_content import resolve_site_context

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

router = IntentRouter()
retriever = SimpleRetriever()
llm = LLMClient()
budget = BudgetTracker(monthly_budget=float(GUARDRAILS["monthly_budget_usd"]))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db_pool()
    yield
    await close_db_pool()


_cors_origins = [o.strip() for o in CORS_ALLOWED_ORIGINS.split(",") if o.strip()]
app = FastAPI(title="Infigo Site Bot API", version="1.0.0", lifespan=lifespan)
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Site-Api-Key", "X-Ingest-Key"],
    )
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _estimate_cost(prompt: str, output: str) -> float:
    in_tokens = max(1, int(len(prompt) / 4))
    out_tokens = max(1, int(len(output) / 4))
    return round((in_tokens / 1_000_000) * 0.4 + (out_tokens / 1_000_000) * 1.6, 6)


def _confidence(n_chunks: int) -> float:
    if n_chunks >= 2:
        return 0.82
    if n_chunks == 1:
        return 0.68
    return 0.45


def _wrap_site(response: ChatResponse, message: str, visitor: Optional[Dict[str, str]]) -> ChatResponse:
    meta = site_response_meta(message, visitor=visitor)
    answer = append_booking_link_if_needed(response.answer, message, visitor)
    return response.model_copy(
        update={
            "answer": answer,
            "booking_url": meta.get("booking_url"),
            "contact_email": meta.get("contact_email"),
            "proposal_hint": meta.get("proposal_hint"),
        }
    )


async def _persist(
    *,
    session_id: Optional[str],
    erp_uid: str,
    message: str,
    response: ChatResponse,
    intent_class: str,
) -> ChatResponse:
    if not DATABASE_URL:
        return response
    try:
        async with db_connection(timeout=15.0) as conn:
            sid = await persist_chat_turn_conn(
                conn,
                session_id=session_id,
                user_id=None,
                erp_uid=erp_uid,
                channel="site",
                user_message=message,
                assistant_message=response.answer,
                llm_source=response.llm_source,
                confidence=response.confidence,
                intent_class=intent_class,
                sources_used=response.sources_used,
            )
        return response.model_copy(update={"session_id": sid})
    except Exception as exc:
        logger.warning("Chat persist skipped: %s", exc)
        return response


async def run_site_chat(
    message: str,
    *,
    session_id: Optional[str] = None,
    visitor: Optional[Dict[str, str]] = None,
) -> ChatResponse:
    erp_uid = site_public_erp_uid()
    intent_class = router.route(message)

    if intent_class == "human_required" and GUARDRAILS["handoff_on_sensitive_intent"]:
        contact = SITE_CONTACT_EMAIL or "the contact form on infigosolutions.com"
        resp = _wrap_site(
            ChatResponse(
                answer=f"This needs our team. Please reach us via {contact}.",
                confidence=0.35,
                action="handoff",
                est_cost_usd=0.0,
                llm_source="rules",
            ),
            message,
            visitor,
        )
        return await _persist(session_id=session_id, erp_uid=erp_uid, message=message, response=resp, intent_class=intent_class)

    booked = booking_reply(message, visitor)
    if booked:
        resp = _wrap_site(
            ChatResponse(
                answer=booked,
                confidence=0.95,
                action="answered",
                est_cost_usd=0.0,
                llm_source="rules",
            ),
            message,
            visitor,
        )
        return await _persist(session_id=session_id, erp_uid=erp_uid, message=message, response=resp, intent_class="auto_answer")

    chunks = await retriever.retrieve(message, int(GUARDRAILS["max_retrieval_chunks"]))
    confidence = _confidence(len(chunks))

    if confidence < float(GUARDRAILS["min_confidence_to_answer"]) and GUARDRAILS["handoff_on_low_confidence"]:
        contact = SITE_CONTACT_EMAIL or "our contact page"
        resp = _wrap_site(
            ChatResponse(
                answer=f"I am not sure from our materials. Please use {contact} and our team will help.",
                confidence=confidence,
                action="handoff",
                est_cost_usd=0.0,
                llm_source="rules",
                sources_used=len(chunks),
            ),
            message,
            visitor,
        )
        return await _persist(session_id=session_id, erp_uid=erp_uid, message=message, response=resp, intent_class=intent_class)

    kb_context = "\n".join(f"- {c.text}" for c in chunks) if chunks else "(none)"
    live, content_source = await resolve_site_context(
        json_url=SITE_JSON_URL,
        runtime_enabled=SITE_RUNTIME_FETCH_ENABLED,
        runtime_url=SITE_FETCH_URL,
        bundled_enabled=SITE_CONTENT_ENABLED,
        bundled_path=SITE_CONTENT_JSON,
    )
    if live:
        label = {
            "json_url": "Official site content (public content.json)",
            "bundled_json": "Official site content (bundled JSON in API)",
            "runtime_html": "Live website text (HTML fetch)",
        }.get(content_source, "Site content")
        kb_context = f"{label}:\n{live[:9000]}\n\nFallback hints:\n{kb_context}"
    chat_history_block = ""
    if DATABASE_URL and session_id and CHAT_HISTORY_TURNS > 0:
        try:
            async with db_connection(timeout=12.0) as conn:
                sess_uid = await get_chat_session_erp_uid_conn(conn, session_id)
                if sess_uid and sess_uid != erp_uid:
                    session_id = None
                prior = (
                    await get_recent_chat_for_prompt_conn(conn, session_id, CHAT_HISTORY_TURNS)
                    if session_id
                    else []
                )
                if prior:
                    lines = [
                        f"{'Visitor' if role == 'user' else 'You'}: {content[:500]}"
                        for role, content in prior
                    ]
                    chat_history_block = "\nRecent conversation:\n" + "\n".join(lines) + "\n"
        except Exception as exc:
            logger.warning("History load skipped: %s", exc)

    system_prompt = build_site_system_prompt(visitor=visitor)
    user_prompt = build_site_user_prompt(message, kb_context, chat_history_block=chat_history_block)
    answer, llm_source = await llm.answer(
        system_prompt,
        user_prompt,
        int(GUARDRAILS["max_output_tokens"]),
        message,
    )
    cost = _estimate_cost(system_prompt + user_prompt, answer)
    budget.add(cost)

    resp = _wrap_site(
        ChatResponse(
            answer=answer,
            confidence=round(confidence, 2),
            action="answered",
            est_cost_usd=round(cost, 6),
            llm_source=llm_source,
            sources_used=len(chunks),
        ),
        message,
        visitor,
    )
    return await _persist(session_id=session_id, erp_uid=erp_uid, message=message, response=resp, intent_class=intent_class)


def _verify_public_key(x_site_api_key: Optional[str]) -> None:
    if not SITE_BOT_ENABLED:
        raise HTTPException(status_code=503, detail="Site bot disabled")
    if PUBLIC_CHAT_API_KEY and x_site_api_key != PUBLIC_CHAT_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Site-Api-Key")


def _verify_ingest_key(x_ingest_key: Optional[str]) -> None:
    if INGEST_API_KEY and x_ingest_key != INGEST_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid X-Ingest-Key")


@app.get("/")
async def root() -> dict:
    return {
        "service": "Infigo Site Bot API",
        "chat": "POST /chat/public",
        "embed": "/static/infigo-embed.js",
        "site_json": "/public/site-content.json",
        "health": "/health",
    }


@app.get("/public/site-content.json")
async def public_site_content_json() -> JSONResponse:
    """Copy of bundled content — host the same file on React: public/content.json"""
    from pathlib import Path
    import json

    p = Path(__file__).resolve().parent.parent / SITE_CONTENT_JSON
    if not p.is_file():
        p = Path(__file__).resolve().parent.parent / "config" / "infigo_site_content.json"
    with open(p, "r", encoding="utf-8") as f:
        return JSONResponse(json.load(f))


@app.get("/health")
async def health() -> dict:
    month, spend, alert = budget.snapshot()
    return {
        "ok": True,
        "database": database_ready(),
        "llm_configured": llm.api_enabled,
        "site_bot": SITE_BOT_ENABLED,
        "budget_month": month,
        "budget_spend_usd": round(spend, 4),
        "budget_alert": alert,
    }


@app.get("/integrations/site/status")
async def site_status() -> dict:
    return {
        "site_bot_enabled": SITE_BOT_ENABLED,
        "public_chat_key_required": bool(PUBLIC_CHAT_API_KEY),
        "company": SITE_COMPANY_NAME,
        "contact_email_configured": bool(SITE_CONTACT_EMAIL),
        "booking_url_configured": bool(SITE_BOOKING_URL),
        "proposal_url": SITE_PROPOSAL_URL,
        "content_mode": (
            "json_url"
            if SITE_JSON_URL
            else "bundled_json"
            if SITE_CONTENT_ENABLED
            else "runtime_html"
            if SITE_RUNTIME_FETCH_ENABLED
            else "fallback_only"
        ),
        "site_json_url": SITE_JSON_URL or None,
        "runtime_fetch_enabled": SITE_RUNTIME_FETCH_ENABLED,
        "runtime_fetch_url": SITE_FETCH_URL or None,
        "site_content_json": SITE_CONTENT_JSON,
        "site_content_enabled": SITE_CONTENT_ENABLED,
        "cors_origins": _cors_origins,
        "embed_script": "/static/infigo-embed.js",
    }


@app.post("/chat/public", response_model=ChatResponse)
async def chat_public(
    req: PublicChatRequest,
    x_site_api_key: Optional[str] = Header(default=None, alias="X-Site-Api-Key"),
) -> ChatResponse:
    _verify_public_key(x_site_api_key)
    visitor: Dict[str, str] = {}
    if req.visitor_name:
        visitor["name"] = req.visitor_name.strip()
    if req.visitor_email:
        visitor["email"] = req.visitor_email.strip()
    return await run_site_chat(req.message, session_id=req.session_id, visitor=visitor or None)


@app.post("/knowledge/text")
async def knowledge_text(
    body: KnowledgeTextRequest,
    x_ingest_key: Optional[str] = Header(default=None, alias="X-Ingest-Key"),
) -> dict:
    _verify_ingest_key(x_ingest_key)
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="DATABASE_URL not configured")
    doc = await insert_rag_document(
        pool,
        owner_user_id=None,
        title=body.title,
        body=body.body,
        source_type="text",
        source_ref=None,
        category=body.category,
    )
    return {"ok": True, "document": doc}


@app.post("/knowledge/file")
async def knowledge_file(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    x_ingest_key: Optional[str] = Header(default=None, alias="X-Ingest-Key"),
) -> dict:
    _verify_ingest_key(x_ingest_key)
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="DATABASE_URL not configured")
    data = await file.read()
    if len(data) > 2_000_000:
        raise HTTPException(status_code=400, detail="File too large (max 2MB)")
    try:
        text = extract_text_from_bytes(file.filename or "upload.txt", data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    doc = await insert_rag_document(
        pool,
        owner_user_id=None,
        title=normalize_title(title, file.filename or "upload"),
        body=text,
        source_type="file",
        source_ref=file.filename,
        category="infigo",
    )
    return {"ok": True, "document": doc}


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)
