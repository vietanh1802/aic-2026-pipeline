from __future__ import annotations

import json
import queue
import sqlite3
import threading
import time
from typing import Any, Callable

from app.db.connection import get_conn, utcnow_iso
from app.evaluation.ensemble import evaluate_translated_ensemble_query
from app.evaluation.repository import get_results, get_run, update_counts
from app.evaluation.scoring import summarize_run_results
from app.translation import DEFAULT_TRANSLATION_POLICY, translate_vi_to_en
from app.version import SHORT_COMMIT, VERSION


_run_queue : queue.Queue[int] = queue.Queue()
_worker_lock = threading.Lock()
_worker_thread : threading.Thread | None = None


def interrupt_incomplete_runs(conn : sqlite3.Connection) -> int :
    """Mark work from a previous process as interrupted; never resume silently."""
    now = utcnow_iso()
    run_ids = [
        int(row["id"])
        for row in conn.execute(
            "SELECT id FROM evaluation_runs WHERE status IN ('queued', 'running', 'cancelling')"
        ).fetchall()
    ]
    if (not run_ids) :
        return 0

    placeholders = ",".join("?" for _ in run_ids)
    conn.execute("BEGIN IMMEDIATE")
    try :
        conn.execute(
            f"""
            UPDATE evaluation_query_results
            SET status = 'interrupted', finished_at = ?
            WHERE run_id IN ({placeholders}) AND status = 'running'
            """,
            (now, *run_ids),
        )
        conn.execute(
            f"""
            UPDATE evaluation_runs
            SET status = 'interrupted', updated_at = ?, finished_at = ?
            WHERE id IN ({placeholders})
            """,
            (now, now, *run_ids),
        )
        conn.execute("COMMIT")
    except Exception :
        conn.execute("ROLLBACK")
        raise
    return len(run_ids)


def _runtime_snapshot() -> dict[str, Any] :
    from app.preprocess import system_status

    status = system_status()
    return {
        "version"          : VERSION,
        "commit"           : SHORT_COMMIT,
        "device"           : status.get("device"),
        "active_models"    : status.get("active_models"),
        "ensemble_weights" : status.get("ensemble_weights"),
        "index_files"      : status.get("index_files"),
        "stale_files"      : status.get("stale_files"),
    }


