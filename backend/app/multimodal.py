from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any
import math


DEFAULT_RRF_K = 60.0


def normalize_weights(visual_weight : float, asr_weight : float) -> tuple[float, float] :
    visual = float(visual_weight)
    asr    = float(asr_weight)
    if (not math.isfinite(visual) or not math.isfinite(asr)) :
        raise ValueError("Fusion weights must be finite")
    if (visual < 0.0 or asr < 0.0) :
        raise ValueError("Fusion weights must be nonnegative")
    total = visual + asr
    if (total <= 0.0) :
        raise ValueError("At least one fusion weight must be positive")
    return visual / total, asr / total


def collapse_visual_results(
    results : Sequence[dict[str, Any]],
    *,
    max_frames_per_video : int = 3,
) -> list[dict[str, Any]] :
    if (max_frames_per_video <= 0) :
        raise ValueError("max_frames_per_video must be positive")

    by_video : dict[str, dict[str, Any]] = {}
    for frame_rank, result in enumerate(results, start = 1) :
        video_id = str(result.get("video") or result.get("video_id") or "").strip()
        if (not video_id) :
            continue

        candidate = by_video.get(video_id)
        if (candidate is None) :
            candidate = {
                "rank" : len(by_video) + 1,
                "video_id" : video_id,
                "best_frame_rank" : frame_rank,
                "frames" : [],
            }
            by_video[video_id] = candidate

        if (len(candidate["frames"]) < max_frames_per_video) :
            candidate["frames"].append(dict(result))

    return list(by_video.values())


def fuse_video_rankings(
    visual_candidates : Sequence[dict[str, Any]],
    asr_hits : Sequence[dict[str, Any]],
    *,
    visual_weight : float = 0.5,
    asr_weight : float = 0.5,
    rrf_k : float = DEFAULT_RRF_K,
    limit : int = 50,
) -> list[dict[str, Any]] :
    visual_weight, asr_weight = normalize_weights(visual_weight, asr_weight)
    rrf_k = float(rrf_k)
    if (not math.isfinite(rrf_k) or rrf_k < 0.0) :
        raise ValueError("rrf_k must be finite and nonnegative")
    if (limit <= 0) :
        raise ValueError("limit must be positive")

    candidates : dict[str, dict[str, Any]] = {}

    for visual in visual_candidates :
        video_id = str(visual["video_id"])
        rank = int(visual["rank"])
        candidates[video_id] = {
            "video_id" : video_id,
            "visual" : dict(visual),
            "asr" : None,
            "fusion_score" : visual_weight / (rrf_k + rank),
        }

    for asr in asr_hits :
        video_id = str(asr["video_id"])
        rank = int(asr["rank"])
        candidate = candidates.setdefault(
            video_id,
            {
                "video_id" : video_id,
                "visual" : None,
                "asr" : None,
                "fusion_score" : 0.0,
            },
        )
        candidate["asr"] = dict(asr)
        candidate["fusion_score"] += asr_weight / (rrf_k + rank)

    def sort_key(candidate : dict[str, Any]) :
        visual_rank = (
            int(candidate["visual"]["rank"])
            if candidate["visual"] is not None
            else math.inf
        )
        asr_rank = (
            int(candidate["asr"]["rank"])
            if candidate["asr"] is not None
            else math.inf
        )
        return (
            -float(candidate["fusion_score"]),
            visual_rank,
            asr_rank,
            candidate["video_id"],
        )

    ordered = sorted(candidates.values(), key = sort_key)[ : limit]
    for rank, candidate in enumerate(ordered, start = 1) :
        candidate["rank"] = rank
        candidate["fusion"] = {
            "policy"        : "weighted_rrf",
            "score"         : float(candidate["fusion_score"]),
            "visual_weight" : visual_weight,
            "asr_weight"    : asr_weight,
            "rrf_k"         : rrf_k,
        }

    return ordered


def multimodal_search(
    query : str,
    *,
    limit : int = 50,
    visual_top_k : int = 100,
    visual_top_m : int = 50,
    asr_top_k : int = 50,
    windows_per_hit : int = 3,
    visual_weight : float = 0.5,
    asr_weight : float = 0.5,
    rrf_k : float = DEFAULT_RRF_K,
    max_visual_frames_per_video : int = 3,
    visual_search : Callable[..., Sequence[dict[str, Any]]] | None = None,
    asr_search : Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any] :
    visual_weight, asr_weight = normalize_weights(visual_weight, asr_weight)
    if (limit <= 0 or visual_top_k <= 0 or visual_top_m <= 0 or asr_top_k <= 0) :
        raise ValueError("Search limits must be positive")

    if (visual_search is None and visual_weight > 0.0) :
        from app.preprocess import ensemble_search
        visual_search = ensemble_search
    if (asr_search is None and asr_weight > 0.0) :
        from app.asr_service import search_asr
        asr_search = search_asr

    visual_results : Sequence[dict[str, Any]] = []
    if (visual_weight > 0.0) :
        if (visual_search is None) :
            raise RuntimeError("Visual search function is unavailable")
        visual_results = visual_search(
            query,
            top_k = visual_top_k,
            top_m = visual_top_m,
            use_rerank = True,
        )

    asr_result : dict[str, Any] = {"hits" : []}
    if (asr_weight > 0.0) :
        if (asr_search is None) :
            raise RuntimeError("ASR search function is unavailable")
        asr_result = asr_search(
            query,
            top_k = asr_top_k,
            windows_per_hit = windows_per_hit,
        )

    visual_candidates = collapse_visual_results(
        visual_results,
        max_frames_per_video = max_visual_frames_per_video,
    )
    results = fuse_video_rankings(
        visual_candidates,
        asr_result.get("hits", []),
        visual_weight = visual_weight,
        asr_weight = asr_weight,
        rrf_k = rrf_k,
        limit = limit,
    )

    return {
        "query" : query,
        "results" : results,
        "visual_result_count" : len(visual_results),
        "visual_video_count" : len(visual_candidates),
        "asr_video_count" : len(asr_result.get("hits", [])),
        "fusion" : {
            "policy" : "weighted_rrf",
            "visual_weight" : visual_weight,
            "asr_weight" : asr_weight,
            "rrf_k" : float(rrf_k),
        },
    }
