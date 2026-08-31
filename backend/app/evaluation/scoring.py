from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.multimodal import collapse_visual_results


VIDEO_RANKING_POLICY = "first_frame_occurrence_v1"


def rank_visual_videos(results : Sequence[dict[str, Any]]) -> list[dict[str, Any]] :
    return collapse_visual_results(results, max_frames_per_video = 3)


def score_video_ranking(
    ranked_videos : Sequence[dict[str, Any]],
    reference_video : str,
) -> dict[str, Any] :
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


def summarize_run_results(results : Sequence[dict[str, Any]]) -> dict[str, Any] :
    total = len(results)
    completed = [result for result in results if result.get("status") == "completed"]
    failed = [result for result in results if result.get("status") == "failed"]

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
    total_times = [
        float(result["total_ms"])
        for result in completed
        if result.get("total_ms") is not None
    ]
    within_10s = sum(
        1
        for result in completed
        if result.get("total_ms") is not None and float(result["total_ms"]) <= 10000.0
    )

    median_rank = _percentile(reference_ranks, 0.5)
    return {
        "total_queries"         : total,
        "completed_queries"     : len(completed),
        "failed_queries"        : len(failed),
        "top1_accuracy"         : rate("hit_at_1"),
        "recall_at_3"           : rate("hit_at_3"),
        "recall_at_5"           : rate("hit_at_5"),
        "recall_at_10"          : rate("hit_at_10"),
        "mrr"                   : reciprocal_rank / total if total else 0.0,
        "median_reference_rank" : median_rank,
        "not_retrieved_count"   : sum(1 for result in completed if result.get("not_retrieved") is True),
        "p50_ms"                : _percentile(total_times, 0.50),
        "p95_ms"                : _percentile(total_times, 0.95),
        "max_ms"                : max(total_times) if total_times else None,
        "within_10s_rate"       : within_10s / total if total else 0.0,
    }
