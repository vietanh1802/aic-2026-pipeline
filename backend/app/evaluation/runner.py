"""The run engine: one background daemon thread, one queue, one run at a time.

Each query is translated and retrieved OUTSIDE any transaction (a Gemini call
plus an ensemble search is seconds of work that must not hold a write lock),
then its whole result row is written in a single BEGIN IMMEDIATE / COMMIT so a
crash mid-query can never leave a half-scored row.
"""
from __future__ import annotations

import json
import os
import queue
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from app.db.connection import get_conn, utcnow_iso
from app.evaluation import cues, text_cache, text_measures, trake
from app.evaluation.config import config_from_configuration
from app.evaluation.diagnostics import interval_gap
from app.evaluation.coverage import provenance, video_coverage
from app.evaluation.ensemble import evaluate_translated_ensemble_query, evaluate_with_config
from app.evaluation.repository import get_results, get_run, update_counts
from app.evaluation.scoring import summarize_run
from app.translation import DEFAULT_TRANSLATION_POLICY, translate_vi_to_en
from app.version import SHORT_COMMIT, VERSION


_run_queue : queue.Queue[int] = queue.Queue()
_worker_lock = threading.Lock()
_worker_thread : threading.Thread | None = None


def interrupt_incomplete_runs(conn : sqlite3.Connection) -> int :
    """Mark work left mid-flight by a previous process as interrupted. It is
    never resumed automatically — an admin decides."""
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


def _fps_of(video : str) -> float :
    from app.preprocess import fps_for_video
    return fps_for_video(video)


def _final_status(completed_count : int, failed_count : int) -> str :
    if (completed_count == 0) :
        return "failed"
    if (failed_count) :
        return "partial"
    return "completed"


def _write_completed_result(
    conn : sqlite3.Connection,
    result_id : int,
    query_en : str,
    result : dict[str, Any],
    extra : dict[str, Any] | None = None,
) -> None :
    video = result["video_metrics"]
    interval = result["interval_metrics"]
    timings = result["timings"]
    interval_hit = interval["interval_hit"]
    conn.execute("BEGIN IMMEDIATE")
    try :
        conn.execute(
            """
            UPDATE evaluation_query_results
            SET status = 'completed', query_en = ?,
                predicted_top1_video = ?, reference_video_rank = ?,
                hit_at_1 = ?, hit_at_3 = ?, hit_at_5 = ?, hit_at_10 = ?,
                reciprocal_rank = ?, not_retrieved = ?,
                interval_hit = ?, interval_rank = ?, matched_interval_index = ?, final_score = ?,
                translation_ms = ?, retrieval_ms = ?, aggregation_ms = ?, total_ms = ?,
                frame_results_json = ?, ranked_videos_json = ?,
                error = NULL, finished_at = ?
            WHERE id = ?
            """,
            (
                query_en,
                video["predicted_top1_video"], video["reference_video_rank"],
                int(video["hit_at_1"]), int(video["hit_at_3"]),
                int(video["hit_at_5"]), int(video["hit_at_10"]),
                float(video["reciprocal_rank"]), int(video["not_retrieved"]),
                None if interval_hit is None else int(interval_hit),
                interval["interval_rank"], interval["matched_interval_index"],
                interval["final_score"],
                float(timings["translation_ms"]), float(timings["retrieval_ms"]),
                float(timings["aggregation_ms"]), float(timings["total_ms"]),
                json.dumps(result["frame_results"], ensure_ascii = False),
                json.dumps(result["ranked_videos"], ensure_ascii = False),
                utcnow_iso(), result_id,
            ),
        )
        if (extra) :
            # Merge into what create_run froze (the label flags) instead of replacing it.
            current = conn.execute("SELECT extra_json FROM evaluation_query_results WHERE id = ?", (result_id,)).fetchone()
            merged = {**(json.loads(current["extra_json"]) if current["extra_json"] else {}), **extra}
            conn.execute(
                "UPDATE evaluation_query_results SET extra_json = ? WHERE id = ?",
                (json.dumps(merged, ensure_ascii = False), result_id),
            )
        conn.execute("COMMIT")
    except Exception :
        conn.execute("ROLLBACK")
        raise


