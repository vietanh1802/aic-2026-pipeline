"""Apply schema.sql, then the numbered steps on top of it.

Idempotent by construction — schema.sql is entirely IF NOT EXISTS — because the
API runs this on every startup and a second run must never lose data.

That property is also schema.sql's limit: a CREATE that is skipped cannot add a
column to a table that already exists. This file's original note said versioning
should wait until a column had to change shape. It has, so migrations.py now
runs after the baseline; see it for the version bookkeeping.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from app.db.connection import get_conn
from app.db.migrations import apply_steps

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

TABLES = (
    "answers",
    "audit_log",
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
        apply_steps(conn)
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
