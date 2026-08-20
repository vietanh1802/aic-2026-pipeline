"""Bearer tokens, stored in the sessions table.

The lifetime is settings.session_ttl_days — configuration, not a constant, so a
deployment can shorten it without a code change. Long by default on purpose: a
round can run for hours and a token that expires in the middle of one is a live
failure, while a long-lived token on a five-person internal tool is the cheaper
risk. Revocation is by deleting rows, which is why this is a table and not a JWT.

Timestamps use utcnow_iso() throughout, and that format sorts lexicographically
in the same order it sorts chronologically — so `expires_at > :now` as a string
comparison is correct, not a shortcut.
"""
from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from app.config import load_settings
from app.db.connection import utcnow_iso


def _expiry() -> str:
    days = load_settings().session_ttl_days
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_session(conn: sqlite3.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, user_id, utcnow_iso(), _expiry()),
    )
    return token


def resolve_session(conn: sqlite3.Connection, token: str) -> sqlite3.Row | None:
    """The users row behind a token, or None if the token is dead.

    Dead covers all three ways: unknown, expired, or belonging to a user who has
    since been disabled.
    """
    return conn.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
        "WHERE s.token = ? AND s.expires_at > ? AND u.disabled = 0",
        (token, utcnow_iso()),
    ).fetchone()


def delete_session(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def delete_sessions_for_user(
    conn: sqlite3.Connection, user_id: int, keep: str | None = None
) -> int:
    """Revoke every session for a user, optionally sparing the caller's own.

    `keep` is what makes a password change not log you out of the tab you changed
    it in, while still logging out whoever else was holding a token.
    """
    if keep is None:
        cur = conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    else:
        cur = conn.execute(
            "DELETE FROM sessions WHERE user_id = ? AND token != ?", (user_id, keep)
        )
    return cur.rowcount
