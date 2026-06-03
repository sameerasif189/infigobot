#!/usr/bin/env python3
"""Run a .sql file against DATABASE_URL (no psql required).

Usage:
  py scripts/apply_sql.py scripts/init_schema.sql
  py scripts/apply_sql.py scripts/migrate_auth_rag.sql
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ImportError:
        pass


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: py scripts/apply_sql.py <path-to.sql>")

    _load_env()
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn or dsn == "postgresql://...":
        raise SystemExit(
            "DATABASE_URL is missing or still a placeholder.\n"
            "1. Copy .env.example to .env\n"
            "2. Paste your Neon connection string from https://console.neon.tech\n"
            "   (Dashboard → your project → Connection details → pooled connection string)\n"
            "3. Re-run this script."
        )

    sql_path = Path(sys.argv[1])
    if not sql_path.is_file():
        raise SystemExit(f"SQL file not found: {sql_path}")

    sql = sql_path.read_text(encoding="utf-8")
    if "neon.tech" not in dsn and "localhost" in dsn:
        print("Warning: DATABASE_URL looks like localhost — did you paste the Neon URL?")

    import psycopg

    print(f"Applying {sql_path.name} …")
    with psycopg.connect(dsn, connect_timeout=30) as conn:
        conn.execute(sql)
        conn.commit()
    print("Done.")


if __name__ == "__main__":
    main()
