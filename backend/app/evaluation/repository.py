from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.db.connection import utcnow_iso
from app.evaluation.config import RunConfig, to_configuration
from app.evaluation.ensemble import MODELS, STRATEGY_NAME, STRATEGY_SHARED, TOP_K, TOP_M, USE_RERANK
from app.evaluation.flags import flags_for, select_rows
from app.evaluation.scoring import INTERVAL_SCORING_POLICY, VIDEO_RANKING_POLICY
from app.translation import (
    DEFAULT_TRANSLATION_POLICY,
    normalize_translation_policy,
    translator_id_for_policy,
)

ACTIVE_STATUSES = ("queued", "running", "cancelling")
_ACTIVE_PLACEHOLDERS = ", ".join("?" for _ in ACTIVE_STATUSES)


def _loads(value : str | None) -> Any :
    return json.loads(value) if value else None


def _bool_or_none(value : Any) -> bool | None :
    return bool(value) if value is not None else None


def _run_payload(row : sqlite3.Row) -> dict[str, Any] :
    return {
        "id"                      : int(row["id"]),
        "dataset_id"              : int(row["dataset_id"]),
        "dataset_version"         : row["dataset_version"],
        "reference_set_id"        : int(row["reference_set_id"]),
        "reference_set_version"   : row["reference_set_version"],
        "strategy"                : row["strategy"],
        "video_ranking_policy"    : row["video_ranking_policy"],
        "interval_scoring_policy" : row["interval_scoring_policy"],
        "translator"              : row["translator"],
        "status"                  : row["status"],
        "query_count"             : int(row["query_count"]),
        "completed_count"         : int(row["completed_count"]),
        "failed_count"            : int(row["failed_count"]),
        "created_by_user_id"      : row["created_by_user_id"],
        "configuration"           : _loads(row["configuration_json"]),
        "runtime"                 : _loads(row["runtime_json"]),
        "summary"                 : _loads(row["summary_json"]),
        "task_type_summary"       : _loads(row["task_type_summary_json"]),
        "error"                   : row["error"],
        "created_at"              : row["created_at"],
        "started_at"              : row["started_at"],
        "finished_at"             : row["finished_at"],
        "updated_at"              : row["updated_at"],
        "resume_count"            : int(row["resume_count"]),
    }


def _result_payload(row : sqlite3.Row) -> dict[str, Any] :
    """Per-query result WITHOUT the heavy frame_results / ranked_videos blobs.

    Those are only attached by get_result() for the single-query view — the
    list endpoint is polled every couple of seconds and 25+ full candidate
    lists per response is megabytes of payload the table never renders.
    """
    return {
        "id"                     : int(row["id"]),
        "run_id"                 : int(row["run_id"]),
        "query_id"               : int(row["query_id"]),
        "query_key"              : row["query_key"],
        "ordinal"                : int(row["ordinal"]),
        "task_type"              : row["task_type"],
        "status"                 : row["status"],
        "query_vi"               : row["query_vi"],
        "query_en"               : row["query_en"],
        "translator"             : row["translator"],
        "reference_video"        : row["reference_video"],
        "reference_intervals"    : _loads(row["reference_intervals_json"]),
        "reference_frame_idx"    : row["reference_frame_idx"],
        "reference_notes"        : row["reference_notes"],
        "predicted_top1_video"   : row["predicted_top1_video"],
        "reference_video_rank"   : row["reference_video_rank"],
        "hit_at_1"               : _bool_or_none(row["hit_at_1"]),
        "hit_at_3"               : _bool_or_none(row["hit_at_3"]),
        "hit_at_5"               : _bool_or_none(row["hit_at_5"]),
        "hit_at_10"              : _bool_or_none(row["hit_at_10"]),
        "reciprocal_rank"        : row["reciprocal_rank"],
        "not_retrieved"          : _bool_or_none(row["not_retrieved"]),
        "interval_hit"           : _bool_or_none(row["interval_hit"]),
        "interval_rank"          : row["interval_rank"],
        "matched_interval_index" : row["matched_interval_index"],
        "final_score"            : row["final_score"],
        "translation_ms"         : row["translation_ms"],
        "retrieval_ms"           : row["retrieval_ms"],
        "aggregation_ms"         : row["aggregation_ms"],
        "total_ms"               : row["total_ms"],
        "error"                  : row["error"],
        "started_at"             : row["started_at"],
        "finished_at"            : row["finished_at"],
        "extra"                  : _loads(row["extra_json"]),
    }


