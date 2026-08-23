from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from typing import Sequence
import threading
import time

import numpy as np

from .artifacts import LoadedRelease, load_release
from .config import (
    BM25Config,
    E5Config,
    CandidateConfig,
    ProductionConfig,
    bm25_identity,
    e5_identity,
)
from .dense import E5Encoder, exact_dense_scores
from .reranker import BGEReranker, RerankerOutput
from .schemas import ASRSearchResult, ASRVideoHit, ASRWindowHit, SearchTimings


class ASRRetrievalEngine :
    def __init__(
        self,
        release : LoadedRelease,
        config : ProductionConfig,
        e5_encoder : E5Encoder,
        reranker : BGEReranker | None,
    ) :
        self.release = release
        self.config = config
        self.e5 = e5_encoder
        self.reranker = reranker
        self._gpu_lock = threading.Lock()
        self._eligible_video_indices = np.asarray(
            release.window_to_video[release.eligible_to_physical],
            dtype = np.int32,
        )
        self._video_ids = tuple(record.video_id for record in release.videos)
        self._state = "READY" if self._components_loaded() else "CREATED"

    @property
    def state(self) -> str :
        return self._state

    @classmethod
    def from_artifacts(
        cls,
        path : Path,
        *,
        config : ProductionConfig | None = None,
        warmup : bool = True,
    ) -> "ASRRetrievalEngine" :
        production = config or ProductionConfig()
        release = load_release(path, production.artifacts)

        expected_bm25 = bm25_identity(BM25Config())
        if (release.manifest.bm25_identity != expected_bm25) :
            raise ValueError(
                "Release BM25 identity does not match the production retrieval contract"
            )

        e5_config = E5Config(device = production.runtime.e5_device)
        if (release.manifest.e5_identity != e5_identity(e5_config)) :
            raise ValueError(
                "Release E5 identity does not match the production retrieval contract"
            )

        encoder = E5Encoder(e5_config)
        reranker = BGEReranker(production.bge) if production.runtime.load_reranker else None
        engine = cls(release, production, encoder, reranker)
        engine._state = "LOADING"

        try :
            encoder.load()
            if (reranker is not None) :
                reranker.load()
            if (warmup) :
                engine.warmup()
            else :
                engine._state = "READY"
        except Exception :
            engine.close()
            raise

        return engine

    def _components_loaded(self) -> bool :
        e5_loaded = bool(getattr(self.e5, "loaded", False))
        if (self.reranker is None) :
            return e5_loaded
        return e5_loaded and bool(getattr(self.reranker, "loaded", False))

    def warmup(self) -> dict[str, float] :
        if (self._state == "CLOSED") :
            raise RuntimeError("Cannot warm a closed ASR retrieval engine")
        if (not bool(getattr(self.e5, "loaded", False))) :
            raise RuntimeError("E5 must be loaded before warmup")
        if (self.reranker is not None and not bool(getattr(self.reranker, "loaded", False))) :
            raise RuntimeError("BGE must be loaded before warmup")

        self._state = "WARMING"
        query = self.config.runtime.warmup_query
        lock_context = self._gpu_lock if self.config.runtime.serialize_gpu_requests else nullcontext()

        with lock_context :
            started = time.perf_counter()
            query_embedding = self.e5.encode_query(query)
            e5_ms = (time.perf_counter() - started) * 1000.0

            started = time.perf_counter()
            exact_dense_scores(query_embedding, self.release.embeddings)
            dense_ms = (time.perf_counter() - started) * 1000.0

            bge_ms = 0.0
            if (self.reranker is not None) :
                first_physical = int(self.release.eligible_to_physical[0])
                text = self.release.windows[first_physical].retrieval_text
                started = time.perf_counter()
                self.reranker.score_pairs([(query, text)])
                bge_ms = (time.perf_counter() - started) * 1000.0

        self._state = "READY"
        return {
            "e5_encode_ms" : e5_ms,
            "dense_search_ms" : dense_ms,
            "bge_ms" : bge_ms,
        }

    @staticmethod
    def _elapsed_ms(start_ns : int) -> float :
        return (time.perf_counter_ns() - start_ns) / 1_000_000.0

    @staticmethod
    def _minmax_normalize(
        scores : np.ndarray,
        tolerance : float,
    ) -> np.ndarray :
        values = np.asarray(scores, dtype = np.float64).reshape(-1)
        if (len(values) == 0) :
            raise ValueError("Score normalization requires at least one value")
        if (not np.isfinite(values).all()) :
            raise ValueError("Score normalization source contains non-finite values")
        if (tolerance < 0) :
            raise ValueError("Score normalization tolerance must be nonnegative")

        minimum = float(values.min())
        maximum = float(values.max())
        score_range = maximum - minimum
        if (score_range <= tolerance) :
            return np.zeros(len(values), dtype = np.float32)
        return np.asarray((values - minimum) / score_range, dtype = np.float32)

    def _fuse_first_stage(
        self,
        bm25_raw : np.ndarray,
        dense_raw : np.ndarray,
    ) -> np.ndarray :
        if (bm25_raw.shape != dense_raw.shape) :
            raise ValueError("BM25 and dense score axes do not match")
        tolerance = self.config.fusion.constant_score_tolerance
        bm25_normalized = self._minmax_normalize(bm25_raw, tolerance)
        dense_normalized = self._minmax_normalize(dense_raw, tolerance)
        fused = (
            self.config.fusion.bm25_weight * bm25_normalized.astype(np.float64)
            + self.config.fusion.dense_weight * dense_normalized.astype(np.float64)
        )
        output = np.asarray(fused, dtype = np.float32)
        if (not np.isfinite(output).all()) :
            raise ValueError("First-stage fusion produced non-finite values")
        return output

    def _scatter_to_all_windows(self, eligible_scores : np.ndarray) -> np.ndarray :
        values = np.asarray(eligible_scores, dtype = np.float32).reshape(-1)
        if (values.shape != (self.release.manifest.eligible_window_count,)) :
            raise ValueError("Searchable-window score axis has the wrong length")
        output = np.zeros(self.release.manifest.physical_window_count, dtype = np.float32)
        output[self.release.eligible_to_physical] = values
        return output

    def _video_scores_and_order(
        self,
        eligible_scores : np.ndarray,
    ) -> tuple[np.ndarray, list[int]] :
        video_scores = np.zeros(self.release.manifest.video_count, dtype = np.float32)
        np.maximum.at(video_scores, self._eligible_video_indices, eligible_scores)
        order = sorted(
            range(self.release.manifest.video_count),
            key = lambda video_index : (
                -float(video_scores[video_index]),
                self._video_ids[video_index],
            ),
        )
        return video_scores, order

    def _ordered_searchable_windows(
        self,
        video_index : int,
        all_window_scores : np.ndarray,
    ) -> list[int] :
        start = int(self.release.video_window_offsets[video_index])
        end = int(self.release.video_window_offsets[video_index + 1])
        physical_ids = self.release.video_window_physical_ids[start : end].astype(int).tolist()
        searchable = [
            physical_index
            for physical_index in physical_ids
            if int(self.release.physical_to_eligible[physical_index]) >= 0
        ]
        return sorted(
            searchable,
            key = lambda physical_index : (
                -float(all_window_scores[physical_index]),
                int(self.release.windows[physical_index].sample_start),
                self.release.windows[physical_index].window_id,
            ),
        )

    def _select_candidates(
        self,
        first_stage_video_order : Sequence[int],
        all_window_scores : np.ndarray,
        candidate_config : CandidateConfig,
    ) -> tuple[list[int], list[int]] :
        candidate_videos = []
        ordered_by_video : dict[int, list[int]] = {}

        for video_index in first_stage_video_order :
            ordered = self._ordered_searchable_windows(video_index, all_window_scores)
            if (not ordered) :
                continue
            candidate_videos.append(video_index)
            ordered_by_video[video_index] = ordered
            if (len(candidate_videos) >= candidate_config.video_k) :
                break

        selected_physical = []
        for window_rank in range(candidate_config.windows_per_video) :
            for video_index in candidate_videos :
                if (len(selected_physical) >= candidate_config.max_candidate_pairs) :
                    return candidate_videos, selected_physical
                ordered = ordered_by_video[video_index]
                if (window_rank < len(ordered)) :
                    selected_physical.append(ordered[window_rank])

        return candidate_videos, selected_physical

    def _fuse_candidates(
        self,
        first_stage_scores : np.ndarray,
        reranker_scores : np.ndarray,
    ) -> np.ndarray :
        first = np.asarray(first_stage_scores, dtype = np.float32).reshape(-1)
        rerank = np.asarray(reranker_scores, dtype = np.float32).reshape(-1)
        if (first.shape != rerank.shape) :
            raise ValueError("Candidate first-stage and BGE score axes do not match")
        tolerance = self.config.fusion.constant_score_tolerance
        first_normalized = self._minmax_normalize(first, tolerance)
        reranker_normalized = self._minmax_normalize(rerank, tolerance)
        fused = (
            self.config.fusion.first_stage_weight * first_normalized.astype(np.float64)
            + self.config.fusion.reranker_weight * reranker_normalized.astype(np.float64)
        )
        output = np.asarray(fused, dtype = np.float32)
        if (not np.isfinite(output).all()) :
            raise ValueError("Candidate fusion produced non-finite values")
        return output

    def _build_window_hit(
        self,
        physical_index : int,
        first_stage_scores : np.ndarray,
        reranker_by_physical : dict[int, float],
        final_by_physical : dict[int, float],
    ) -> ASRWindowHit :
        record = self.release.windows[physical_index]
        return ASRWindowHit(
            window_id = record.window_id,
            video_id = record.video_id,
            start_s = record.start_s,
            end_s = record.end_s,
            transcript = record.retrieval_text,
            first_stage_score = float(first_stage_scores[physical_index]),
            reranker_score = reranker_by_physical.get(physical_index),
            final_score = final_by_physical.get(physical_index),
            reranked = physical_index in final_by_physical,
        )

    def _supporting_windows(
        self,
        video_index : int,
        first_stage_scores : np.ndarray,
        reranker_by_physical : dict[int, float],
        final_by_physical : dict[int, float],
        windows_per_hit : int,
    ) -> tuple[ASRWindowHit, ...] :
        first_order = self._ordered_searchable_windows(video_index, first_stage_scores)
        selected = [index for index in first_order if index in final_by_physical]
        selected = sorted(
            selected,
            key = lambda physical_index : (
                -float(final_by_physical[physical_index]),
                int(self.release.windows[physical_index].sample_start),
                self.release.windows[physical_index].window_id,
            ),
        )
        remaining = [index for index in first_order if index not in final_by_physical]
        final_order = (selected + remaining)[:windows_per_hit]
        return tuple(
            self._build_window_hit(
                physical_index,
                first_stage_scores,
                reranker_by_physical,
                final_by_physical,
            )
            for physical_index in final_order
        )

    def search(
        self,
        query : str,
        *,
        top_k : int | None = None,
        first_stage_only : bool = False,
        candidate_config : CandidateConfig | None = None,
        windows_per_hit : int | None = None,
    ) -> ASRSearchResult :
        if (self._state != "READY") :
            raise RuntimeError(f"ASR retrieval engine is not ready; current state={self._state!r}")
        text = str(query).strip()
        if (not text) :
            raise ValueError("Query must not be empty")

        requested_top_k = self.config.runtime.default_top_k if top_k is None else int(top_k)
        requested_windows = (
            self.config.runtime.default_windows_per_hit
            if windows_per_hit is None
            else int(windows_per_hit)
        )
        if (requested_top_k <= 0) :
            raise ValueError("top_k must be positive")
        if (requested_windows <= 0) :
            raise ValueError("windows_per_hit must be positive")
        candidate_policy = candidate_config or self.config.candidates

        total_started = time.perf_counter_ns()

        stage_started = time.perf_counter_ns()
        bm25_raw = self.release.bm25.score(text)
        bm25_ms = self._elapsed_ms(stage_started)

        e5_encode_ms = 0.0
        dense_search_ms = 0.0
        first_stage_fusion_ms = 0.0
        video_aggregation_ms = 0.0
        candidate_selection_ms = 0.0
        bge_ms = 0.0
        candidate_fusion_ms = 0.0
        reranker_batch_size = None
        candidate_pair_count = 0

        lock_context = self._gpu_lock if self.config.runtime.serialize_gpu_requests else nullcontext()
        with lock_context :
            stage_started = time.perf_counter_ns()
            query_embedding = self.e5.encode_query(text)
            e5_encode_ms = self._elapsed_ms(stage_started)

            stage_started = time.perf_counter_ns()
            dense_raw = exact_dense_scores(query_embedding, self.release.embeddings)
            dense_search_ms = self._elapsed_ms(stage_started)

            stage_started = time.perf_counter_ns()
            eligible_scores = self._fuse_first_stage(bm25_raw, dense_raw)
            all_window_scores = self._scatter_to_all_windows(eligible_scores)
            first_stage_fusion_ms = self._elapsed_ms(stage_started)

            stage_started = time.perf_counter_ns()
            video_scores, first_video_order = self._video_scores_and_order(eligible_scores)
            video_aggregation_ms = self._elapsed_ms(stage_started)

            first_stage_rank_by_video = {
                video_index : rank
                for rank, video_index in enumerate(first_video_order, start = 1)
            }

            reranker_by_physical : dict[int, float] = {}
            final_by_physical : dict[int, float] = {}
            candidate_video_set : set[int] = set()
            candidate_best_physical : dict[int, int] = {}
            candidate_video_final : dict[int, float] = {}

            if (first_stage_only) :
                final_video_order = list(first_video_order)
            else :
                if (self.reranker is None or not bool(getattr(self.reranker, "loaded", False))) :
                    raise RuntimeError(
                        "Reranked search was requested, but the BGE reranker is not loaded"
                    )

                stage_started = time.perf_counter_ns()
                candidate_videos, candidate_physical = self._select_candidates(
                    first_video_order,
                    all_window_scores,
                    candidate_policy,
                )
                candidate_selection_ms = self._elapsed_ms(stage_started)
                candidate_pair_count = len(candidate_physical)
                if (not candidate_physical) :
                    raise RuntimeError("No searchable transcript windows are available for reranking")

                pairs = [
                    (text, self.release.windows[physical_index].retrieval_text)
                    for physical_index in candidate_physical
                ]
                output : RerankerOutput = self.reranker.score_pairs(pairs)
                bge_ms = output.runtime_s * 1000.0
                reranker_batch_size = output.effective_batch_size

                stage_started = time.perf_counter_ns()
                candidate_first = np.asarray(
                    [all_window_scores[index] for index in candidate_physical],
                    dtype = np.float32,
                )
                candidate_final = self._fuse_candidates(candidate_first, output.scores)
                candidate_fusion_ms = self._elapsed_ms(stage_started)

                reranker_by_physical = {
                    physical_index : float(output.scores[index])
                    for index, physical_index in enumerate(candidate_physical)
                }
                final_by_physical = {
                    physical_index : float(candidate_final[index])
                    for index, physical_index in enumerate(candidate_physical)
                }
                candidate_video_set = set(candidate_videos)

                for video_index in candidate_videos :
                    selected = [
                        physical_index
                        for physical_index in candidate_physical
                        if int(self.release.window_to_video[physical_index]) == video_index
                    ]
                    if (not selected) :
                        continue
                    best_physical = min(
                        selected,
                        key = lambda physical_index : (
                            -final_by_physical[physical_index],
                            int(self.release.windows[physical_index].sample_start),
                            self.release.windows[physical_index].window_id,
                        ),
                    )
                    candidate_best_physical[video_index] = best_physical
                    candidate_video_final[video_index] = final_by_physical[best_physical]

                reranked_candidate_order = sorted(
                    candidate_video_final,
                    key = lambda video_index : (
                        -candidate_video_final[video_index],
                        self._video_ids[video_index],
                    ),
                )
                noncandidate_order = [
                    video_index
                    for video_index in first_video_order
                    if video_index not in candidate_video_set
                ]
                final_video_order = reranked_candidate_order + noncandidate_order

        result_started = time.perf_counter_ns()
        limit = min(requested_top_k, len(final_video_order))
        hits = []

        for final_rank, video_index in enumerate(final_video_order[:limit], start = 1) :
            reranked = video_index in candidate_video_set
            best_physical = candidate_best_physical.get(video_index)
            hit_windows = self._supporting_windows(
                video_index,
                all_window_scores,
                reranker_by_physical,
                final_by_physical,
                requested_windows,
            )
            hits.append(
                ASRVideoHit(
                    rank = final_rank,
                    video_id = self._video_ids[video_index],
                    first_stage_rank = first_stage_rank_by_video[video_index],
                    first_stage_score = float(video_scores[video_index]),
                    reranker_score = (
                        reranker_by_physical.get(best_physical)
                        if best_physical is not None
                        else None
                    ),
                    final_score = candidate_video_final.get(video_index),
                    reranked = reranked,
                    windows = hit_windows,
                )
            )

        result_build_ms = self._elapsed_ms(result_started)
        total_ms = self._elapsed_ms(total_started)
        timings = SearchTimings(
            total_ms = total_ms,
            bm25_ms = bm25_ms,
            e5_encode_ms = e5_encode_ms,
            dense_search_ms = dense_search_ms,
            first_stage_fusion_ms = first_stage_fusion_ms,
            video_aggregation_ms = video_aggregation_ms,
            candidate_selection_ms = candidate_selection_ms,
            bge_ms = bge_ms,
            candidate_fusion_ms = candidate_fusion_ms,
            result_build_ms = result_build_ms,
            candidate_pair_count = candidate_pair_count,
            reranker_batch_size = reranker_batch_size,
        )
        return ASRSearchResult(
            query = text,
            mode = "first_stage" if first_stage_only else "reranked",
            release_id = self.release.manifest.release_id,
            hits = tuple(hits),
            timings = timings,
        )

    def close(self) -> None :
        if (self._state == "CLOSED") :
            return
        try :
            self.e5.close()
        finally :
            if (self.reranker is not None) :
                self.reranker.close()
            self._state = "CLOSED"

    def __enter__(self) -> "ASRRetrievalEngine" :
        if (self._state != "READY") :
            raise RuntimeError("ASR retrieval engine is not ready")
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None :
        self.close()
