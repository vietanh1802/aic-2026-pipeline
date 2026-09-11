"""Scoring for one benchmark run.

Two independent questions are answered from the same ranked frame list that
`ensemble_search` returns:

  - video-level: did the pipeline find the right video at all, and at what
    rank (Hit@1, Recall@3/5/10, MRR). Cheap, and still useful.
  - interval-level: the official AIC R-Score — a submitted frame counts only
    if it is the right video AND its frame index falls inside a manually
    reviewed valid interval. R@k and Final Score come from this.

TRAKE queries get the video-level answer only (Tier 0); their per-event
frames are not scored.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any


VIDEO_RANKING_POLICY = "first_frame_occurrence_v1"
INTERVAL_SCORING_POLICY = "any_interval_frame_match_v1"

# The rank cut-offs the official Final Score averages R@k over.
R_AT_CUTS = (1, 5, 20, 50, 100)


def _result_video(result : dict[str, Any]) -> str :
    return str(result.get("video") or result.get("video_id") or "").strip()


def collapse_visual_results(
    results : Sequence[dict[str, Any]],
    max_frames_per_video : int = 3,
) -> list[dict[str, Any]] :
    """Group a ranked frame list into a ranked video list, ordered by where
    each video FIRST appears in the frame ranking.

    Inlined from the old app.multimodal so the evaluation package carries no
    dependency on the multimodal / ASR code.
    """
    if (max_frames_per_video <= 0) :
        raise ValueError("max_frames_per_video must be positive")

    by_video : dict[str, dict[str, Any]] = {}
    for frame_rank, result in enumerate(results, start = 1) :
        video_id = _result_video(result)
        if (not video_id) :
            continue

        candidate = by_video.get(video_id)
        if (candidate is None) :
            candidate = {
                "rank"            : len(by_video) + 1,
                "video_id"        : video_id,
                "best_frame_rank" : frame_rank,
                "frames"          : [],
            }
            by_video[video_id] = candidate

        if (len(candidate["frames"]) < max_frames_per_video) :
            candidate["frames"].append(dict(result))

    return list(by_video.values())


def rank_visual_videos(results : Sequence[dict[str, Any]]) -> list[dict[str, Any]] :
    return collapse_visual_results(results, max_frames_per_video = 3)


def score_video_ranking(
    ranked_videos : Sequence[dict[str, Any]],
    reference_video : str,
) -> dict[str, Any] :
    """Video-level metrics: where the reference video sits in the ranked
    video list. A reference that never appears scores 0, not null."""
    reference = reference_video.strip()
    if (not reference) :
        raise ValueError("reference_video must not be empty")

    reference_rank = next(
        (
            int(candidate["rank"])
            for candidate in ranked_videos
            if str(candidate.get("video_id") or "") == reference
        ),
        None,
    )
    predicted_top1 = (
        str(ranked_videos[0].get("video_id") or "")
        if ranked_videos
        else None
    )

    return {
        "reference_video"      : reference,
        "predicted_top1_video" : predicted_top1,
        "reference_video_rank" : reference_rank,
        "hit_at_1"             : reference_rank == 1,
        "hit_at_3"             : reference_rank is not None and reference_rank <= 3,
        "hit_at_5"             : reference_rank is not None and reference_rank <= 5,
        "hit_at_10"            : reference_rank is not None and reference_rank <= 10,
        "reciprocal_rank"      : 1.0 / reference_rank if reference_rank else 0.0,
        "not_retrieved"        : reference_rank is None,
    }


def score_frame_intervals(
    frame_results : Sequence[dict[str, Any]],
    reference_video : str,
    valid_intervals : Sequence[dict[str, int]] | None,
) -> dict[str, Any] :
    """Official R-Score for one KIS/QA query.

    A submitted frame at rank i counts when it belongs to the reference video
    AND its frame index lands inside any valid interval (start and end both
    inclusive). `interval_rank` is the smallest such i; R@k is 1 when
    interval_rank <= k, and the query's Final Score is the mean of R@k over
    the official cut-offs.

    TRAKE passes valid_intervals=None and every field comes back None.
    """
    if (valid_intervals is None) :
        return {
            "interval_hit"           : None,
            "interval_rank"          : None,
            "matched_interval_index" : None,
            "r_at"                   : {cut : None for cut in R_AT_CUTS},
            "final_score"            : None,
        }

    reference = reference_video.strip()
    intervals = [(int(iv["start"]), int(iv["end"])) for iv in valid_intervals]

    interval_rank = None
    matched_interval_index = None
    for rank, frame in enumerate(frame_results, start = 1) :
        if (_result_video(frame) != reference) :
            continue
        frame_idx = frame.get("frame_idx")
        if (frame_idx is None) :
            continue
        frame_idx = int(frame_idx)
        for index, (start, end) in enumerate(intervals) :
            if (start <= frame_idx <= end) :
                interval_rank = rank
                matched_interval_index = index
                break
        if (interval_rank is not None) :
            break

    r_at = {
        cut : (1 if interval_rank is not None and interval_rank <= cut else 0)
        for cut in R_AT_CUTS
    }
    final_score = sum(r_at.values()) / len(R_AT_CUTS)

    return {
        "interval_hit"           : interval_rank is not None,
        "interval_rank"          : interval_rank,
        "matched_interval_index" : matched_interval_index,
        "r_at"                   : r_at,
        "final_score"            : final_score,
    }


def _percentile(values : Sequence[float], percentile : float) -> float | None :
    if (not values) :
        return None
    ordered = sorted(float(value) for value in values)
    if (len(ordered) == 1) :
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _video_metrics(results : Sequence[dict[str, Any]]) -> dict[str, Any] :
    """Video-level rates over a subset. Failed queries stay in the
    denominator so a run that silently lost queries reads as worse."""
    total = len(results)
    completed = [result for result in results if result.get("status") == "completed"]

    def rate(field : str) -> float :
        if (total == 0) :
            return 0.0
        return sum(1 for result in completed if result.get(field) is True) / total

    reciprocal_rank = sum(float(result.get("reciprocal_rank") or 0.0) for result in completed)
    reference_ranks = [
        int(result["reference_video_rank"])
        for result in completed
        if result.get("reference_video_rank") is not None
    ]
    return {
        "total"                 : total,
        "completed"             : len(completed),
        "failed"                : sum(1 for result in results if result.get("status") == "failed"),
        "hit_at_1"              : rate("hit_at_1"),
        "recall_at_3"           : rate("hit_at_3"),
        "recall_at_5"           : rate("hit_at_5"),
        "recall_at_10"          : rate("hit_at_10"),
        "mrr"                   : reciprocal_rank / total if total else 0.0,
        "median_reference_rank" : _percentile(reference_ranks, 0.5),
        "not_retrieved_count"   : sum(1 for result in completed if result.get("not_retrieved") is True),
    }


def _interval_metrics(results : Sequence[dict[str, Any]]) -> dict[str, Any] :
    """Interval-level rates over a subset of KIS/QA results. A failed or
    never-scored query contributes 0 to every rate and to Final Score."""
    total = len(results)
    if (total == 0) :
        return {
            "final_score"            : 0.0,
            "r_at"                   : {cut : 0.0 for cut in R_AT_CUTS},
            "interval_hit_rate"      : 0.0,
            "video_hit_interval_miss": 0,
        }

    final_score = sum(float(result.get("final_score") or 0.0) for result in results) / total
    r_at = {
        cut : sum(
            1 for result in results
            if result.get("interval_rank") is not None and int(result["interval_rank"]) <= cut
        ) / total
        for cut in R_AT_CUTS
    }
    interval_hits = sum(1 for result in results if result.get("interval_hit") is True)
    video_hit_interval_miss = sum(
        1 for result in results
        if result.get("interval_hit") is False
        and result.get("reference_video_rank") is not None
    )
    return {
        "final_score"             : final_score,
        "r_at"                    : r_at,
        "interval_hit_rate"       : interval_hits / total,
        "video_hit_interval_miss" : video_hit_interval_miss,
    }


def _latency_metrics(results : Sequence[dict[str, Any]]) -> dict[str, Any] :
    completed = [result for result in results if result.get("status") == "completed"]
    total_times = [
        float(result["total_ms"])
        for result in completed
        if result.get("total_ms") is not None
    ]
    within_10s = sum(1 for value in total_times if value <= 10000.0)
    denominator = len(results)
    return {
        "p50_ms"          : _percentile(total_times, 0.50),
        "p95_ms"          : _percentile(total_times, 0.95),
        "max_ms"          : max(total_times) if total_times else None,
        "within_10s_rate" : within_10s / denominator if denominator else 0.0,
    }


def summarize_run(results : Sequence[dict[str, Any]]) -> dict[str, Any] :
    """Blended headline plus a per-task-type breakdown.

    KIS and QA carry both the video-level and interval-level blocks. TRAKE
    carries the video-level block only, flagged tier 0. The headline reports
    two Final Score numbers side by side — KIS+QA and KIS-only — because QA is
    scored on video+interval but its answer text is never checked, and a
    single blended number reads as if it were.
    """
    kis = [result for result in results if result.get("task_type") == "KIS"]
    qa = [result for result in results if result.get("task_type") == "QA"]
    trake = [result for result in results if result.get("task_type") == "TRAKE"]
    kis_qa = kis + qa

    by_task_type = {
        "KIS" : {
            "video"    : _video_metrics(kis),
            "interval" : _interval_metrics(kis),
        },
        "QA" : {
            "video"    : _video_metrics(qa),
            "interval" : _interval_metrics(qa),
        },
        "TRAKE" : {
            "scoring_tier" : 0,
            "video"        : _video_metrics(trake),
        },
    }

    interval_kis_qa = _interval_metrics(kis_qa)
    interval_kis = _interval_metrics(kis)
    headline = {
        "total_queries"       : len(results),
        "scored_queries"      : len(kis_qa),
        "final_score_kis_qa"  : interval_kis_qa["final_score"],
        "final_score_kis"     : interval_kis["final_score"],
        "r_at_kis_qa"         : interval_kis_qa["r_at"],
        "r_at_kis"            : interval_kis["r_at"],
        "interval"            : interval_kis_qa,
        "video"               : _video_metrics(kis_qa),
        "latency"             : _latency_metrics(results),
    }

    return {"headline" : headline, "by_task_type" : by_task_type}
