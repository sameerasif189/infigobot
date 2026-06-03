#!/usr/bin/env python3
"""Seed Infigo KB into Neon. Run from infigobot/: python scripts/seed_infigo_kb.py"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)

SEED = ROOT / "config" / "infigo_kb_seed.md"


async def main() -> None:
    from app.db import close_db_pool, get_pool, init_db_pool
    from app.ingest import normalize_title
    from app.repositories import insert_rag_document
    from app.settings import DATABASE_URL

    if not DATABASE_URL:
        print("Set DATABASE_URL in infigobot/.env")
        sys.exit(1)
    body = SEED.read_text(encoding="utf-8")
    await init_db_pool()
    pool = get_pool()
    if not pool:
        sys.exit(1)
    doc = await insert_rag_document(
        pool,
        owner_user_id=None,
        title=normalize_title("Infigo Solutions website knowledge", "seed"),
        body=body,
        source_type="text",
        source_ref=str(SEED),
        category="infigo",
    )
    print(f"OK document id={doc.get('id')}")
    if __import__("app.settings", fromlist=["EMBEDDING_API_KEY"]).EMBEDDING_API_KEY:
        try:
            from app.db_util import db_connection
            from app.rag_vector import reindex_all_conn

            async with db_connection(timeout=180.0) as conn:
                print("Reindex:", await reindex_all_conn(conn))
        except Exception as exc:
            print("Reindex skipped:", exc)
    await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
