"""Run one query end to end: translate, retrieve, score.

Both scorers run on the same ranked frame list `ensemble_search` returns —
`score_video_ranking` (did we find the right video) and `score_frame_intervals`
(the official R-Score, KIS/QA only). TRAKE passes valid_intervals=None and gets
the video-level answer alone.
"""
from __future__ import annotations

import time
from typing import Any

from app.evaluation.scoring import (
    INTERVAL_SCORING_POLICY,
    VIDEO_RANKING_POLICY,
    rank_visual_videos,
    score_frame_intervals,
    score_video_ranking,
)
from app.translation import (
    normalize_translation_policy,
    translate_vi_to_en,
    translator_id_for_policy,
)


STRATEGY_NAME = "ensemble_search_en_v1"
STRATEGY_SHARED = "shared_search_v1"
TOP_K = 100
TOP_M = 50
USE_RERANK = True
MODELS = ["beit3", "clip"]


def evaluate_ensemble_query(
    query_vi : str,
    reference_video : str,
    valid_intervals : list[dict[str, int]] | None,
    *,
    translation_policy : str | None = None,
    search_fn = None,
) -> dict[str, Any] :
    selected_policy = normalize_translation_policy(translation_policy)
    query_en, translation_ms = translate_vi_to_en(query_vi, policy = selected_policy)
    return evaluate_translated_ensemble_query(
        query_vi,
        query_en,
        reference_video,
        valid_intervals,
        translation_ms = translation_ms,
        translation_policy = selected_policy,
        search_fn = search_fn,
    )


def evaluate_translated_ensemble_query(
    query_vi : str,
    query_en : str,
    reference_video : str,
    valid_intervals : list[dict[str, int]] | None,
    *,
    translation_ms : float,
    translation_policy : str | None = None,
    search_fn = None,
) -> dict[str, Any] :
    selected_policy = normalize_translation_policy(translation_policy)
    if (search_fn is None) :
        from app.preprocess import ensemble_search
        search_fn = ensemble_search

    retrieval_started = time.monotonic()
    frame_results = search_fn(
        query_en,
        top_k = TOP_K,
        top_m = TOP_M,
        use_rerank = USE_RERANK,
        models = MODELS,
    )
    retrieval_ms = (time.monotonic() - retrieval_started) * 1000.0

    aggregation_started = time.monotonic()
    ranked_videos = rank_visual_videos(frame_results)
    video_metrics = score_video_ranking(ranked_videos, reference_video)
    interval_metrics = score_frame_intervals(frame_results, reference_video, valid_intervals)
    aggregation_ms = (time.monotonic() - aggregation_started) * 1000.0

    total_ms = float(translation_ms) + retrieval_ms + aggregation_ms
    return {
        "strategy"                : STRATEGY_NAME,
        "video_ranking_policy"    : VIDEO_RANKING_POLICY,
        "interval_scoring_policy" : INTERVAL_SCORING_POLICY,
        "translator"              : translator_id_for_policy(selected_policy),
        "query_vi"                : query_vi,
        "query_en"                : query_en,
        "configuration" : {
            "models"             : MODELS,
            "top_k"              : TOP_K,
            "top_m"              : TOP_M,
            "use_rerank"         : USE_RERANK,
            "translation_policy" : selected_policy,
        },
        "frame_results"    : frame_results,
        "ranked_videos"    : ranked_videos,
        "video_metrics"    : video_metrics,
        "interval_metrics" : interval_metrics,
        "timings" : {
            "translation_ms" : round(translation_ms, 3),
            "retrieval_ms"   : round(retrieval_ms, 3),
            "aggregation_ms" : round(aggregation_ms, 3),
            "total_ms"       : round(total_ms, 3),
        },
    }


def evaluate_with_config(
    query_vi : str,
    query_text : str,
    reference_video : str,
    valid_intervals : list[dict[str, int]] | None,
    config,
    *,
    text_ms : float = 0.0,
    search_fn = None,
) -> dict[str, Any] :
    """One query of a configured run: the text is already resolved (cache replay, no network), the
    search goes through the shared per-model memo, scoring is the unchanged scoring.py.

    The result has the same shape as evaluate_translated_ensemble_query so the runner writes it
    with the same code. search_fn exists for tests; the default is shared_search.search."""
    if (config.task_mode != "ensemble") :
        raise NotImplementedError(f"task_mode {config.task_mode} is not available yet")
    shared = search_fn is None
    if (shared) :
        from app.evaluation import shared_search
        search_fn = shared_search.search

    retrieval_started = time.monotonic()
    # Passed only when set, so search stubs written before rerank variants keep working.
    variant = {"variant" : config.rerank_variant} if config.rerank_variant is not None else {}
    frame_results = search_fn(
        query_text, list(config.models), config.top_k, config.top_m, config.rerank_mode, **variant
    )
    retrieval_ms = (time.monotonic() - retrieval_started) * 1000.0
    # Per-model search and rerank times as first measured (a reused memo entry reports its original
    # time with reused = true), so the cost of this arm can be rebuilt offline. Stubs report nothing.
    model_timings = shared_search.last_timing() if shared else None

    aggregation_started = time.monotonic()
    ranked_videos = rank_visual_videos(frame_results)
    video_metrics = score_video_ranking(ranked_videos, reference_video)
    interval_metrics = score_frame_intervals(frame_results, reference_video, valid_intervals)
    aggregation_ms = (time.monotonic() - aggregation_started) * 1000.0

    total_ms = float(text_ms) + retrieval_ms + aggregation_ms
    return {
        "strategy"                : STRATEGY_SHARED,
        "video_ranking_policy"    : VIDEO_RANKING_POLICY,
        "interval_scoring_policy" : INTERVAL_SCORING_POLICY,
        "translator"              : f"cache:{config.text_policy}",
        "query_vi"                : query_vi,
        "query_en"                : query_text,
        "configuration"           : config.model_dump(),
        "frame_results"           : frame_results,
        "ranked_videos"           : ranked_videos,
        "video_metrics"           : video_metrics,
        "interval_metrics"        : interval_metrics,
        "model_timings"           : model_timings,
        "timings" : {
            "translation_ms" : round(text_ms, 3),
            "retrieval_ms"   : round(retrieval_ms, 3),
            "aggregation_ms" : round(aggregation_ms, 3),
            "total_ms"       : round(total_ms, 3),
        },
    }
