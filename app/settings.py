import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=True)
CONFIG_DIR = ROOT / "config"

IS_SERVERLESS = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name, default)
    return value.strip().strip('"').strip("'") if value else default


def _load_json(name: str) -> dict:
    with open(CONFIG_DIR / name, "r", encoding="utf-8") as f:
        return json.load(f)


GUARDRAILS = _load_json("guardrails.json")
INTENTS_POLICY = _load_json("intents_policy.json")

DATABASE_URL = _env("DATABASE_URL")
LLM_API_BASE = _env("LLM_API_BASE", "https://api.groq.com/openai/v1")
LLM_API_KEY = _env("LLM_API_KEY")
LLM_MODEL = _env("LLM_MODEL", "llama-3.1-8b-instant")
LLM_API_TIMEOUT_SEC = float(_env("LLM_API_TIMEOUT_SEC", "25"))
LLM_ORDER = _env("LLM_ORDER", "api")

CHAT_HISTORY_TURNS = int(_env("CHAT_HISTORY_TURNS", "6"))
INGEST_API_KEY = _env("INGEST_API_KEY", "")

RAG_VECTOR_ENABLED = _env("RAG_VECTOR_ENABLED", "true").lower() in ("1", "true", "yes")
RAG_RETRIEVAL_MODE = _env("RAG_RETRIEVAL_MODE", "hybrid")
RAG_CHUNK_SIZE_TOKENS = int(_env("RAG_CHUNK_SIZE_TOKENS", "400"))
RAG_CHUNK_OVERLAP_TOKENS = int(_env("RAG_CHUNK_OVERLAP_TOKENS", "60"))
RAG_VECTOR_TOP_K = int(_env("RAG_VECTOR_TOP_K", "8"))
EMBEDDING_API_BASE = _env("EMBEDDING_API_BASE", "https://api.openai.com/v1")
EMBEDDING_API_KEY = _env("EMBEDDING_API_KEY", "")
EMBEDDING_MODEL = _env("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIM = int(_env("EMBEDDING_DIM", "1536"))
EMBEDDING_BATCH_SIZE = int(_env("EMBEDDING_BATCH_SIZE", "32"))
EMBEDDING_TIMEOUT_SEC = float(_env("EMBEDDING_TIMEOUT_SEC", "60"))

SITE_BOT_ENABLED = _env("SITE_BOT_ENABLED", "true").lower() in ("1", "true", "yes")
PUBLIC_CHAT_API_KEY = _env("PUBLIC_CHAT_API_KEY", "")
SITE_COMPANY_NAME = _env("SITE_COMPANY_NAME", "Infigo Solutions")
SITE_CONTACT_EMAIL = _env("SITE_CONTACT_EMAIL", "")
SITE_BOOKING_URL = _env("SITE_BOOKING_URL", "")
SITE_PROPOSAL_URL = _env("SITE_PROPOSAL_URL", "https://infigosolutions.com/")
CORS_ALLOWED_ORIGINS = _env(
    "CORS_ALLOWED_ORIGINS",
    "https://infigosolutions.com,https://www.infigosolutions.com",
)
# Content source (pick one via env):
# - SITE_JSON_URL — public JSON on React site, e.g. https://infigosolutions.com/content.json (scenario 2)
# - SITE_RUNTIME_FETCH_ENABLED + SITE_FETCH_URL — live HTML fetch (scenario 1)
# - SITE_CONTENT_ENABLED + SITE_CONTENT_JSON — bundled file in API repo
SITE_JSON_URL = _env("SITE_JSON_URL", "")
SITE_RUNTIME_FETCH_ENABLED = _env("SITE_RUNTIME_FETCH_ENABLED", "false").lower() in (
    "1",
    "true",
    "yes",
)
SITE_FETCH_URL = _env("SITE_FETCH_URL", "https://infigosolutions.com/")
SITE_CONTENT_ENABLED = _env("SITE_CONTENT_ENABLED", "false").lower() in ("1", "true", "yes")
SITE_CONTENT_JSON = _env("SITE_CONTENT_JSON", "config/infigo_site_content.json")