def _write_failed_result(
    conn : sqlite3.Connection,
    result_id : int,
    query_en : str | None,
    translation_ms : float | None,
    total_ms : float,
    error : str,
) -> None :
    conn.execute("BEGIN IMMEDIATE")
    try :
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
                round(total_ms, 3), error, utcnow_iso(), result_id,
            ),
        )
        conn.execute("COMMIT")
    except Exception :
        conn.execute("ROLLBACK")
        raise


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

        config = config_from_configuration(run.get("configuration"))

        try :
            runtime = runtime_snapshot_fn()
            if (config is not None) :
                runtime["provenance"] = provenance(
                    conn, run, text_cache.planned_digests(conn, config, run["dataset_version"])
                )
        except Exception as exc :
            runtime = {"error" : f"{type(exc).__name__}: {exc}"}
        conn.execute(
            "UPDATE evaluation_runs SET runtime_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(runtime, ensure_ascii = False), utcnow_iso(), run_id),
        )

        if (config is not None and not _prefetch_texts(conn, run, config)) :
            return
        cue_map = cues.load_cues(run["dataset_version"]) if (config is not None and config.text_filter.sources) else {}
        announced_annotation_error = False

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
                _finalize(conn, run_id, "cancelled")
                return
            if (state != "running") :
                return

            print(f"[evaluation] run {run_id}: {row['query_key']} ({index}/{len(rows)})")

            # A single atomic marker so interrupt_incomplete_runs can see this
            # query was in flight if the process dies during the compute below.
            conn.execute(
                """
                UPDATE evaluation_query_results
                SET status = 'running', started_at = ?, finished_at = NULL, error = NULL
                WHERE id = ?
                """,
                (utcnow_iso(), row["id"]),
            )

            valid_intervals = (
                json.loads(row["reference_intervals_json"])
                if row["reference_intervals_json"]
                else None
            )
            attempt_started = time.monotonic()
            query_en = None
            translation_ms = None
            extra = None
            trake_events = None
            try :
                if (config is not None and config.task_mode == "trake_n") :
                    # One text per event, each through the chosen policy on its own (replay only).
                    trake_events = trake.reference_events(conn, run, row)
                    cached_events = [
                        text_cache.get_text(conn, config.text_policy, e["description_vi"], row["task_type"])
                        for e in trake_events
                    ]
                    query_en, translation_ms = " | ".join(c.text for c in cached_events), 0.0
                    extra = {
                        "text_policy"    : config.text_policy,
                        "cache_digests"  : [c.digest for c in cached_events],
                        "video_coverage" : video_coverage(row["reference_video"]),
                    }
                elif (config is not None) :
                    # Replay only: the text was recorded before the first query, so retrieval
                    # never reaches an LLM or the network.
                    cached = text_cache.get_text(conn, config.text_policy, row["query_vi"], row["task_type"])
                    query_en, translation_ms = cached.text, 0.0
                    extra = {
                        "text_policy"  : config.text_policy,
                        "cache_digest" : cached.digest,
                        "check_units"  : cached.check_units,
                        "text_provider": cached.provider,
                        "video_coverage" : video_coverage(row["reference_video"]),
                    }
                elif (translate_fn is None) :
                    query_en, translation_ms = translate_vi_to_en(
                        row["query_vi"], policy = translation_policy
                    )
                else :
                    query_en, translation_ms = translate_fn(row["query_vi"])

                if (evaluate_fn is None and trake_events is not None) :
                    result = trake.evaluate_trake_n(
                        row["query_vi"], [c.text for c in cached_events], row["reference_video"], trake_events, config,
                    )
                    extra["trake"] = result["trake"]
                    if (result["trake"]["missing_labels"]) :
                        print(f"[evaluation] {row['query_key']}: no per-event reference frame for "
                              f"{result['trake']['missing_labels']}; scored at video level only")
                elif (evaluate_fn is None and config is not None) :
                    result = evaluate_with_config(
                        row["query_vi"], query_en, row["reference_video"], valid_intervals,
                        config, text_ms = 0.0,
                    )
                elif (evaluate_fn is None) :
                    result = evaluate_translated_ensemble_query(
                        row["query_vi"], query_en, row["reference_video"], valid_intervals,
                        translation_ms = float(translation_ms),
                        translation_policy = translation_policy,
                    )
                else :
                    result = evaluate_fn(
                        row["query_vi"], query_en, row["reference_video"], valid_intervals,
                        translation_ms = float(translation_ms),
                    )
                if (config is not None and extra is not None) :
                    # Coverage of the loaded OCR and ASR artifacts for the reference video, and the
                    # annotation blocks. measure_query never raises: whatever fails is recorded under
                    # text_signal_errors and the query keeps its ranking and its metrics.
                    side, side_errors = text_measures.measure_query(
                        result["frame_results"], row["reference_video"], valid_intervals,
                        result["video_metrics"]["reference_video_rank"], cue_map.get(row["query_key"], {}),
                        annotate = bool(config.text_filter.sources) and trake_events is None,
                        asr_mode = config.text_filter.asr_mode,
                    )
                    extra.update(side)
                    if (result.get("model_timings")) :
                        extra["model_timings"] = result["model_timings"]
                    # How far the closest returned frame of the reference video was from the valid
                    # interval (None for TRAKE). Its own narrow try, like the other side measures.
                    try :
                        gap = interval_gap(result["frame_results"], row["reference_video"], valid_intervals, _fps_of(row["reference_video"]))
                        if (gap is not None) :
                            extra["interval_gap"] = gap
                    except Exception as exc :
                        side_errors.append({"part" : "interval_gap", "error_type" : type(exc).__name__, "message" : str(exc)[ : 300]})
                    if (side_errors) :
                        extra["text_signal_errors"] = side_errors
                        if (not announced_annotation_error) :
                            announced_annotation_error = True
                            print(f"[evaluation] text signal side measure failed (recorded, query kept): "
                                  f"{side_errors[0]['error_type']}: {side_errors[0]['message']}")
                _write_completed_result(conn, int(row["id"]), query_en, result, extra)
            except Exception as exc :
                total_ms = (time.monotonic() - attempt_started) * 1000.0
                _write_failed_result(
                    conn, int(row["id"]), query_en, translation_ms, total_ms,
                    f"{type(exc).__name__}: {exc}",
                )

            update_counts(conn, run_id)

        # A cancel that landed while the final query was still running would
        # otherwise be overwritten by the finished summary below.
        if (get_run(conn, run_id)["status"] == "cancelling") :
            _finalize(conn, run_id, "cancelled")
            return

        results = get_results(conn, run_id)
        completed_count = sum(1 for result in results if result["status"] == "completed")
        failed_count = sum(1 for result in results if result["status"] == "failed")
        _finalize(conn, run_id, _final_status(completed_count, failed_count))
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


