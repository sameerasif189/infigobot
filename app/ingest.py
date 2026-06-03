"""Ingest text, files, and API URLs into RAG documents."""

from __future__ import annotations

import json
import re
from typing import Optional

import httpx

_MAX_BODY = 50_000
_ALLOWED_SUFFIXES = {".txt", ".md", ".csv", ".json", ".log"}


def extract_text_from_bytes(filename: str, data: bytes) -> str:
    name = (filename or "upload.txt").lower()
    if not any(name.endswith(s) for s in _ALLOWED_SUFFIXES):
        raise ValueError(f"Unsupported file type. Allowed: {', '.join(sorted(_ALLOWED_SUFFIXES))}")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("File must be UTF-8 text") from exc
    return text[:_MAX_BODY]


_SITE_FEED_TOPICS = [
    {
        "id": "invoices",
        "title": "Invoices and billing",
        "body": "Download invoices under Billing > Invoices. Unpaid invoices show status and due date.",
    },
    {
        "id": "orders",
        "title": "Order status",
        "body": "Track orders under Orders. Status values include pending, processing, shipped, and delivered.",
    },
    {
        "id": "tickets",
        "title": "Support tickets",
        "body": "Create tickets from Support or Help Center. Open tickets appear in your dashboard.",
    },
    {
        "id": "highest-bill",
        "title": "Highest bill and order totals",
        "body": "Ask the assistant about your highest invoice, largest order, or order totals. Answers use your signed-in account only.",
    },
    {
        "id": "chat",
        "title": "ERP AI support chat",
        "body": "Use the chat panel for billing, orders, and policy questions. Sign in as a customer to see your own ERP data.",
    },
]

_DEMO_FEED_BODY = json.dumps(
    {"title": "ERP Help API (demo)", "topics": _SITE_FEED_TOPICS[:3]},
    indent=2,
)

SITE_FEED_JSON = json.dumps(
    {"title": "ERP site knowledge feed", "topics": _SITE_FEED_TOPICS},
    indent=2,
)


def bundled_site_feed_json() -> str:
    return SITE_FEED_JSON[:_MAX_BODY]


def normalize_feed_url(url: str) -> str:
    """Map site root to the JSON site-feed endpoint for reliable polling."""
    u = url.strip()
    low = u.rstrip("/").lower()
    if low in (
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8000/",
        "http://127.0.0.1:8000/",
    ):
        return "http://127.0.0.1:8000/knowledge/site-feed"
    return u


async def fetch_api_feed(url: str) -> str:
    url = normalize_feed_url(url)
    low = url.rstrip("/").lower()
    if low.endswith("/knowledge/demo-feed"):
        return _DEMO_FEED_BODY[:_MAX_BODY]
    if low.endswith("/knowledge/site-feed"):
        try:
            timeout = httpx.Timeout(8.0, connect=4.0)
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "ERP-AI-Support-Agent/1.0"})
                resp.raise_for_status()
                return resp.text[:_MAX_BODY]
        except Exception:
            return bundled_site_feed_json()
    timeout = httpx.Timeout(15.0, connect=8.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": "ERP-AI-Support-Agent/1.0"})
        resp.raise_for_status()
        ctype = (resp.headers.get("content-type") or "").lower()
        raw = resp.text[:_MAX_BODY]
        if "json" in ctype or raw.strip().startswith(("{", "[")):
            try:
                parsed = json.loads(raw)
                return json.dumps(parsed, indent=2)[:_MAX_BODY]
            except json.JSONDecodeError:
                pass
        if "html" in ctype:
            raw = re.sub(r"<script[^>]*>.*?</script>", " ", raw, flags=re.I | re.S)
            raw = re.sub(r"<style[^>]*>.*?</style>", " ", raw, flags=re.I | re.S)
            raw = re.sub(r"<[^>]+>", " ", raw)
            raw = re.sub(r"\s+", " ", raw)
        return raw.strip()[:_MAX_BODY]


def normalize_title(title: Optional[str], fallback: str) -> str:
    t = (title or "").strip()
    return (t[:300] if t else fallback[:300])
