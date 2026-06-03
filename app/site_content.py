"""Load structured site content from bundled JSON or a public JSON URL."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Tuple

from .ingest import fetch_api_feed

logger = logging.getLogger(__name__)

_JSON_URL_CACHE: Dict[str, Tuple[str, float]] = {}
_JSON_CACHE_TTL = 1800

_DEFAULT_JSON = Path(__file__).resolve().parent.parent / "config" / "infigo_site_content.json"


def _format_content(data: Dict[str, Any]) -> str:
    lines = [
        f"Company: {data.get('company', '')}",
        f"Tagline: {data.get('tagline', '')}",
        "",
    ]
    services = data.get("services") or {}
    for key, block in services.items():
        if not isinstance(block, dict):
            continue
        lines.append(f"## {block.get('title', key)}")
        if block.get("summary"):
            lines.append(str(block["summary"]))
        for p in block.get("points") or []:
            lines.append(f"- {p}")
        lines.append("")
    if data.get("process"):
        lines.append("## Work process")
        for i, step in enumerate(data["process"], 1):
            lines.append(f"{i}. {step}")
        lines.append("")
    if data.get("capabilities"):
        lines.append("## Capabilities")
        for c in data["capabilities"]:
            lines.append(f"- {c}")
        lines.append("")
    contact = data.get("contact") or {}
    if contact:
        lines.append("## Contact")
        for k, v in contact.items():
            lines.append(f"- {k}: {v}")
        lines.append("")
    for faq in data.get("faqs") or []:
        if isinstance(faq, dict):
            lines.append(f"Q: {faq.get('q', '')}")
            lines.append(f"A: {faq.get('a', '')}")
            lines.append("")
    return "\n".join(lines).strip()


def load_bundled_json(path: Path | None = None) -> str:
    p = path or _DEFAULT_JSON
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return _format_content(data)
    except OSError as exc:
        logger.warning("Bundled site JSON missing %s: %s", p, exc)
        return ""


async def fetch_json_url(url: str) -> str:
    """Fetch public content.json from the React site (cached ~30 min)."""
    u = (url or "").strip()
    if not u:
        return ""
    now = time.time()
    hit = _JSON_URL_CACHE.get(u)
    if hit and (now - hit[1]) < _JSON_CACHE_TTL:
        return hit[0]
    raw = await fetch_api_feed(u)
    raw = raw.strip()
    text = ""
    if raw.startswith("{"):
        try:
            text = _format_content(json.loads(raw))
        except json.JSONDecodeError as exc:
            logger.warning("Invalid JSON from %s: %s", u, exc)
    if not text:
        text = raw[:12_000]
    _JSON_URL_CACHE[u] = (text, now)
    return text


async def load_site_content_json(*, file_path: str, fetch_url: str = "") -> str:
    """Bundled file and/or optional secondary URL."""
    if file_path:
        p = Path(file_path)
        if not p.is_absolute():
            p = Path(__file__).resolve().parent.parent / p
        text = load_bundled_json(p)
        if text:
            return text
    if fetch_url:
        return await fetch_json_url(fetch_url)
    return load_bundled_json()


async def resolve_site_context(
    *,
    json_url: str,
    runtime_enabled: bool,
    runtime_url: str,
    bundled_enabled: bool,
    bundled_path: str,
) -> tuple[str, str]:
    """Returns (text, source_label) for status/logging."""
    if json_url:
        text = await fetch_json_url(json_url)
        return text, "json_url"
    if bundled_enabled:
        text = await load_site_content_json(file_path=bundled_path, fetch_url="")
        return text, "bundled_json"
    if runtime_enabled and runtime_url:
        from .site_runtime import fetch_runtime_site

        text = await fetch_runtime_site(runtime_url)
        return text, "runtime_html"
    return "", "none"
