# backend/tests/test_evaluation_trake.py
"""TRAKE-N scoring on a small fixture: video rank always, per-event tolerance when every event is labelled.

Three shortlisted videos in score order: OTHER_1, the reference video, OTHER_2. The reference video's
chain picked frames 100, 205 and 400 for events whose team reference frames are 100, 200 and 800; at 25 fps
a 5 s tolerance is 125 frames, so the first two events are correct and the third is not.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from app import preprocess
from app.db.connection import utcnow_iso
from app.evaluation import report, text_cache
from app.evaluation.config import RunConfig
from app.evaluation.presets import preset_configs
from app.evaluation.repository import get_run
from app.evaluation.runner import process_run
from app.evaluation.seed import SEEDS_DIR, import_seed
from app.evaluation.trake import discovery_info, evaluate_trake_n, score_trake
from app.routers import evaluation as evaluation_router

REFERENCE = "L10_V001"


def _chain(video : str, frames : list[int]) -> dict :
    return {"video" : video, "combined_score" : 1.0, "events" : [{"name" : f"{video}-{i}.jpg", "frame_idx" : f} for i, f in enumerate(frames)]}


RESULTS = [_chain("OTHER_1", [1, 2, 3]), _chain(REFERENCE, [100, 205, 400]), _chain("OTHER_2", [7, 8, 9])]
LABELLED = [{"event_id" : f"E{i + 1}", "reference_frame_idx" : f} for i, f in enumerate([100, 200, 800])]


def test_video_rank_and_per_event_tolerance() :
    scored = score_trake(RESULTS, REFERENCE, LABELLED, fps = 25.0, tolerance_s = 5.0)
    assert scored["video_metrics"]["reference_video_rank"] == 2
    assert scored["video_metrics"]["hit_at_1"] is False and scored["video_metrics"]["hit_at_3"] is True
    events = scored["events"]
    assert [e["correct"] for e in events["rows"]] == [True, True, False]
    assert events["rows"][1]["error_s"] == 0.2
    assert (events["correct"], events["total"]) == (2, 3)
    assert events["accuracy"] == pytest.approx(2 / 3)


def test_missing_reference_frames_fall_back_to_video_level_and_are_named() :
    unlabelled = [LABELLED[0], {"event_id" : "E2", "reference_frame_idx" : None}, {"event_id" : "E3"}]
    scored = score_trake(RESULTS, REFERENCE, unlabelled, fps = 25.0, tolerance_s = 5.0)
    assert scored["video_metrics"]["reference_video_rank"] == 2
    assert scored["events"] is None and scored["missing_labels"] == ["E2", "E3"]


def test_reference_video_not_shortlisted_scores_zero_and_the_call_uses_production_parameters() :
    seen = {}

    def search(texts, **kwargs) :
        seen.update(kwargs, texts = texts)
        return [_chain("OTHER_1", [1, 2, 3])]

    config = RunConfig(name = "T01", task_mode = "trake_n")
    result = evaluate_trake_n("q", ["a", "b", "c"], REFERENCE, LABELLED, config, search_fn = search, fps_fn = lambda video : 25.0)
    assert result["video_metrics"]["not_retrieved"] is True
    assert result["trake"]["events"]["accuracy"] == 0.0
    # K 20, g 60 s, top_m 50, CLIP: what the UI sends to /trake-search-text.
    assert (seen["top_videos"], seen["gap_c"], seen["top_m"], seen["model_name"]) == (20, 60, 50, "clip")
    assert seen["texts"] == ["a", "b", "c"]
    assert [c.name for c in preset_configs("trake")] == ["T01 TRAKE-N", "T02 TRAKE queries, plain ensemble"]


# ─── through the real runner path ──────────────────────────────────────────

def _seed_and_cache(conn, monkeypatch, dataset : str) -> tuple[sqlite3.Row, list[sqlite3.Row]] :
    """Admin user, the seed imported, and every TRAKE event text of it cached (so replay needs neither a
    key nor the network). Returns (user, the TRAKE query rows)."""
    monkeypatch.setattr(evaluation_router, "enqueue_run", lambda run_id : None)
    user_id = conn.execute(
        "INSERT INTO users (username, display_name, role, password_hash, must_change_password, disabled, created_at) "
        "VALUES ('admin', 'admin', 'admin', 'x', 0, 0, ?)", (utcnow_iso(),),
    ).lastrowid
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    import_seed(conn, SEEDS_DIR / f"{dataset}.json")
    rows = [row for row in text_cache.query_rows(conn, dataset) if row["task_type"] == "TRAKE"]
    for row in rows :
        for event in json.loads(row["trake_events_json"]) :
            text_cache.store(conn, text_cache.make_key("translate_gtx", event["description_vi"], ""),
                             event["description_vi"], {"text" : f"EN::{event['description_vi']}"}, "google_gtx")
    return user, rows


def _chain(video : str, frames : list[int]) -> dict :
    return {"video" : video, "combined_score" : 0.9, "events" : [
        {"name" : f"{video}-{i}.jpg", "frame_idx" : f, "score" : 0.5} for i, f in enumerate(frames)]}


def _start(conn, user, dataset : str, reference_set : str) -> dict :
    request = evaluation_router.EvaluationRunCreate(
        dataset_version = dataset, reference_set_version = reference_set,
        config = {"task_mode" : "trake_n", "text_policy" : "translate_gtx"},
    )
    return evaluation_router.start_run(request, user, conn)["run"]


def test_trake_n_run_goes_through_process_run_and_the_report(conn, monkeypatch) :
    """round1-v3 has one TRAKE query (p1-16, three events, reference video L24_V024). The run is created
    through the router, scored by process_run with trake_search_candidates and the fps lookup stubbed,
    and its rows must load in the report with the per-event accuracy."""
    user, rows = _seed_and_cache(conn, monkeypatch, "round1-v3")
    assert len(rows) == 1 and len(json.loads(rows[0]["trake_events_json"])) == 3

    calls : list[list[str]] = []

    def stub_trake(event_texts, **kwargs) :
        calls.append(list(event_texts))
        # The reference chain hits E1 and E3 within 5 s (125 frames at 25 fps) and misses E2.
        return [_chain("L01_V001", [1, 2, 3]), _chain("L24_V024", [9784, 10500, 10190])]

    monkeypatch.setattr(preprocess, "trake_search_candidates", stub_trake)
    monkeypatch.setattr(preprocess, "fps_for_video", lambda video : 25.0)

    run = _start(conn, user, "round1-v3", "r1-manual-v3")
    assert run["strategy"] == "trake_n_v1"
    process_run(run["id"], runtime_snapshot_fn = lambda : {"device" : "test"})

    stored = get_run(conn, run["id"])
    assert (stored["status"], stored["completed_count"], stored["failed_count"]) == ("completed", 1, 0)
    assert (stored["strategy"], stored["video_ranking_policy"], stored["interval_scoring_policy"]) == (
        "trake_n_v1", "trake_combined_score_v1", "none_trake_video_level")
    assert len(calls) == 1 and len(calls[0]) == 3 and all(t.startswith("EN::") for t in calls[0])

    # Video metrics are written; the interval columns hold NULL for a TRAKE query.
    row = conn.execute("SELECT * FROM evaluation_query_results WHERE run_id = ?", (run["id"],)).fetchone()
    assert row["status"] == "completed" and row["reference_video_rank"] == 2
    assert row["interval_hit"] is None and row["interval_rank"] is None and row["final_score"] is None

    # summarize_run copes with every interval metric being None. The headline is KIS and QA only, so a
    # TRAKE-only run reads from the TRAKE block of task_type_summary.
    video = stored["task_type_summary"]["TRAKE"]["video"]
    assert (video["total"], video["completed"], video["recall_at_3"], video["hit_at_1"]) == (1, 1, 1.0, 0.0)
    assert stored["summary"]["scored_queries"] == 0

    rows = report.load_rows(conn, [run["id"]])
    assert len(rows) == 1
    extra = rows[0]["extra"]
    assert extra["trake"]["events"]["correct"] == 2 and extra["trake"]["events"]["total"] == 3
    assert extra["trake"]["shortlist"] == 2
    # The stage breakdown is stored (with the corpus not loaded here the rebuilt shortlist is empty).
    assert {"candidates", "reference_rank", "in_shortlist", "feasible_chain", "consistent"} <= set(extra["trake"]["discovery"])
    assert extra["trake"]["discovery"]["feasible_chain"] is True
    assert len(extra["cache_digests"]) == 3
    long_rows = report.long_table(rows)
    assert long_rows and any(r.get("event_accuracy") == pytest.approx(2 / 3) for r in long_rows)


@pytest.mark.parametrize("dataset, reference_set", [
    ("round1-v3", "r1-manual-v3"), ("round2-v2", "r2-manual-v2"), ("round3-v2", "r3-manual-v2"), ("final-v1", "final-appeal-v1"),
])
def test_trake_n_completes_on_every_seed_with_exact_chains(conn, monkeypatch, dataset, reference_set) :
    """Smoke over the real seeds: whatever shape a seed's TRAKE events have (3 or 4 events, S and L
    reference videos), every query completes, scores a perfect chain as such, and loads in the report."""
    user, rows = _seed_and_cache(conn, monkeypatch, dataset)
    truth = {}
    for row in rows :
        events = json.loads(row["trake_events_json"])
        truth[f"EN::{events[0]['description_vi']}"] = (row["video_id"], [e["reference_frame_idx"] for e in events])

    def stub_trake(event_texts, **kwargs) :
        video, frames = truth[event_texts[0]]
        return [_chain(video, frames)]

    monkeypatch.setattr(preprocess, "trake_search_candidates", stub_trake)
    monkeypatch.setattr(preprocess, "fps_for_video", lambda video : 25.0)

    run = _start(conn, user, dataset, reference_set)
    assert run["query_count"] == len(rows)
    process_run(run["id"], runtime_snapshot_fn = lambda : {"device" : "test"})

    stored = get_run(conn, run["id"])
    assert (stored["status"], stored["completed_count"], stored["failed_count"]) == ("completed", len(rows), 0)
    assert stored["task_type_summary"]["TRAKE"]["video"]["hit_at_1"] == 1.0
    loaded = report.load_rows(conn, [run["id"]])
    assert [r["extra"]["trake"]["events"]["accuracy"] for r in loaded] == [1.0] * len(rows)
    assert all(r.get("event_accuracy") == 1.0 for r in report.long_table(loaded))


# ─── where the reference video stood in the shortlist stage ────────────────

def _fake_discovery_search(text, models, top_k, top_m, rerank_mode) :
    """Two events. V_REF appears in both, V_ONE in event 1 only, V_TWO in event 2 only."""
    rows = {"e1" : [("V_ONE", 90.0), ("V_REF", 80.0), ("V_ONE", 70.0)], "e2" : [("V_TWO", 95.0), ("V_REF", 60.0)]}[text]
    return [{"video" : v, "distance" : d} for v, d in rows]


def test_discovery_info_separates_not_shortlisted_from_no_feasible_chain() :
    # V_REF appears in both events and is first. V_ONE (best distance 90, counted once per event) and
    # V_TWO (95) have one event each, so V_TWO comes second.
    shortlisted = discovery_info(["e1", "e2"], "V_REF", 50, 2, ["V_TWO"], search_fn = _fake_discovery_search)
    assert (shortlisted["reference_rank"], shortlisted["reference_events"], shortlisted["candidates"]) == (1, 2, 3)
    assert shortlisted["in_shortlist"] is True and shortlisted["feasible_chain"] is False
    assert shortlisted["shortlist_videos"] == ["V_REF", "V_TWO"] and shortlisted["consistent"] is True

    # A reference that no event returned has no rank at all.
    absent = discovery_info(["e1", "e2"], "V_NONE", 50, 2, ["V_TWO"], search_fn = _fake_discovery_search)
    assert absent["reference_rank"] is None and absent["in_shortlist"] is False and absent["reference_events"] == 0

    # Ranked second but K = 1: not shortlisted. The real call returning it anyway would mean the rebuilt
    # rule does not follow the real one, which is what consistent reports.
    outside = discovery_info(["e1", "e2"], "V_TWO", 50, 1, ["V_TWO"], search_fn = _fake_discovery_search)
    assert outside["reference_rank"] == 2 and outside["in_shortlist"] is False and outside["consistent"] is False
