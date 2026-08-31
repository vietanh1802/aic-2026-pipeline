from __future__ import annotations

import time
from typing import Any

from app.evaluation.scoring import VIDEO_RANKING_POLICY, rank_visual_videos, score_video_ranking
from app.translation import TRANSLATOR_ID, translate_vi_to_en


STRATEGY_NAME = "ensemble_search_en_v1"
TOP_K = 100
TOP_M = 50
USE_RERANK = True
MODELS = ["beit3", "clip"]


def evaluate_ensemble_query(
    query_vi : str,
    reference_video : str,
    *,
    search_fn = None,
) -> dict[str, Any] :
    query_en, translation_ms = translate_vi_to_en(query_vi)
    return evaluate_translated_ensemble_query(
        query_vi,
        query_en,
        reference_video,
        translation_ms = translation_ms,
        search_fn = search_fn,
    )


def evaluate_translated_ensemble_query(
    query_vi : str,
    query_en : str,
    reference_video : str,
    *,
    translation_ms : float,
    search_fn = None,
) -> dict[str, Any] :
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
    metrics = score_video_ranking(ranked_videos, reference_video)
    aggregation_ms = (time.monotonic() - aggregation_started) * 1000.0

    total_ms = float(translation_ms) + retrieval_ms + aggregation_ms
    return {
        "strategy"             : STRATEGY_NAME,
        "video_ranking_policy" : VIDEO_RANKING_POLICY,
        "translator"           : TRANSLATOR_ID,
        "query_vi"             : query_vi,
        "query_en"             : query_en,
        "configuration" : {
            "models"     : MODELS,
            "top_k"      : TOP_K,
            "top_m"      : TOP_M,
            "use_rerank" : USE_RERANK,
        },
        "frame_results"  : frame_results,
        "ranked_videos"  : ranked_videos,
        "metrics"        : metrics,
        "timings" : {
            "translation_ms" : round(translation_ms, 3),
            "retrieval_ms"   : round(retrieval_ms, 3),
            "aggregation_ms" : round(aggregation_ms, 3),
            "total_ms"       : round(total_ms, 3),
        },
    }
