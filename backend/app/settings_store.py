"""The §4.2 settings table: its keys, its defaults, and its types.

A key that is not in DEFAULTS does not exist. Writing an unknown key is a 400
rather than an insert, because a typo'd key that persists quietly is a setting
the admin believes they changed and did not.

SQLite stores every value as TEXT; DEFAULTS carries the type each one is cast
back to, so `export.header` reads as a bool and `export.rows_per_query` as an int.
"""
from __future__ import annotations

import sqlite3
from typing import Any


# Spec 2026-08-19 §9. Adding a key here without adding it to the spec is how
# the two drift apart — change the spec first.
#
# edit_mode, cache.limit_bytes and frames.strip_radius went with the features
# they configured: this branch has no edit-request flow and no local video store.
DEFAULTS: dict[str, tuple[Any, type]] = {
    "export.filename_pattern": ("query-{id}-{type}.csv", str),
    "export.delimiter": (",", str),
    "export.header": (False, bool),
    "export.line_ending": ("LF", str),
    "export.encoding": ("utf-8", str),
    "export.rows_per_query": (100, int),
}

ENUMS: dict[str, set[str]] = {
    "export.line_ending": {"LF", "CRLF"},
}

# What a member's browser may read. Everything else is admin-only. Slice 3 will
# widen this when the Export screen needs the format keys — until something
# needs a key, it stays out.
PUBLIC_KEYS = ("export.rows_per_query",)


class UnknownSettingError(KeyError):
    """A key that is not in DEFAULTS."""


class InvalidSettingError(ValueError):
    """A value of the wrong type, outside the key's enum, or above a hard ceiling."""


def _encode(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _decode(key: str, raw: str) -> Any:
    kind = DEFAULTS[key][1]
    if kind is bool:
        return raw == "true"
    if kind is int:
        return int(raw)
    return raw


def _coerce(key: str, value: Any) -> Any:
    """Validate one incoming value, or raise InvalidSettingError."""
    kind = DEFAULTS[key][1]

    if kind is bool:
        if not isinstance(value, bool):
            raise InvalidSettingError(f"{key} must be true or false")
        return value

    if kind is int:
        # bool is a subclass of int in Python; True must not pass as 1 here.
        if isinstance(value, bool) or not isinstance(value, int):
            raise InvalidSettingError(f"{key} must be a whole number")
        if value < 0:
            raise InvalidSettingError(f"{key} must not be negative")
        return value

    if not isinstance(value, str):
        raise InvalidSettingError(f"{key} must be a string")
    if key in ENUMS and value not in ENUMS[key]:
        raise InvalidSettingError(f"{key} must be one of: {', '.join(sorted(ENUMS[key]))}")
    return value


def all_settings(conn: sqlite3.Connection) -> dict[str, Any]:
    """Every key, stored value where one exists and the default where not."""
    stored = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}
    return {
        key: _decode(key, stored[key]) if key in stored else default
        for key, (default, _) in DEFAULTS.items()
    }


def public_settings(conn: sqlite3.Connection) -> dict[str, Any]:
    everything = all_settings(conn)
    return {key: everything[key] for key in PUBLIC_KEYS}


def set_many(conn: sqlite3.Connection, updates: dict[str, Any]) -> dict[str, Any]:
    """Validate everything, then write everything. Returns the full settings.

    Validation runs over the whole payload before the first write, so a request
    with one bad key changes nothing at all.
    """
    for key in updates:
        if key not in DEFAULTS:
            raise UnknownSettingError(key)
    coerced = {key: _coerce(key, value) for key, value in updates.items()}

    conn.execute("BEGIN IMMEDIATE")
    try:
        for key, value in coerced.items():
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, _encode(value)),
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return all_settings(conn)
