"""Load structured site content from bundled JSON or a public JSON URL."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

from .ingest import fetch_api_feed

logger = logging.getLogger(__name__)

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


async def load_site_content_json(*, file_path: str, fetch_url: str) -> str:
    """
    Priority:
    1) SITE_CONTENT_JSON file in repo (recommended for React sites)
    2) SITE_FETCH_URL — public JSON URL (e.g. https://infigosolutions.com/content.json)
    """
    if file_path:
        p = Path(file_path)
        if not p.is_absolute():
            p = Path(__file__).resolve().parent.parent / p
        text = load_bundled_json(p)
        if text:
            return text
    if fetch_url:
        raw = await fetch_api_feed(fetch_url)
        raw = raw.strip()
        if raw.startswith("{"):
            try:
                return _format_content(json.loads(raw))
            except json.JSONDecodeError:
                pass
        return raw[:12_000]
    return load_bundled_json()
