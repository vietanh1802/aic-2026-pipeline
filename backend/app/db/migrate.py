"""Apply schema.sql.

Idempotent by construction — the whole file is IF NOT EXISTS — because the API
runs this on every startup and a second run must never lose data. There is no
version table yet: there is one schema and it only grows. When a column has to
change shape, that is the moment to add versioning, not before.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from app.db.connection import get_conn

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

TABLES = (
    "answers",
    "edit_requests",
    "packs",
    "presence",
    "sessions",
    "settings",
    "tasks",
    "users",
    "video_cache",
)


def migrate(conn: sqlite3.Connection | None = None) -> list[str]:
    """Create anything missing. Returns the table names present afterwards."""
    own = conn is None
    conn = conn if conn is not None else get_conn()
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        return [r["name"] for r in rows]
    finally:
        if own:
            conn.close()


if __name__ == "__main__":
    from app.db.connection import db_path

    print(f"{db_path()}")
    for name in migrate():
        print(f"  {name}")