def process_run(
    run_id : int,
    *,
    conn_factory : Callable[[], sqlite3.Connection] = get_conn,
    translate_fn = None,
    evaluate_fn = None,
    runtime_snapshot_fn = _runtime_snapshot,
) -> None :
    conn = conn_factory()
    try :
        now = utcnow_iso()
        claimed = conn.execute(
            """
            UPDATE evaluation_runs
            SET status = 'running', started_at = COALESCE(started_at, ?), updated_at = ?
            WHERE id = ? AND status = 'queued'
            """,
            (now, now, run_id),
        ).rowcount
        if (claimed != 1) :
            return

        run = get_run(conn, run_id)
        if (run is None) :
            return
        translation_policy = str(
            (run.get("configuration") or {}).get("translation_policy")
            or DEFAULT_TRANSLATION_POLICY
        )

        try :
            runtime = runtime_snapshot_fn()
        except Exception as exc :
            runtime = {"error" : f"{type(exc).__name__}: {exc}"}
        conn.execute(
            "UPDATE evaluation_runs SET runtime_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(runtime, ensure_ascii = False), utcnow_iso(), run_id),
        )

        rows = conn.execute(
            """
            SELECT * FROM evaluation_query_results
            WHERE run_id = ? AND status != 'completed'
            ORDER BY ordinal
            """,
            (run_id,),
        ).fetchall()

        for index, row in enumerate(rows, start = 1) :
            state = conn.execute(
                "SELECT status FROM evaluation_runs WHERE id = ?", (run_id,)
            ).fetchone()["status"]
            if (state == "cancelling") :
                now = utcnow_iso()
                conn.execute(
                    "UPDATE evaluation_runs SET status = 'cancelled', finished_at = ?, updated_at = ? WHERE id = ?",
                    (now, now, run_id),
                )
                return
            if (state != "running") :
                return

            print(f"[evaluation] run {run_id}: {row['query_key']} ({index}/{len(rows)})")
            started_at = utcnow_iso()
            attempt_started = time.monotonic()
            conn.execute(
                """
                UPDATE evaluation_query_results
                SET status = 'running', started_at = ?, finished_at = NULL, error = NULL
                WHERE id = ?
                """,
                (started_at, row["id"]),
            )

            query_en = None
            translation_ms = None
            try :
                if (translate_fn is None) :
                    query_en, translation_ms = translate_vi_to_en(
                        row["query_vi"],
                        policy = translation_policy,
                    )
                else :
                    query_en, translation_ms = translate_fn(row["query_vi"])
                conn.execute(
                    """
                    UPDATE evaluation_query_results
                    SET query_en = ?, translation_ms = ?
                    WHERE id = ?
                    """,
                    (query_en, float(translation_ms), row["id"]),
                )

                if (evaluate_fn is None) :
                    result = evaluate_translated_ensemble_query(
                        row["query_vi"],
                        query_en,
                        row["reference_video"],
                        translation_ms = float(translation_ms),
                        translation_policy = translation_policy,
                    )
                else :
                    result = evaluate_fn(
                        row["query_vi"],
                        query_en,
                        row["reference_video"],
                        translation_ms = float(translation_ms),
                    )
                metrics = result["metrics"]
                timings = result["timings"]
                conn.execute(
                    """
                    UPDATE evaluation_query_results
                    SET status = 'completed', query_en = ?,
                        predicted_top1_video = ?, reference_video_rank = ?,
                        hit_at_1 = ?, hit_at_3 = ?, hit_at_5 = ?, hit_at_10 = ?,
                        reciprocal_rank = ?, not_retrieved = ?,
                        translation_ms = ?, retrieval_ms = ?, aggregation_ms = ?, total_ms = ?,
                        frame_results_json = ?, ranked_videos_json = ?,
                        error = NULL, finished_at = ?
                    WHERE id = ?
                    """,
                    (
                        query_en,
                        metrics["predicted_top1_video"],
                        metrics["reference_video_rank"],
                        int(metrics["hit_at_1"]),
                        int(metrics["hit_at_3"]),
                        int(metrics["hit_at_5"]),
                        int(metrics["hit_at_10"]),
                        float(metrics["reciprocal_rank"]),
                        int(metrics["not_retrieved"]),
                        float(timings["translation_ms"]),
                        float(timings["retrieval_ms"]),
                        float(timings["aggregation_ms"]),
                        float(timings["total_ms"]),
                        json.dumps(result["frame_results"], ensure_ascii = False),
                        json.dumps(result["ranked_videos"], ensure_ascii = False),
                        utcnow_iso(),
                        row["id"],
                    ),
                )
            except Exception as exc :
                total_ms = (time.monotonic() - attempt_started) * 1000.0
                conn.execute(
                    """
                    UPDATE evaluation_query_results
                    SET status = 'failed', query_en = ?, translation_ms = ?, total_ms = ?,
                        error = ?, finished_at = ?
                    WHERE id = ?
                    """,
                    (
                        query_en,
                        float(translation_ms) if translation_ms is not None else None,
                        round(total_ms, 3),
                        f"{type(exc).__name__}: {exc}",
                        utcnow_iso(),
                        row["id"],
                    ),
                )

            update_counts(conn, run_id)

        results = get_results(conn, run_id)
        summary = summarize_run_results(results)
        failed_count = sum(1 for result in results if result["status"] == "failed")
        final_status = "partial" if failed_count else "completed"
        now = utcnow_iso()
        conn.execute(
            """
            UPDATE evaluation_runs
            SET status = ?, summary_json = ?, finished_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (final_status, json.dumps(summary, ensure_ascii = False), now, now, run_id),
        )
    except Exception as exc :
        try :
            now = utcnow_iso()
            conn.execute(
                """
                UPDATE evaluation_runs
                SET status = 'failed', error = ?, finished_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (f"{type(exc).__name__}: {exc}", now, now, run_id),
            )
        finally :
            raise
    finally :
        conn.close()


def _worker_loop() -> None :
    while True :
        run_id = _run_queue.get()
        try :
            process_run(run_id)
        except Exception as exc :
            print(f"[evaluation] run {run_id} failed: {type(exc).__name__}: {exc}")
        finally :
            _run_queue.task_done()


def enqueue_run(run_id : int) -> None :
    global _worker_thread
    with _worker_lock :
        if (_worker_thread is None or not _worker_thread.is_alive()) :
            _worker_thread = threading.Thread(
                target = _worker_loop,
                name = "evaluation-worker",
                daemon = True,
            )
            _worker_thread.start()
    _run_queue.put(int(run_id))
