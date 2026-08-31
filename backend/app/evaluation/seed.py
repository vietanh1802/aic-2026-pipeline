from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.db.connection import utcnow_iso


ROUND1_SEED_PATH = Path(__file__).resolve().parent / "seeds" / "round1-v1.json"


def import_seed(
    conn : sqlite3.Connection,
    seed_path : Path = ROUND1_SEED_PATH,
) -> dict[str, Any] :
    seed = json.loads(seed_path.read_text(encoding = "utf-8"))
    if (seed.get("schema_version") != 1) :
        raise ValueError("Unsupported evaluation seed schema_version")

    dataset = seed["dataset"]
    reference_set = seed["reference_set"]
    queries = seed["queries"]
    if (len(queries) != int(dataset["query_count"])) :
        raise ValueError("Seed query_count does not match queries")

    now = utcnow_iso()
    conn.execute("BEGIN IMMEDIATE")
    try :
        conn.execute(
            """
            INSERT OR IGNORE INTO evaluation_datasets (
                slug, version, display_name, query_count,
                source_filename, source_sha256, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dataset["slug"],
                dataset["version"],
                dataset["display_name"],
                dataset["query_count"],
                dataset.get("source", {}).get("filename"),
                dataset.get("source", {}).get("sha256"),
                now,
            ),
        )
        dataset_row = conn.execute(
            "SELECT * FROM evaluation_datasets WHERE slug = ? AND version = ?",
            (dataset["slug"], dataset["version"]),
        ).fetchone()
        if (dataset_row is None) :
            raise RuntimeError("Failed to load evaluation dataset after insert")

        source_sha256 = dataset.get("source", {}).get("sha256")
        if (dataset_row["source_sha256"] != source_sha256) :
            raise ValueError(
                f"Dataset {dataset['version']} already exists with a different source hash"
            )

        conn.execute(
            """
            INSERT OR IGNORE INTO evaluation_reference_sets (
                dataset_id, version, label_semantics,
                interval_annotation, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                dataset_row["id"],
                reference_set["version"],
                reference_set["label_semantics"],
                reference_set.get("interval_annotation"),
                reference_set.get("notes"),
                now,
            ),
        )
        reference_set_row = conn.execute(
            """
            SELECT * FROM evaluation_reference_sets
            WHERE dataset_id = ? AND version = ?
            """,
            (dataset_row["id"], reference_set["version"]),
        ).fetchone()
        if (reference_set_row is None) :
            raise RuntimeError("Failed to load evaluation reference set after insert")

        for query in queries :
            conn.execute(
                """
                INSERT OR IGNORE INTO evaluation_queries (
                    dataset_id, query_key, ordinal, task_type, query_vi
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    dataset_row["id"],
                    query["id"],
                    query["ordinal"],
                    query["task_type"],
                    query["query_vi"],
                ),
            )
            query_row = conn.execute(
                """
                SELECT * FROM evaluation_queries
                WHERE dataset_id = ? AND query_key = ?
                """,
                (dataset_row["id"], query["id"]),
            ).fetchone()
            if (query_row is None) :
                raise RuntimeError(f"Failed to load evaluation query {query['id']}")

            reference = query["reference"]
            trake_events = query.get("trake_events")
            conn.execute(
                """
                INSERT OR IGNORE INTO evaluation_references (
                    reference_set_id, query_id, video_id,
                    reference_frame_idx, valid_start_frame, valid_end_frame,
                    status, confidence, provenance, qa_answer, trake_events_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reference_set_row["id"],
                    query_row["id"],
                    reference["video_id"],
                    reference.get("reference_frame_idx"),
                    reference.get("valid_start_frame"),
                    reference.get("valid_end_frame"),
                    reference["status"],
                    reference.get("confidence"),
                    reference.get("provenance"),
                    query.get("qa_answer"),
                    json.dumps(trake_events, ensure_ascii = False) if trake_events else None,
                ),
            )

        conn.execute("COMMIT")
    except Exception :
        conn.execute("ROLLBACK")
        raise

    return {
        "dataset_id"           : int(dataset_row["id"]),
        "dataset_version"      : dataset["version"],
        "reference_set_id"     : int(reference_set_row["id"]),
        "reference_set_version" : reference_set["version"],
        "query_count"          : len(queries),
    }