def _prefetch_texts(conn : sqlite3.Connection, run : dict[str, Any], config) -> bool :
    """Fill the text cache for a configured run before any retrieval. Returns False after marking
    the run failed when that is impossible (missing key, provider error), so the failure is one
    clear message on the run instead of one error per query."""
    report = text_cache.preflight(conn, [config], [run["dataset_version"]])
    try :
        text_cache.ensure_ready(report)
        text_cache.prefetch(conn, report["_missing_items"], run["id"])
    except (text_cache.PreflightBlocked, text_cache.PrefetchError) as exc :
        now = utcnow_iso()
        conn.execute(
            "UPDATE evaluation_runs SET status = 'failed', error = ?, finished_at = ?, updated_at = ? WHERE id = ?",
            (f"{type(exc).__name__}: {exc}", now, now, run["id"]),
        )
        return False
    return True


def _finalize(conn : sqlite3.Connection, run_id : int, final_status : str) -> None :
    """Write the terminal status plus a summary over whatever ran. A cancelled
    run gets real partial numbers too, not a blank summary."""
    summary = summarize_run(get_results(conn, run_id))
    now = utcnow_iso()
    conn.execute(
        """
        UPDATE evaluation_runs
        SET status = ?, summary_json = ?, task_type_summary_json = ?,
            finished_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            final_status,
            json.dumps(summary["headline"], ensure_ascii = False),
            json.dumps(summary["by_task_type"], ensure_ascii = False),
            now, now, run_id,
        ),
    )


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
                target = _worker_loop, name = "evaluation-worker", daemon = True
            )
            _worker_thread.start()
    _run_queue.put(int(run_id))


@contextmanager
def _db_path_env(db_path : str | Path) -> Iterator[None] :
    """get_conn() reads the path from AIC_DB_PATH on every call; point it at one file for a block."""
    previous = os.environ.get("AIC_DB_PATH")
    os.environ["AIC_DB_PATH"] = str(db_path)
    try :
        yield
    finally :
        if (previous is None) :
            os.environ.pop("AIC_DB_PATH", None)
        else :
            os.environ["AIC_DB_PATH"] = previous


def run_config_inprocess(config, dataset_slug : str, db_path : str | Path) -> dict[str, Any] :
    """Run one (configuration, dataset) pair to completion in this process and return the run row.

    For the stage-2 script and for tests: no HTTP, no worker thread, the same process_run the API
    uses. Migrates the database, seeds the benchmark files (idempotent) and takes the newest
    dataset version of the slug. Raises PreflightBlocked when a needed text is not cached and
    needs a key that is not configured; fetchable texts are fetched by process_run before the
    first query."""
    from app.db.connection import get_conn
    from app.db.migrate import migrate
    from app.evaluation.repository import create_run
    from app.evaluation.seed import import_all_seeds

    with _db_path_env(db_path) :
        conn = get_conn()
        try :
            migrate(conn)
            import_all_seeds(conn)
            text_cache.import_seed_caches(conn)
            dataset = conn.execute(
                "SELECT id, version FROM evaluation_datasets WHERE slug = ? ORDER BY id DESC LIMIT 1",
                (dataset_slug,),
            ).fetchone()
            if (dataset is None) :
                raise ValueError(f"Unknown dataset slug: {dataset_slug}")
            reference_set = conn.execute(
                "SELECT version FROM evaluation_reference_sets WHERE dataset_id = ? ORDER BY id DESC LIMIT 1",
                (dataset["id"],),
            ).fetchone()
            text_cache.ensure_ready(text_cache.preflight(conn, [config], [dataset["version"]]))
            run = create_run(conn, dataset["version"], reference_set["version"], None, config = config)
        finally :
            conn.close()
        process_run(run["id"])
        conn = get_conn()
        try :
            return get_run(conn, run["id"])
        finally :
            conn.close()
