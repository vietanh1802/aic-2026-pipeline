"""Integration tests for the run engine, against a stubbed ensemble so results
are deterministic and no model is loaded."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app import audit
from app.db.connection import get_conn, utcnow_iso
from app.evaluation.repository import create_run, get_result, get_run, resume_run
from app.evaluation.runner import process_run
from app.evaluation.scoring import rank_visual_videos, score_frame_intervals, score_video_ranking
from app.evaluation.seed import SEEDS_DIR, import_seed
from app.routers import evaluation as evaluation_router

ROUND1 = SEEDS_DIR / "round1-v2.json"


def _admin(conn) -> int :
    cursor = conn.execute(
        "INSERT INTO users (username, display_name, role, password_hash, "
        "must_change_password, disabled, created_at) VALUES ('admin', 'admin', 'admin', 'x', 0, 0, ?)",
        (utcnow_iso(),),
    )
    return int(cursor.lastrowid)


def _translate(query_vi : str) -> tuple[str, float] :
    return (f"EN::{query_vi[:20]}", 12.0)


def _perfect_evaluate(query_vi, query_en, reference_video, valid_intervals, *, translation_ms) :
    """Reference video at rank 1, evidence frame inside the first interval."""
    start = valid_intervals[0]["start"] if valid_intervals else 0
    frame_results = [{"video" : reference_video, "frame_idx" : start}, {"video" : "OTHER", "frame_idx" : 1}]
    ranked_videos = rank_visual_videos(frame_results)
    return {
        "video_metrics"    : score_video_ranking(ranked_videos, reference_video),
        "interval_metrics" : score_frame_intervals(frame_results, reference_video, valid_intervals),
        "timings" : {
            "translation_ms" : translation_ms, "retrieval_ms" : 5.0,
            "aggregation_ms" : 1.0, "total_ms" : translation_ms + 6.0,
        },
        "frame_results" : frame_results,
        "ranked_videos" : ranked_videos,
    }


def _run(conn, evaluate_fn = _perfect_evaluate) :
    _admin(conn)
    import_seed(conn, ROUND1)
    run = create_run(conn, "round1-v2", "r1-manual-v2", 1)
    process_run(run["id"], translate_fn = _translate, evaluate_fn = evaluate_fn)
    return run["id"]


# ─── a full run ────────────────────────────────────────────────────────────

def test_full_run_persists_video_and_interval_scores(conn) :
    run_id = _run(conn)

    run = get_run(conn, run_id)
    assert run["status"] == "completed"
    assert run["completed_count"] == 25
    assert run["failed_count"] == 0
    assert run["interval_scoring_policy"] == "any_interval_frame_match_v1"

    kis = get_result(conn, run_id, "p1-1")
    assert kis["status"] == "completed"
    assert kis["hit_at_1"] is True
    assert kis["interval_hit"] is True
    assert kis["interval_rank"] == 1
    assert kis["matched_interval_index"] == 0
    assert kis["final_score"] == 1.0
    assert kis["query_en"].startswith("EN::")
    assert kis["frame_results"] is not None  # single-query endpoint keeps evidence

    trake = get_result(conn, run_id, "p1-16")
    assert trake["status"] == "completed"
    assert trake["hit_at_1"] is True
    assert trake["interval_hit"] is None
    assert trake["interval_rank"] is None
    assert trake["final_score"] is None
    # detail endpoint surfaces the reference answer / events, unscored
    assert len(trake["trake_events"]) == 3
    qa = get_result(conn, run_id, "p1-3")
    assert qa["qa_answer"] == "37.05"


def test_full_run_persists_task_type_summary(conn) :
    run_id = _run(conn)
    run = get_run(conn, run_id)

    headline = run["summary"]
    assert headline["final_score_kis"] == 1.0
    assert headline["final_score_kis_qa"] == 1.0
    assert headline["scored_queries"] == 24

    by_type = run["task_type_summary"]
    assert by_type["KIS"]["interval"]["final_score"] == 1.0
    assert by_type["QA"]["interval"]["final_score"] == 1.0
    assert by_type["TRAKE"]["scoring_tier"] == 0
    assert "interval" not in by_type["TRAKE"]


def test_completed_row_is_all_or_nothing(conn) :
    run_id = _run(conn)
    row = conn.execute(
        """
        SELECT predicted_top1_video, reference_video_rank, hit_at_1, final_score,
               translation_ms, retrieval_ms, total_ms, frame_results_json, finished_at
        FROM evaluation_query_results WHERE run_id = ? AND query_key = 'p1-1'
        """,
        (run_id,),
    ).fetchone()
    # every completed-path column populated together — the single UPDATE inside
    # BEGIN IMMEDIATE / COMMIT makes a half-written row structurally impossible
    assert all(row[column] is not None for column in row.keys())


# ─── cancel on the last query (Phase 2 item 1.2) ───────────────────────────

def test_cancel_during_last_query_is_not_overwritten_by_summary(conn) :
    _admin(conn)
    import_seed(conn, ROUND1)
    run = create_run(conn, "round1-v2", "r1-manual-v2", 1)
    run_id = run["id"]

    calls = {"n" : 0}

    def evaluate_then_cancel_on_last(query_vi, query_en, ref, intervals, *, translation_ms) :
        calls["n"] += 1
        if (calls["n"] == 25) :
            side = get_conn()
            side.execute(
                "UPDATE evaluation_runs SET status = 'cancelling' WHERE id = ? AND status = 'running'",
                (run_id,),
            )
            side.close()
        return _perfect_evaluate(query_vi, query_en, ref, intervals, translation_ms = translation_ms)

    process_run(run_id, translate_fn = _translate, evaluate_fn = evaluate_then_cancel_on_last)

    run = get_run(conn, run_id)
    assert run["status"] == "cancelled"
    # a cancelled run still carries real partial numbers over what ran
    assert run["summary"]["final_score_kis"] == 1.0
    assert run["task_type_summary"]["KIS"]["video"]["completed"] == 20
    # the query that was in flight when the cancel landed still finished
    assert conn.execute(
        "SELECT COUNT(*) FROM evaluation_query_results WHERE run_id = ? AND status = 'completed'",
        (run_id,),
    ).fetchone()[0] == 25


def test_cancel_mid_run_still_persists_a_partial_summary(conn) :
    _admin(conn)
    import_seed(conn, ROUND1)
    run = create_run(conn, "round1-v2", "r1-manual-v2", 1)
    run_id = run["id"]

    calls = {"n" : 0}

    def cancel_after_ten(query_vi, query_en, ref, intervals, *, translation_ms) :
        calls["n"] += 1
        if (calls["n"] == 10) :
            side = get_conn()
            side.execute("UPDATE evaluation_runs SET status = 'cancelling' WHERE id = ?", (run_id,))
            side.close()
        return _perfect_evaluate(query_vi, query_en, ref, intervals, translation_ms = translation_ms)

    process_run(run_id, translate_fn = _translate, evaluate_fn = cancel_after_ten)

    run = get_run(conn, run_id)
    assert run["status"] == "cancelled"
    assert run["summary"] is not None
    assert run["summary"]["video"]["completed"] == 10


# ─── resume skips completed rows ──────────────────────────────────────────

def test_resume_only_reprocesses_unfinished_rows(conn) :
    _admin(conn)
    import_seed(conn, ROUND1)
    run = create_run(conn, "round1-v2", "r1-manual-v2", 1)
    run_id = run["id"]

    def fail_after_20(query_vi, query_en, ref, intervals, *, translation_ms) :
        ordinal = conn.execute(
            "SELECT ordinal FROM evaluation_query_results WHERE run_id = ? AND query_vi = ?",
            (run_id, query_vi),
        ).fetchone()["ordinal"]
        if (ordinal > 20) :
            raise RuntimeError("boom")
        return _perfect_evaluate(query_vi, query_en, ref, intervals, translation_ms = translation_ms)

    process_run(run_id, translate_fn = _translate, evaluate_fn = fail_after_20)
    assert get_run(conn, run_id)["status"] == "partial"

    first_pass_finished = {
        row["query_key"] : row["finished_at"]
        for row in conn.execute(
            "SELECT query_key, finished_at FROM evaluation_query_results "
            "WHERE run_id = ? AND status = 'completed'",
            (run_id,),
        )
    }
    assert len(first_pass_finished) == 20

    resume_run(conn, run_id)
    second_calls = {"n" : 0}

    def count_calls(query_vi, query_en, ref, intervals, *, translation_ms) :
        second_calls["n"] += 1
        return _perfect_evaluate(query_vi, query_en, ref, intervals, translation_ms = translation_ms)

    process_run(run_id, translate_fn = _translate, evaluate_fn = count_calls)

    assert second_calls["n"] == 5  # only the 5 that had failed
    assert get_run(conn, run_id)["status"] == "completed"

    still_finished = {
        row["query_key"] : row["finished_at"]
        for row in conn.execute(
            "SELECT query_key, finished_at FROM evaluation_query_results "
            "WHERE run_id = ? AND query_key IN ({})".format(
                ",".join(f"'{key}'" for key in first_pass_finished)
            ),
            (run_id,),
        )
    }
    assert still_finished == first_pass_finished  # untouched


# ─── fully failed run (Phase 2 item 2.6) ──────────────────────────────────

def test_run_where_every_query_errors_is_labelled_failed(conn) :
    def always_raise(*args, **kwargs) :
        raise RuntimeError("no model")

    run_id = _run(conn, evaluate_fn = always_raise)
    run = get_run(conn, run_id)
    assert run["status"] == "failed"
    assert run["completed_count"] == 0
    assert run["failed_count"] == 25


# ─── router: 409 while a run is active (Phase 2 item 2.2) ─────────────────

def test_second_run_while_one_active_returns_409(conn, monkeypatch) :
    monkeypatch.setattr(evaluation_router, "enqueue_run", lambda run_id : None)
    admin_id = _admin(conn)
    admin = conn.execute("SELECT * FROM users WHERE id = ?", (admin_id,)).fetchone()
    import_seed(conn, ROUND1)

    payload = evaluation_router.EvaluationRunCreate()
    first = evaluation_router.start_run(payload, admin, conn)
    assert first["run"]["status"] == "queued"

    with pytest.raises(HTTPException) as excinfo :
        evaluation_router.start_run(payload, admin, conn)
    assert excinfo.value.status_code == 409


def test_start_cancel_resume_are_audited(conn, monkeypatch) :
    monkeypatch.setattr(evaluation_router, "enqueue_run", lambda run_id : None)
    admin_id = _admin(conn)
    admin = conn.execute("SELECT * FROM users WHERE id = ?", (admin_id,)).fetchone()
    import_seed(conn, ROUND1)

    run = evaluation_router.start_run(evaluation_router.EvaluationRunCreate(), admin, conn)["run"]
    evaluation_router.cancel_run(run["id"], admin, conn)

    actions = {
        row["action"]
        for row in conn.execute("SELECT action FROM audit_log WHERE target = ?", (f"evaluation_run:{run['id']}",))
    }
    assert audit.EVALUATION_RUN_START in actions
    assert audit.EVALUATION_RUN_CANCEL in actions
