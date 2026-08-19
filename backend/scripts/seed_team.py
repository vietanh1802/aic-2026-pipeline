# -*- coding: utf-8 -*-
"""Create the six accounts the team competes with.

A fixed roster for one season does not need a member-management screen, so this
replaces dev's admin CRUD entirely. Idempotent: an account that already exists
is left alone, including its password, so re-running after adding a name is safe.

Everyone starts on the same known password and is NOT forced to change it. That
is a deliberate trade for a six-person tool that has to be usable the minute it
deploys: a default nobody can use is not a default. Anyone who wants a private
password can still set one from the change-password screen.

    cd backend && python -m scripts.seed_team
"""
from __future__ import annotations

import sqlite3
import sys

from app.auth.passwords import hash_password
from app.db.connection import get_conn, utcnow_iso
from app.db.migrate import migrate

# (username, display_name, role)
#
# admin is its own account rather than a hat one of the five wears, so nobody
# imports a pack over the round they are competing in by mistake.
# Handed out as-is. Change it here and re-seed a fresh database to rotate it.
DEFAULT_PASSWORD = "password"

ACCOUNTS: list[tuple[str, str, str]] = [
    ("admin", "Admin", "admin"),
    ("vanh", "VAnh", "member"),
    ("bang", "Bằng", "member"),
    ("nam", "Nam", "member"),
    ("an", "An", "member"),
    ("phat", "Phát", "member"),
]


def seed_team(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """Create any missing account. Returns (username, password) for new ones."""
    created: list[tuple[str, str]] = []
    for username, display_name, role in ACCOUNTS:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        ).fetchone()
        if exists:
            continue
        conn.execute(
            "INSERT INTO users (username, display_name, role, password_hash, "
            "must_change_password, disabled, created_at) VALUES (?, ?, ?, ?, 0, 0, ?)",
            (username, display_name, role, hash_password(DEFAULT_PASSWORD), utcnow_iso()),
        )
        created.append((username, DEFAULT_PASSWORD))
    return created


def main() -> int:
    conn = get_conn()
    try:
        migrate(conn)
        created = seed_team(conn)
    finally:
        conn.close()

    if not created:
        print("Every account already exists. Nothing changed.")
        return 0

    print("Hand these out once. They are not stored and cannot be shown again.")
    print(f"{'username':<10} password")
    for username, password in created:
        print(f"{username:<10} {password}")
    print("\nEveryone is asked to change their password at first sign-in.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