def list_datasets(conn : sqlite3.Connection) -> list[dict[str, Any]] :
    datasets = conn.execute(
        "SELECT * FROM evaluation_datasets ORDER BY id DESC"
    ).fetchall()
    output = []
    for dataset in datasets :
        refs = conn.execute(
            """
            SELECT id, version, label_semantics, interval_annotation, notes, created_at
            FROM evaluation_reference_sets
            WHERE dataset_id = ?
            ORDER BY id DESC
            """,
            (dataset["id"],),
        ).fetchall()
        output.append({
            "id"             : int(dataset["id"]),
            "slug"           : dataset["slug"],
            "version"        : dataset["version"],
            "display_name"   : dataset["display_name"],
            "query_count"    : int(dataset["query_count"]),
            "source_filename": dataset["source_filename"],
            "source_sha256"  : dataset["source_sha256"],
            "created_at"     : dataset["created_at"],
            "reference_sets" : [dict(row) for row in refs],
        })
    return output


def get_dataset(conn : sqlite3.Connection, dataset_id : int) -> dict[str, Any] | None :
    dataset = conn.execute(
        "SELECT * FROM evaluation_datasets WHERE id = ?", (dataset_id,)
    ).fetchone()
    if (dataset is None) :
        return None

    queries = conn.execute(
        """
        SELECT q.id, q.query_key, q.ordinal, q.task_type, q.query_vi,
               r.video_id, r.interval_count, r.reference_frame_idx, r.notes
        FROM evaluation_queries q
        LEFT JOIN evaluation_references r ON r.query_id = q.id
        WHERE q.dataset_id = ?
        ORDER BY q.ordinal
        """,
        (dataset_id,),
    ).fetchall()
    refs = conn.execute(
        """
        SELECT id, version, label_semantics, interval_annotation, notes, created_at
        FROM evaluation_reference_sets
        WHERE dataset_id = ?
        ORDER BY id DESC
        """,
        (dataset_id,),
    ).fetchall()
    return {
        "id"             : int(dataset["id"]),
        "slug"           : dataset["slug"],
        "version"        : dataset["version"],
        "display_name"   : dataset["display_name"],
        "query_count"    : int(dataset["query_count"]),
        "source_filename": dataset["source_filename"],
        "source_sha256"  : dataset["source_sha256"],
        "created_at"     : dataset["created_at"],
        "reference_sets" : [dict(row) for row in refs],
        "queries"        : [dict(row) for row in queries],
    }


def find_active_run(conn : sqlite3.Connection) -> dict[str, Any] | None :
    """The single run currently queued, running, or cancelling. The worker is
    one thread with one queue, so a second run would only sit behind this one
    while still competing with live search — the router refuses it instead."""
    row = conn.execute(
        f"SELECT id FROM evaluation_runs WHERE status IN ({_ACTIVE_PLACEHOLDERS}) ORDER BY id LIMIT 1",
        ACTIVE_STATUSES,
    ).fetchone()
    return get_run(conn, int(row["id"])) if row is not None else None


