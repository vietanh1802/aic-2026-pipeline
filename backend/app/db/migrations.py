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
    (
        2,
        (
            """
            CREATE TABLE evaluation_datasets (
                id INTEGER PRIMARY KEY,
                slug TEXT NOT NULL,
                version TEXT NOT NULL,
                display_name TEXT NOT NULL,
                query_count INTEGER NOT NULL,
                source_filename TEXT,
                source_sha256 TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(slug, version)
            )
            """,
            """
            CREATE TABLE evaluation_queries (
                id INTEGER PRIMARY KEY,
                dataset_id INTEGER NOT NULL REFERENCES evaluation_datasets(id) ON DELETE CASCADE,
                query_key TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                task_type TEXT NOT NULL,
                query_vi TEXT NOT NULL,
                UNIQUE(dataset_id, query_key)
            )
            """,
            """
            CREATE TABLE evaluation_reference_sets (
                id INTEGER PRIMARY KEY,
                dataset_id INTEGER NOT NULL REFERENCES evaluation_datasets(id) ON DELETE CASCADE,
                version TEXT NOT NULL,
                label_semantics TEXT NOT NULL,
                interval_annotation TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(dataset_id, version)
            )
            """,
            """
            CREATE TABLE evaluation_references (
                id INTEGER PRIMARY KEY,
                reference_set_id INTEGER NOT NULL REFERENCES evaluation_reference_sets(id) ON DELETE CASCADE,
                query_id INTEGER NOT NULL REFERENCES evaluation_queries(id) ON DELETE CASCADE,
                video_id TEXT NOT NULL,
                reference_frame_idx INTEGER,
                valid_start_frame INTEGER,
                valid_end_frame INTEGER,
                status TEXT NOT NULL,
                confidence TEXT,
                provenance TEXT,
                qa_answer TEXT,
                trake_events_json TEXT,
                UNIQUE(reference_set_id, query_id)
            )
            """,
        ),
    ),
    (
        3,
        (
            """
            CREATE TABLE evaluation_runs (
                id INTEGER PRIMARY KEY,
                dataset_id INTEGER NOT NULL REFERENCES evaluation_datasets(id) ON DELETE CASCADE,
                reference_set_id INTEGER NOT NULL REFERENCES evaluation_reference_sets(id) ON DELETE CASCADE,
                strategy TEXT NOT NULL,
                video_ranking_policy TEXT NOT NULL,
                translator TEXT NOT NULL,
                status TEXT NOT NULL,
                query_count INTEGER NOT NULL,
                completed_count INTEGER NOT NULL DEFAULT 0,
                failed_count INTEGER NOT NULL DEFAULT 0,
                created_by_user_id INTEGER,
                configuration_json TEXT NOT NULL,
                runtime_json TEXT,
                summary_json TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                updated_at TEXT NOT NULL,
                resume_count INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE TABLE evaluation_query_results (
                id INTEGER PRIMARY KEY,
                run_id INTEGER NOT NULL REFERENCES evaluation_runs(id) ON DELETE CASCADE,
                query_id INTEGER NOT NULL REFERENCES evaluation_queries(id) ON DELETE CASCADE,
                query_key TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                task_type TEXT NOT NULL,
                status TEXT NOT NULL,
                query_vi TEXT NOT NULL,
                query_en TEXT,
                translator TEXT NOT NULL,
                reference_video TEXT NOT NULL,
                reference_frame_idx INTEGER,
                predicted_top1_video TEXT,
                reference_video_rank INTEGER,
                hit_at_1 INTEGER,
                hit_at_3 INTEGER,
                hit_at_5 INTEGER,
                hit_at_10 INTEGER,
                reciprocal_rank REAL,
                not_retrieved INTEGER,
                translation_ms REAL,
                retrieval_ms REAL,
                aggregation_ms REAL,
                total_ms REAL,
                frame_results_json TEXT,
                ranked_videos_json TEXT,
                error TEXT,
                started_at TEXT,
                finished_at TEXT,
                UNIQUE(run_id, query_id)
            )
            """,
            "CREATE INDEX idx_evaluation_runs_status ON evaluation_runs(status)",
            "CREATE INDEX idx_evaluation_query_results_run ON evaluation_query_results(run_id, ordinal)",
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
