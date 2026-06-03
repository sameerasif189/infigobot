import datetime as dt
import logging
import re
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import httpx

from .db_util import db_connection
from .models import RetrievalChunk
from .repositories import search_kb_conn
from .settings import (
    DATABASE_URL,
    GUARDRAILS,
    INTENTS_POLICY,
    LLM_API_BASE,
    LLM_API_KEY,
    LLM_API_TIMEOUT_SEC,
    LLM_MODEL,
)

logger = logging.getLogger(__name__)

_INFIGO_FALLBACK: List[Tuple[str, str, str]] = [
    ("infigo-1", "services", "Infigo builds startup MVPs in 6-10 weeks and enterprise software with dedicated teams."),
    ("infigo-2", "process", "Process: share your idea, get a roadmap, design and build MVP, launch with support."),
    ("infigo-3", "contact", "Contact Infigo via the website contact form or book a 30-minute meeting on the contact page."),
]


class BudgetTracker:
    def __init__(self, monthly_budget: float) -> None:
        self.monthly_budget = monthly_budget
        self.monthly_spend: Dict[str, float] = defaultdict(float)

    def add(self, usd: float) -> None:
        month = dt.datetime.utcnow().strftime("%Y-%m")
        self.monthly_spend[month] += usd

    def snapshot(self) -> Tuple[str, float, bool]:
        month = dt.datetime.utcnow().strftime("%Y-%m")
        total = self.monthly_spend[month]
        alert = total >= (self.monthly_budget * GUARDRAILS["monthly_alert_percent"] / 100)
        return month, total, alert


class SimpleRetriever:
    @staticmethod
    def _fallback(query: str, k: int) -> List[RetrievalChunk]:
        tokens = set(query.lower().split())
        scored = []
        for doc_id, src, text in _INFIGO_FALLBACK:
            score = len(tokens.intersection(set(text.lower().split()))) / (len(tokens) + 1)
            scored.append((score, doc_id, src, text))
        scored.sort(reverse=True, key=lambda x: x[0])
        return [
            RetrievalChunk(id=d[1], source=d[2], text=d[3], score=float(round(d[0], 3)))
            for d in scored[:k]
        ]

    async def retrieve(self, query: str, k: int) -> List[RetrievalChunk]:
        if not DATABASE_URL:
            return self._fallback(query, k)
        try:
            async with db_connection(timeout=15.0) as conn:
                chunks = await search_kb_conn(conn, query, k, customer_id=None)
            if chunks:
                return chunks
        except Exception as exc:
            logger.warning("KB search failed: %s", exc)
        return self._fallback(query, k)


class IntentRouter:
    def route(self, text: str) -> str:
        t = text.lower()
        for keyword in INTENTS_POLICY["sensitive_keywords"]:
            if keyword in t:
                return "human_required"
        return "auto_answer"


class LLMClient:
    def __init__(self) -> None:
        self.api_enabled = bool(LLM_API_KEY and LLM_API_KEY.strip() and LLM_API_KEY != "replace-me")

    @staticmethod
    def _sanitize(answer: str) -> str:
        text = answer.strip()
        text = re.sub(
            r"(?i)\b(?:knowledge base|retrieved from|based on the)\b[,:]?\s*",
            "",
            text,
        )
        return text.strip() or answer.strip()

    async def answer(
        self,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int,
        user_message: str,
    ) -> tuple[str, str]:
        if not self.api_enabled:
            return (
                "The assistant is temporarily unavailable. Please use our contact form on infigosolutions.com.",
                "rules",
            )
        payload = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_output_tokens,
        }
        headers = {"Authorization": f"Bearer {LLM_API_KEY}"}
        timeout = httpx.Timeout(LLM_API_TIMEOUT_SEC, connect=min(10.0, LLM_API_TIMEOUT_SEC))
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{LLM_API_BASE.rstrip('/')}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
                raw = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
                if isinstance(raw, str) and raw.strip():
                    return self._sanitize(raw), "api"
        except Exception as exc:
            logger.warning("LLM API failed: %s", exc)
        return (
            "I could not reach the AI service. Please email us or use the contact form on our website.",
            "rules",
        )
