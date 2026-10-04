# backend/app/evaluation/trake.py
"""TRAKE-N as a benchmark task mode: the production path, scored.

The production UI sends a TRAKE query to /trake-search-text, which splits it into events and calls
preprocess.trake_search_candidates (per-event ensemble search over every encoder, shortlist of K
videos by event coverage, one local encoder scores the frames of each shortlisted video, greedy
sequential pick under a gap of g seconds). Evaluation calls that same function with the production
defaults (K 20, g 60 s) and passes the seed's event list directly, each event already run through the
chosen text policy on its own. Direct passing differs from the UI's ". " splitter only for events
that contain a sentence break themselves.

Scoring
  video      always: the reference video's rank in the result list (sorted by combined score), through
             scoring.score_video_ranking, so Hit@k and MRR mean what they mean everywhere else. A video
             that is not shortlisted, or has no feasible chain, is not retrieved.
  per event  only when the seed has a reference frame for EVERY event of the query: the chosen frame of
             the reference video's chain is correct when within event_tolerance_s seconds of it. The
             seeds hold single team reference frames, not intervals, so the tolerance is the interval.
             A query with a missing reference frame is scored at video level only and the missing
             event ids are reported, so it is clear what to annotate.
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Callable

from app.evaluation.scoring import score_video_ranking

# Written on the run row (repository.create_run) and on every result, so a TRAKE-N run is never
# labelled with the shared-search strategy or the plain video-ranking policy.
STRATEGY_TRAKE_N        = "trake_n_v1"
VIDEO_RANKING_TRAKE_N   = "trake_combined_score_v1"
INTERVAL_POLICY_TRAKE_N = "none_trake_video_level"


def reference_events(conn : sqlite3.Connection, run : dict[str, Any], row : sqlite3.Row) -> list[dict[str, Any]] :
    """The seed's events of one query: event_id, description_vi, reference_frame_idx."""
    found = conn.execute(
        "SELECT trake_events_json FROM evaluation_references WHERE reference_set_id = ? AND query_id = ?",
        (run["reference_set_id"], row["query_id"]),
    ).fetchone()
    return json.loads(found["trake_events_json"]) if found and found["trake_events_json"] else []


def score_trake(
    results : list[dict[str, Any]],
    reference_video : str,
    ref_events : list[dict[str, Any]],
    fps : float,
    tolerance_s : float,
) -> dict[str, Any] :
    """Video rank always, per-event correctness when every event has a reference frame."""
    ranked = [{"rank" : i, "video_id" : r["video"], "combined_score" : r.get("combined_score")} for i, r in enumerate(results, start = 1)]
    video_metrics = score_video_ranking(ranked, reference_video)

    missing = [e["event_id"] for e in ref_events if e.get("reference_frame_idx") is None]
    if (missing or not ref_events) :
        return {"ranked_videos" : ranked, "video_metrics" : video_metrics, "events" : None, "missing_labels" : missing}

    chain = next((r for r in results if r["video"] == reference_video), None)
    tolerance_frames = tolerance_s * fps
    rows = []
    for index, event in enumerate(ref_events) :
        chosen = chain["events"][index].get("frame_idx") if chain and index < len(chain["events"]) else None
        reference = event["reference_frame_idx"]
        rows.append({
            "event_id"            : event["event_id"],
            "reference_frame_idx" : reference,
            "chosen_frame_idx"    : chosen,
            "error_s"             : round(abs(chosen - reference) / fps, 2) if chosen is not None else None,
            "correct"             : chosen is not None and abs(chosen - reference) <= tolerance_frames,
        })
    correct = sum(1 for r in rows if r["correct"])
    return {
        "ranked_videos"  : ranked,
        "video_metrics"  : video_metrics,
        "events"         : {"rows" : rows, "correct" : correct, "total" : len(rows), "accuracy" : correct / len(rows)},
        "missing_labels" : [],
    }


def evaluate_trake_n(
    query_vi : str,
    event_texts : list[str],
    reference_video : str,
    ref_events : list[dict[str, Any]],
    config,
    *,
    search_fn : Callable[..., list[dict]] | None = None,
    fps_fn : Callable[[str], float] | None = None,
) -> dict[str, Any] :
    """One TRAKE query through trake_search_candidates with the production parameters of `config`."""
    from app import preprocess

    search_fn = search_fn or preprocess.trake_search_candidates
    fps_fn = fps_fn or preprocess.fps_for_video

    started = time.monotonic()
    results = search_fn(
        event_texts, top_m = config.top_m, top_videos = config.trake.top_videos, gap_c = config.trake.gap_c,
        min_score = config.trake.min_score, model_name = config.trake.local_model,
    )
    retrieval_ms = (time.monotonic() - started) * 1000.0

    scored = score_trake(results, reference_video, ref_events, fps_fn(reference_video), config.trake.event_tolerance_s)
    frame_results = [
        {"video" : r["video"], "name" : e["name"], "frame_idx" : e.get("frame_idx"), "event" : i + 1, "distance" : e.get("score")}
        for r in results for i, e in enumerate(r["events"])
    ]
    return {
        "strategy"                : STRATEGY_TRAKE_N,
        "video_ranking_policy"    : VIDEO_RANKING_TRAKE_N,
        "interval_scoring_policy" : INTERVAL_POLICY_TRAKE_N,
        "translator"              : f"cache:{config.text_policy}",
        "query_vi"                : query_vi,
        "query_en"                : " | ".join(event_texts),
        "configuration"           : config.model_dump(),
        "frame_results"           : frame_results,
        "ranked_videos"           : scored["ranked_videos"],
        "video_metrics"           : scored["video_metrics"],
        # TRAKE is scored at video level here: no interval is defined for it.
        "interval_metrics"        : {"interval_hit" : None, "interval_rank" : None, "matched_interval_index" : None,
                                     "r_at" : {}, "final_score" : None},
        "timings"                 : {"translation_ms" : 0.0, "retrieval_ms" : round(retrieval_ms, 3),
                                     "aggregation_ms" : 0.0, "total_ms" : round(retrieval_ms, 3)},
        "trake"                   : {"events" : scored["events"], "missing_labels" : scored["missing_labels"],
                                     "shortlist" : len(results)},
    }
