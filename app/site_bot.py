"""Public marketing-site chat (e.g. Infigo Solutions) — prompts, booking, contact handoff."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .settings import (
    SITE_BOOKING_URL,
    SITE_COMPANY_NAME,
    SITE_CONTACT_EMAIL,
    SITE_PROPOSAL_URL,
)

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "site_bot.json"
_DEFAULT: Dict[str, Any] = {
    "company_name": "Infigo Solutions",
    "booking_keywords": ["book", "schedule", "meeting", "calendly"],
    "proposal_keywords": ["proposal", "quote", "contact"],
}


def load_site_config() -> Dict[str, Any]:
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {**_DEFAULT, **data}
    except OSError:
        return dict(_DEFAULT)


def site_public_erp_uid() -> str:
    return "site:public"


def message_matches_keywords(message: str, keywords: List[str]) -> bool:
    ml = message.lower()
    return any(kw.lower() in ml for kw in keywords)


def detect_booking_intent(message: str) -> bool:
    cfg = load_site_config()
    return message_matches_keywords(message, cfg.get("booking_keywords") or [])


def detect_proposal_intent(message: str) -> bool:
    cfg = load_site_config()
    return message_matches_keywords(message, cfg.get("proposal_keywords") or [])


def build_site_erp_context(visitor: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    cfg = load_site_config()
    ctx: Dict[str, Any] = {
        "scope": "site",
        "company": SITE_COMPANY_NAME or cfg.get("company_name", "Infigo Solutions"),
        "source": "site_bot",
    }
    if visitor:
        if visitor.get("name"):
            ctx["visitor_name"] = visitor["name"]
        if visitor.get("email"):
            ctx["visitor_email"] = visitor["email"]
    return ctx


def build_site_system_prompt(*, visitor: Optional[Dict[str, str]] = None) -> str:
    cfg = load_site_config()
    company = SITE_COMPANY_NAME or cfg.get("company_name", "Infigo Solutions")
    tagline = cfg.get("tagline", "")
    persona = cfg.get(
        "persona",
        f"You are a helpful assistant for {company} on the public marketing website.",
    )
    max_sent = int(cfg.get("max_answer_sentences", 4))
    lines = [
        persona,
        f"Company: {company}.",
    ]
    if tagline:
        lines.append(f"Focus: {tagline}.")
    lines.extend(
        [
            "STRICT RULES:",
            "- Answer ONLY from the help articles provided and general company facts in this prompt.",
            "- Do NOT invent pricing, contracts, or legal commitments.",
            "- If unsure, say you can connect them with the team via the contact form or email.",
            f"- Keep replies concise (max {max_sent} short sentences). Professional, friendly tone.",
            "- NEVER mention ERP accounts, order numbers, invoices, or internal demo data.",
            "- NEVER say 'knowledge base', 'retrieved', or 'based on context'.",
            "- For booking or proposals, point to the booking link or contact email when provided in context.",
        ]
    )
    if SITE_CONTACT_EMAIL:
        lines.append(f"Official contact email: {SITE_CONTACT_EMAIL}.")
    if SITE_PROPOSAL_URL:
        lines.append(f"Proposal / contact page: {SITE_PROPOSAL_URL}.")
    if SITE_BOOKING_URL:
        lines.append(f"Meeting booking URL: {SITE_BOOKING_URL}.")
    if visitor and visitor.get("name"):
        lines.append(f"The visitor said their name is {visitor['name']}.")
    if visitor and visitor.get("email"):
        lines.append(f"The visitor email is {visitor['email']} (use only for scheduling context, do not repeat unnecessarily).")
    return "\n".join(lines) + "\n"


def build_site_user_prompt(
    message: str,
    kb_context: str,
    *,
    chat_history_block: str = "",
) -> str:
    return (
        f"Visitor question:\n{message}\n"
        f"{chat_history_block}\n"
        f"Help articles (use only if relevant):\n{kb_context or '(none)'}"
    )


def booking_reply(
    message: str,
    visitor: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """Deterministic booking answer when URL is configured."""
    if not SITE_BOOKING_URL or not detect_booking_intent(message):
        return None
    name = (visitor or {}).get("name", "").strip()
    email = (visitor or {}).get("email", "").strip()
    if not name or not email:
        return (
            "I can share our scheduling link. Please tell me your name and email in one message "
            '(for example: "Alex, alex@company.com") and I will send the booking link.'
        )
    return (
        f"Thanks {name}. Pick a time that works for you here: {SITE_BOOKING_URL}\n"
        "You will receive web conferencing details after you confirm."
    )


def proposal_reply(message: str) -> Optional[str]:
    if not detect_proposal_intent(message):
        return None
    parts = []
    if SITE_PROPOSAL_URL:
        parts.append(f"Share your project details via our contact page: {SITE_PROPOSAL_URL}")
    if SITE_CONTACT_EMAIL:
        parts.append(f"Or email us at {SITE_CONTACT_EMAIL}.")
    if not parts:
        return (
            "For a startup MVP or enterprise proposal, use the Contact section on this website "
            "or the 'Talk To Enterprise Team' / 'Get Startup Consultation' buttons."
        )
    return " ".join(parts) + " Our team will follow up to prepare for your meeting."


def site_response_meta(
    message: str,
    *,
    visitor: Optional[Dict[str, str]] = None,
) -> Dict[str, Optional[str]]:
    """Metadata for embed widget (booking button, contact)."""
    meta: Dict[str, Optional[str]] = {
        "booking_url": SITE_BOOKING_URL if detect_booking_intent(message) else None,
        "contact_email": SITE_CONTACT_EMAIL or None,
        "proposal_hint": (SITE_PROPOSAL_URL or SITE_CONTACT_EMAIL)
        if detect_proposal_intent(message)
        else None,
    }
    if meta["booking_url"] and visitor and visitor.get("name") and visitor.get("email"):
        pass  # URL exposed to widget; answer text handled by booking_reply or LLM
    return meta


def append_booking_link_if_needed(answer: str, message: str, visitor: Optional[Dict[str, str]] = None) -> str:
    if not SITE_BOOKING_URL or SITE_BOOKING_URL in answer:
        return answer
    if detect_booking_intent(message) and visitor and visitor.get("name") and visitor.get("email"):
        return answer.rstrip() + f"\n\nBook here: {SITE_BOOKING_URL}"
    return answer
