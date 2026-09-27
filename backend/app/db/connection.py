"""SQLite access.

One connection helper so nobody forgets a PRAGMA. Spec §4 fixes WAL and a
five-second busy timeout; foreign keys are added because the schema relies on
ON DELETE CASCADE and SQLite leaves enforcement off by default.

The path is resolved on every call rather than captured at import, so one
process can be pointed at a different file per test.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from app.config import load_settings


def db_path() -> Path:
    return load_settings().db_path


def get_conn() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # isolation_level=None means autocommit; statements that need a transaction
    # open one explicitly with BEGIN IMMEDIATE. The alternative is a driver that
    # silently holds a transaction open until someone remembers to commit.
    # check_same_thread=False: get_db() mở một kết nối RIÊNG cho mỗi request rồi
    # đóng ngay, nên không có chuyện hai request dùng chung một kết nối. Nhưng
    # FastAPI chạy dependency đồng bộ ở một luồng threadpool rồi chạy endpoint ở
    # luồng KHÁC, nên kết nối bị tạo ở luồng này mà dùng ở luồng kia — và sqlite3
    # cấm điều đó theo mặc định:
    #
    #   sqlite3.ProgrammingError: SQLite objects created in a thread can only be
    #   used in that same thread.
    #
    # Lỗi chỉ hiện ra khi có nhiều request liên tiếp, vì lúc đó threadpool mới
    # phân ra nhiều luồng — chạy một mình thì thường trúng cùng một luồng và
    # không bao giờ thấy.
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_db() -> Iterator[sqlite3.Connection]:
    """FastAPI dependency: one connection per request."""
    conn = get_conn()
    try:
        yield conn
    finally:
        conn.close()


def utcnow_iso() -> str:
    """The one timestamp format in the system: 2026-08-10T14:30:00Z.

    It sorts lexicographically in the same order it sorts chronologically, which
    is what lets `expires_at > :now` be a string comparison rather than a parse.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
