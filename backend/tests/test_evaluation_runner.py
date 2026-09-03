from __future__ import annotations

import sqlite3
from pathlib import Path

from app.db.migrations import apply_steps, current_version
from app.evaluation.repository import create_run, get_results, get_run, request_cancel, resume_run
from app.evaluation.runner import interrupt_incomplete_runs, process_run
from app.evaluation.scoring import summarize_run_results
from app.evaluation.seed import import_seed


def _conn(path : Path) -> sqlite3.Connection :
    conn = sqlite3.connect(path, isolation_level = None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE TABLE IF NOT EXISTS packs (id INTEGER PRIMARY KEY)")
    apply_steps(conn)
    return conn


def _setup(path : Path) -> int :
    conn = _conn(path)
    try :
        import_seed(conn)
        run = create_run(conn, "round1-v1", "r1-manual-v1", created_by_user_id = 7)
        return int(run["id"])
    finally :
        conn.close()


def _fake_result(query_vi : str, query_en : str, reference_video : str, *, translation_ms : float) -> dict :
    rank = 1 if query_vi.endswith("1") else 3
    videos = [{"rank" : 1, "video_id" : "WRONG"}]
    if (rank == 1) :
        videos[0] = {"rank" : 1, "video_id" : reference_video}
    else :
        videos.extend([
            {"rank" : 2, "video_id" : "OTHER"},
            {"rank" : 3, "video_id" : reference_video},
        ])
    return {
        "frame_results" : [{"video" : videos[0]["video_id"], "frame" : "f1"}],
        "ranked_videos" : videos,
        "metrics" : {
            "predicted_top1_video" : videos[0]["video_id"],
            "reference_video_rank" : rank,
            "hit_at_1" : rank == 1,
            "hit_at_3" : True,
            "hit_at_5" : True,
            "hit_at_10" : True,
            "reciprocal_rank" : 1.0 / rank,
            "not_retrieved" : False,
        },
        "timings" : {
            "translation_ms" : translation_ms,
            "retrieval_ms" : 20.0,
            "aggregation_ms" : 1.0,
            "total_ms" : translation_ms + 21.0,
        },
    }


def test_batch2_migration_and_run_creation(tmp_path : Path) -> None :
    path = tmp_path / "evaluation.db"
    run_id = _setup(path)
    conn = _conn(path)
    try :
        assert current_version(conn) == 3
        run = get_run(conn, run_id)
        assert run is not None
        assert run["status"] == "queued"
        assert run["query_count"] == 25
        assert run["configuration"] == {
            "models" : ["beit3", "clip"],
            "top_k" : 100,
            "top_m" : 50,
            "use_rerank" : True,
            "translation_policy" : "visual_faithful",
        }
        results = get_results(conn, run_id)
        assert len(results) == 25
        assert all(result["status"] == "queued" for result in results)
    finally :
        conn.close()


def test_runner_completes_all_queries_and_persists_summary(tmp_path : Path) -> None :
    path = tmp_path / "evaluation.db"
    run_id = _setup(path)

    process_run(
        run_id,
        conn_factory = lambda : _conn(path),
        translate_fn = lambda text : (f"EN {text}", 5.0),
        evaluate_fn = _fake_result,
        runtime_snapshot_fn = lambda : {"commit" : "test"},
    )

    conn = _conn(path)
    try :
        run = get_run(conn, run_id)
        assert run is not None
        assert run["status"] == "completed"
        assert run["completed_count"] == 25
        assert run["failed_count"] == 0
        assert run["runtime"] == {"commit" : "test"}
        assert run["summary"]["total_queries"] == 25
        assert run["summary"]["recall_at_3"] == 1.0
        assert run["summary"]["within_10s_rate"] == 1.0

        results = get_results(conn, run_id)
        assert all(result["status"] == "completed" for result in results)
        assert all(result["query_en"].startswith("EN ") for result in results)
    finally :
        conn.close()


def test_single_query_failure_continues_and_marks_run_partial(tmp_path : Path) -> None :
    path = tmp_path / "evaluation.db"
    run_id = _setup(path)
    calls = 0

    def sometimes_fails(query_vi : str, query_en : str, reference_video : str, *, translation_ms : float) -> dict :
        nonlocal calls
        calls += 1
        if (calls == 2) :
            raise RuntimeError("synthetic retrieval failure")
        return _fake_result(query_vi, query_en, reference_video, translation_ms = translation_ms)

    process_run(
        run_id,
        conn_factory = lambda : _conn(path),
        translate_fn = lambda text : (f"EN {text}", 5.0),
        evaluate_fn = sometimes_fails,
        runtime_snapshot_fn = lambda : {},
    )

    conn = _conn(path)
    try :
        run = get_run(conn, run_id)
        assert run is not None
        assert run["status"] == "partial"
        assert run["completed_count"] == 24
        assert run["failed_count"] == 1
        results = get_results(conn, run_id)
        failed = [result for result in results if result["status"] == "failed"]
        assert len(failed) == 1
        assert "synthetic retrieval failure" in failed[0]["error"]
        assert failed[0]["query_en"] is not None
    finally :
        conn.close()


def test_cancel_stops_after_current_query(tmp_path : Path) -> None :
    path = tmp_path / "evaluation.db"
    run_id = _setup(path)
    calls = 0

    def cancel_after_first(query_vi : str, query_en : str, reference_video : str, *, translation_ms : float) -> dict :
        nonlocal calls
        calls += 1
        result = _fake_result(query_vi, query_en, reference_video, translation_ms = translation_ms)
        if (calls == 1) :
            conn = _conn(path)
            try :
                cancelled = request_cancel(conn, run_id)
                assert cancelled is not None
                assert cancelled["status"] == "cancelling"
            finally :
                conn.close()
        return result

    process_run(
        run_id,
        conn_factory = lambda : _conn(path),
        translate_fn = lambda text : (f"EN {text}", 5.0),
        evaluate_fn = cancel_after_first,
        runtime_snapshot_fn = lambda : {},
    )

    conn = _conn(path)
    try :
        run = get_run(conn, run_id)
        assert run is not None
        assert run["status"] == "cancelled"
        assert run["completed_count"] == 1
        results = get_results(conn, run_id)
        assert results[0]["status"] == "completed"
        assert all(result["status"] == "queued" for result in results[1:])
    finally :
        conn.close()


def test_restart_marks_unfinished_runs_interrupted_and_resume_keeps_completed(tmp_path : Path) -> None :
    path = tmp_path / "evaluation.db"
    run_id = _setup(path)
    conn = _conn(path)
    try :
        first_id = conn.execute(
            "SELECT id FROM evaluation_query_results WHERE run_id = ? ORDER BY ordinal LIMIT 1",
            (run_id,),
        ).fetchone()[0]
        conn.execute(
            "UPDATE evaluation_query_results SET status = 'completed' WHERE id = ?",
            (first_id,),
        )
        conn.execute(
            "UPDATE evaluation_runs SET status = 'running', completed_count = 1 WHERE id = ?",
            (run_id,),
        )
        assert interrupt_incomplete_runs(conn) == 1
        assert get_run(conn, run_id)["status"] == "interrupted"

        resumed = resume_run(conn, run_id)
        assert resumed is not None
        assert resumed["status"] == "queued"
        assert resumed["completed_count"] == 1
        assert resumed["resume_count"] == 1
        results = get_results(conn, run_id)
        assert results[0]["status"] == "completed"
        assert all(result["status"] == "queued" for result in results[1:])
    finally :
        conn.close()


def test_summary_counts_failures_as_misses() -> None :
    summary = summarize_run_results([
        {
            "status" : "completed", "hit_at_1" : True, "hit_at_3" : True,
            "hit_at_5" : True, "hit_at_10" : True, "reciprocal_rank" : 1.0,
            "reference_video_rank" : 1, "not_retrieved" : False, "total_ms" : 1000.0,
        },
        {
            "status" : "failed", "hit_at_1" : None, "hit_at_3" : None,
            "hit_at_5" : None, "hit_at_10" : None, "reciprocal_rank" : None,
            "reference_video_rank" : None, "not_retrieved" : None, "total_ms" : 50.0,
        },
    ])
    assert summary["top1_accuracy"] == 0.5
    assert summary["mrr"] == 0.5
    assert summary["within_10s_rate"] == 0.5
    assert summary["failed_queries"] == 1
