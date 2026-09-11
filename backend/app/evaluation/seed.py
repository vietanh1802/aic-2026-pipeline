"""Load a v2 benchmark seed file into the evaluation tables.

A seed file is one dataset (Round 1 or Round 2), its reference set, and every
query with its manually reviewed reference. Loading is idempotent — the JSON
is the source of truth, re-running only fills in what is missing — and an
edited file is refused rather than silently merged, so a change means a new
dataset version.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from app.db.connection import utcnow_iso


SEEDS_DIR = Path(__file__).resolve().parent / "seeds"
SCHEMA_VERSION = 2


def _content_sha256(queries : list[dict[str, Any]]) -> str :
    """Hash the canonicalised query list. Used when a seed file declares no
    source.sha256 of its own, so an edit is still detected on the next seed."""
    canonical = json.dumps(queries, ensure_ascii = False, sort_keys = True, separators = (",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate(seed : dict[str, Any], name : str) -> None :
    if (seed.get("schema_version") != SCHEMA_VERSION) :
        raise ValueError(f"{name}: expected schema_version {SCHEMA_VERSION}, got {seed.get('schema_version')}")

    dataset = seed["dataset"]
    queries = seed["queries"]

    if (len(queries) != int(dataset["query_count"])) :
        raise ValueError(f"{name}: query_count {dataset['query_count']} but {len(queries)} queries")

    seen_task_counts : dict[str, int] = {}
    for query in queries :
        seen_task_counts[query["task_type"]] = seen_task_counts.get(query["task_type"], 0) + 1
    if (seen_task_counts != dataset["task_counts"]) :
        raise ValueError(f"{name}: task_counts {dataset['task_counts']} but queries give {seen_task_counts}")

    keys = [query["id"] for query in queries]
    if (len(keys) != len(set(keys))) :
        raise ValueError(f"{name}: duplicate query id")

    for query in queries :
        reference = query["reference"]
        intervals = reference.get("valid_intervals")

        if (query["task_type"] == "TRAKE") :
            if (intervals is not None) :
                raise ValueError(f"{name}: {query['id']} is TRAKE but carries valid_intervals")
            continue

        if (not intervals) :
            raise ValueError(f"{name}: {query['id']} ({query['task_type']}) has no valid_intervals")
        if (reference.get("interval_count") != len(intervals)) :
            raise ValueError(
                f"{name}: {query['id']} interval_count {reference.get('interval_count')} "
                f"but {len(intervals)} intervals"
            )
        for interval in intervals :
            if (interval["start"] > interval["end"]) :
                raise ValueError(f"{name}: {query['id']} interval start {interval['start']} > end {interval['end']}")


def import_seed(conn : sqlite3.Connection, seed_path : Path) -> dict[str, Any] :
    seed = json.loads(seed_path.read_text(encoding = "utf-8"))
    _validate(seed, seed_path.name)

    dataset = seed["dataset"]
    reference_set = seed["reference_set"]
    queries = seed["queries"]

    source = dataset.get("source", {})
    source_sha256 = source.get("sha256") or _content_sha256(queries)

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
                dataset["slug"], dataset["version"], dataset["display_name"],
                dataset["query_count"], source.get("filename"), source_sha256, now,
            ),
        )
        dataset_row = conn.execute(
            "SELECT * FROM evaluation_datasets WHERE slug = ? AND version = ?",
            (dataset["slug"], dataset["version"]),
        ).fetchone()

        if (dataset_row["source_sha256"] != source_sha256) :
            raise ValueError(
                f"Dataset {dataset['version']} is already seeded from a different source. "
                f"Bump the version instead of editing a shipped seed."
            )

        conn.execute(
            """
            INSERT OR IGNORE INTO evaluation_reference_sets (
                dataset_id, version, label_semantics,
                interval_annotation, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                dataset_row["id"], reference_set["version"], reference_set["label_semantics"],
                reference_set.get("interval_annotation"), reference_set.get("notes"), now,
            ),
        )
        reference_set_row = conn.execute(
            "SELECT * FROM evaluation_reference_sets WHERE dataset_id = ? AND version = ?",
            (dataset_row["id"], reference_set["version"]),
        ).fetchone()

        for query in queries :
            conn.execute(
                """
                INSERT OR IGNORE INTO evaluation_queries (
                    dataset_id, query_key, ordinal, task_type, query_vi
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (dataset_row["id"], query["id"], query["ordinal"], query["task_type"], query["query_vi"]),
            )
            query_row = conn.execute(
                "SELECT * FROM evaluation_queries WHERE dataset_id = ? AND query_key = ?",
                (dataset_row["id"], query["id"]),
            ).fetchone()

            reference = query["reference"]
            intervals = reference.get("valid_intervals")
            trake_events = query.get("trake_events")
            conn.execute(
                """
                INSERT OR IGNORE INTO evaluation_references (
                    reference_set_id, query_id, video_id,
                    valid_intervals_json, interval_count, reference_frame_idx,
                    status, confidence, provenance, notes,
                    qa_answer, trake_events_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reference_set_row["id"], query_row["id"], reference["video_id"],
                    json.dumps(intervals, ensure_ascii = False) if intervals is not None else None,
                    reference.get("interval_count", 0),
                    reference.get("reference_frame_idx"),
                    reference["status"], reference.get("confidence"), reference.get("provenance"),
                    query.get("notes") or "",
                    query.get("qa_answer"),
                    json.dumps(trake_events, ensure_ascii = False) if trake_events else None,
                ),
            )

        conn.execute("COMMIT")
    except Exception :
        conn.execute("ROLLBACK")
        raise

    return {
        "dataset_version"       : dataset["version"],
        "dataset_id"            : int(dataset_row["id"]),
        "reference_set_version" : reference_set["version"],
        "reference_set_id"      : int(reference_set_row["id"]),
        "query_count"           : len(queries),
    }


def import_all_seeds(conn : sqlite3.Connection, seeds_dir : Path = SEEDS_DIR) -> list[dict[str, Any]] :
    return [import_seed(conn, path) for path in sorted(seeds_dir.glob("*.json"))]
