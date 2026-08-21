"""Numbered schema steps, applied on top of schema.sql.

schema.sql is the baseline and is deliberately all IF NOT EXISTS, which is also
exactly why it cannot add a column to a table that already exists: the CREATE
is skipped and the new column never appears. That is what this file is for.

`PRAGMA user_version` records how far a database has been taken. Each step runs
at most once, in order, in its own transaction, so a step that fails halfway
leaves the version behind it rather than a half-migrated table.

migrate.py's original note said versioning should arrive the moment a column has
to change shape rather than before. `packs.deleted_at` is that moment.
"""
from __future__ import annotations

import sqlite3

# (version, statements). Never renumber and never edit a shipped step — a
# database that already ran step 1 will not run it again, so changing it only
# splits new deployments from old ones. Add a new step instead.
STEPS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (
        1,
        (
            # Soft delete, for two reasons. A hard DELETE cannot work as-is:
            # tasks.pack_id and presence.task_id carry no ON DELETE CASCADE, so
            # removing a pack mid-round raises a foreign key error. And for a
            # tool whose actual complaint was losing a round's work,
            # unrecoverable deletion is the wrong direction to build in.
            "ALTER TABLE packs ADD COLUMN deleted_at TEXT",
        ),
    ),
)


def current_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def apply_steps(conn: sqlite3.Connection) -> int:
    """Run every step this database has not seen. Returns the version reached."""
    version = current_version(conn)
    for step_version, statements in STEPS:
        if step_version <= version:
            continue
        conn.execute("BEGIN IMMEDIATE")
        try:
            for statement in statements:
                conn.execute(statement)
            # PRAGMA takes no bound parameters, so this is interpolated. The
            # value is an int from the tuple above, never from a request.
            conn.execute(f"PRAGMA user_version = {int(step_version)}")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        version = step_version
    return version