def create_run(
    conn : sqlite3.Connection,
    dataset_version : str,
    reference_set_version : str,
    created_by_user_id : int | None,
    translation_policy : str = DEFAULT_TRANSLATION_POLICY,
    config : RunConfig | None = None,
    extra_configuration : dict[str, Any] | None = None,
) -> dict[str, Any] :
    """config = None is the legacy run: one Gemini translation policy, fixed models. A RunConfig
    makes a configured run (shared search, cached text); its legacy flat keys are still written so
    the existing Benchmark page reads it."""
    if (config is None) :
        selected_policy = normalize_translation_policy(translation_policy)
        translator_id = translator_id_for_policy(selected_policy)
    else :
        if (config.task_mode != "ensemble") :
            raise ValueError(f"task_mode {config.task_mode} is not available yet")
        selected_policy = config.text_policy
        translator_id = f"cache:{config.text_policy}"

    dataset = conn.execute(
        "SELECT * FROM evaluation_datasets WHERE version = ?",
        (dataset_version,),
    ).fetchone()
    if (dataset is None) :
        raise ValueError(f"Unknown evaluation dataset version: {dataset_version}")

    reference_set = conn.execute(
        "SELECT * FROM evaluation_reference_sets WHERE dataset_id = ? AND version = ?",
        (dataset["id"], reference_set_version),
    ).fetchone()
    if (reference_set is None) :
        raise ValueError(f"Unknown evaluation reference set: {reference_set_version}")

    if (config is None) :
        configuration = {
            "models"             : MODELS,
            "top_k"              : TOP_K,
            "top_m"              : TOP_M,
            "use_rerank"         : USE_RERANK,
            "translation_policy" : selected_policy,
        }
        strategy = STRATEGY_NAME
    else :
        configuration = {**to_configuration(config), **(extra_configuration or {})}
        strategy = STRATEGY_SHARED
    now = utcnow_iso()
    conn.execute("BEGIN IMMEDIATE")
    try :
        cursor = conn.execute(
            """
            INSERT INTO evaluation_runs (
                dataset_id, reference_set_id, strategy, video_ranking_policy,
                interval_scoring_policy, translator, status, query_count,
                completed_count, failed_count, created_by_user_id,
                configuration_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'queued', ?, 0, 0, ?, ?, ?, ?)
            """,
            (
                dataset["id"], reference_set["id"], strategy,
                VIDEO_RANKING_POLICY, INTERVAL_SCORING_POLICY, translator_id,
                dataset["query_count"], created_by_user_id,
                json.dumps(configuration, ensure_ascii = False), now, now,
            ),
        )
        run_id = int(cursor.lastrowid)

        rows = conn.execute(
            """
            SELECT q.id, q.query_key, q.ordinal, q.task_type, q.query_vi,
                   r.video_id, r.valid_intervals_json, r.reference_frame_idx, r.notes
            FROM evaluation_queries q
            JOIN evaluation_references r ON r.query_id = q.id
            WHERE q.dataset_id = ? AND r.reference_set_id = ?
            ORDER BY q.ordinal
            """,
            (dataset["id"], reference_set["id"]),
        ).fetchall()
        if (len(rows) != int(dataset["query_count"])) :
            raise RuntimeError("Evaluation reference set does not cover every dataset query")

        # A configured run may cover a subset (task types, excluded flags). The count the run
        # reports is the number of queries it will actually score.
        flags_by_key : dict[str, list[str]] = {}
        if (config is not None) :
            keyed = [{**dict(row), "dataset_version" : dataset_version, "video_id" : row["video_id"]} for row in rows]
            keep = {r["query_key"] for r in select_rows(keyed, config)}
            rows = [row for row in rows if row["query_key"] in keep]
            conn.execute("UPDATE evaluation_runs SET query_count = ? WHERE id = ?", (len(rows), run_id))
        for row in rows :
            flags_by_key[row["query_key"]] = flags_for(dataset_version, row["query_key"], row["video_id"])

        # Freeze the intervals and note onto each result row so a later edit to
        # the reference set cannot change what this run was scored against.
        conn.executemany(
            """
            INSERT INTO evaluation_query_results (
                run_id, query_id, query_key, ordinal, task_type, status,
                query_vi, translator, reference_video,
                reference_intervals_json, reference_frame_idx, reference_notes, extra_json
            ) VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    run_id, row["id"], row["query_key"], row["ordinal"], row["task_type"],
                    row["query_vi"], translator_id, row["video_id"],
                    row["valid_intervals_json"], row["reference_frame_idx"], row["notes"] or "",
                    json.dumps({"flags" : flags_by_key[row["query_key"]]}) if config is not None else None,
                )
                for row in rows
            ],
        )
        conn.execute("COMMIT")
    except Exception :
        conn.execute("ROLLBACK")
        raise

    run = get_run(conn, run_id)
    if (run is None) :
        raise RuntimeError("Failed to load evaluation run after insert")
    return run


def get_run(conn : sqlite3.Connection, run_id : int) -> dict[str, Any] | None :
    row = conn.execute(
        """
        SELECT r.*, d.version AS dataset_version, rs.version AS reference_set_version
        FROM evaluation_runs r
        JOIN evaluation_datasets d ON d.id = r.dataset_id
        JOIN evaluation_reference_sets rs ON rs.id = r.reference_set_id
        WHERE r.id = ?
        """,
        (run_id,),
    ).fetchone()
    return _run_payload(row) if row is not None else None


def list_runs(conn : sqlite3.Connection, limit : int = 50) -> list[dict[str, Any]] :
    rows = conn.execute(
        """
        SELECT r.*, d.version AS dataset_version, rs.version AS reference_set_version
        FROM evaluation_runs r
        JOIN evaluation_datasets d ON d.id = r.dataset_id
        JOIN evaluation_reference_sets rs ON rs.id = r.reference_set_id
        ORDER BY r.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [_run_payload(row) for row in rows]


def get_results(conn : sqlite3.Connection, run_id : int) -> list[dict[str, Any]] :
    rows = conn.execute(
        "SELECT * FROM evaluation_query_results WHERE run_id = ? ORDER BY ordinal",
        (run_id,),
    ).fetchall()
    return [_result_payload(row) for row in rows]


def get_result(conn : sqlite3.Connection, run_id : int, query_key : str) -> dict[str, Any] | None :
    row = conn.execute(
        "SELECT * FROM evaluation_query_results WHERE run_id = ? AND query_key = ?",
        (run_id, query_key),
    ).fetchone()
    if (row is None) :
        return None
    payload = _result_payload(row)
    payload["frame_results"] = _loads(row["frame_results_json"])
    payload["ranked_videos"] = _loads(row["ranked_videos_json"])

    # qa_answer and trake_events live on the reference, not frozen onto the
    # result. The detail panel shows them (labelled "not scored"), so join
    # them in here rather than widen every result row.
    reference = conn.execute(
        """
        SELECT r.qa_answer, r.trake_events_json
        FROM evaluation_references r
        JOIN evaluation_runs run ON run.reference_set_id = r.reference_set_id
        WHERE run.id = ? AND r.query_id = ?
        """,
        (run_id, row["query_id"]),
    ).fetchone()
    payload["qa_answer"] = reference["qa_answer"] if reference is not None else None
    payload["trake_events"] = _loads(reference["trake_events_json"]) if reference is not None else None
    return payload


def update_counts(conn : sqlite3.Connection, run_id : int) -> None :
    row = conn.execute(
        """
        SELECT
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_count,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count
        FROM evaluation_query_results
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchone()
    conn.execute(
        "UPDATE evaluation_runs SET completed_count = ?, failed_count = ?, updated_at = ? WHERE id = ?",
        (int(row["completed_count"] or 0), int(row["failed_count"] or 0), utcnow_iso(), run_id),
    )


def request_cancel(conn : sqlite3.Connection, run_id : int) -> dict[str, Any] | None :
    run = get_run(conn, run_id)
    if (run is None) :
        return None
    now = utcnow_iso()
    if (run["status"] == "queued") :
        conn.execute(
            "UPDATE evaluation_runs SET status = 'cancelled', finished_at = ?, updated_at = ? WHERE id = ?",
            (now, now, run_id),
        )
    elif (run["status"] == "running") :
        conn.execute(
            "UPDATE evaluation_runs SET status = 'cancelling', updated_at = ? WHERE id = ?",
            (now, run_id),
        )
    return get_run(conn, run_id)


def resume_run(conn : sqlite3.Connection, run_id : int) -> dict[str, Any] | None :
    run = get_run(conn, run_id)
    if (run is None) :
        return None
    if (run["status"] not in {"interrupted", "partial", "cancelled", "failed"}) :
        raise ValueError(f"Run {run_id} cannot resume from status {run['status']}")

    now = utcnow_iso()
    conn.execute("BEGIN IMMEDIATE")
    try :
        conn.execute(
            """
            UPDATE evaluation_query_results
            SET status = 'queued', query_en = NULL,
                predicted_top1_video = NULL, reference_video_rank = NULL,
                hit_at_1 = NULL, hit_at_3 = NULL, hit_at_5 = NULL, hit_at_10 = NULL,
                reciprocal_rank = NULL, not_retrieved = NULL,
                interval_hit = NULL, interval_rank = NULL,
                matched_interval_index = NULL, final_score = NULL,
                translation_ms = NULL, retrieval_ms = NULL, aggregation_ms = NULL,
                total_ms = NULL, frame_results_json = NULL, ranked_videos_json = NULL,
                error = NULL, started_at = NULL, finished_at = NULL
            WHERE run_id = ? AND status != 'completed'
            """,
            (run_id,),
        )
        completed = conn.execute(
            "SELECT COUNT(*) FROM evaluation_query_results WHERE run_id = ? AND status = 'completed'",
            (run_id,),
        ).fetchone()[0]
        conn.execute(
            """
            UPDATE evaluation_runs
            SET status = 'queued', completed_count = ?, failed_count = 0,
                summary_json = NULL, task_type_summary_json = NULL, error = NULL,
                finished_at = NULL, updated_at = ?, resume_count = resume_count + 1
            WHERE id = ?
            """,
            (completed, now, run_id),
        )
        conn.execute("COMMIT")
    except Exception :
        conn.execute("ROLLBACK")
        raise
    return get_run(conn, run_id)
