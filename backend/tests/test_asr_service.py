from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from asr_api import runtime as asr_service

def _reset_service(monkeypatch) :
    monkeypatch.setattr(asr_service, "_engine", None)
    monkeypatch.setattr(asr_service, "_manifest", None)
    monkeypatch.setattr(asr_service, "_state", "cold")
    monkeypatch.setattr(asr_service, "_error", None)


def _settings(enabled : bool = True) -> asr_service.ASRSettings :
    return asr_service.ASRSettings(
        enabled = enabled,
        release_path = Path("artifacts/asr/releases/aic2026-full-20260817-r01"),
        device = "cpu",
        top_k = 50,
        windows_per_hit = 3,
        warmup = False,
    )


def test_get_asr_engine_loads_once(monkeypatch) :
    _reset_service(monkeypatch)
    engine = object()
    calls = []

    monkeypatch.setattr(asr_service, "get_asr_settings", lambda : _settings())

    def fake_build(settings) :
        calls.append(settings)
        return SimpleNamespace(release_id = asr_service.RELEASE_ID), engine

    monkeypatch.setattr(asr_service, "_build_engine", fake_build)

    assert asr_service.get_asr_engine() is engine
    assert asr_service.get_asr_engine() is engine
    assert len(calls) == 1
    assert asr_service.asr_status()["state"] == "ready"


def test_disabled_asr_does_not_load(monkeypatch) :
    _reset_service(monkeypatch)
    monkeypatch.setattr(asr_service, "get_asr_settings", lambda : _settings(enabled = False))

    with pytest.raises(RuntimeError, match = "disabled") :
        asr_service.get_asr_engine()

    assert asr_service.asr_status()["state"] == "disabled"


def test_failed_load_is_reported(monkeypatch) :
    _reset_service(monkeypatch)
    monkeypatch.setattr(asr_service, "get_asr_settings", lambda : _settings())

    def fake_build(settings) :
        raise RuntimeError("broken release")

    monkeypatch.setattr(asr_service, "_build_engine", fake_build)

    with pytest.raises(RuntimeError, match = "broken release") :
        asr_service.get_asr_engine()

    status = asr_service.asr_status()
    assert status["state"] == "failed"
    assert "broken release" in status["error"]


def test_search_preserves_authoritative_asr_order(monkeypatch) :
    _reset_service(monkeypatch)
    monkeypatch.setattr(asr_service, "get_asr_settings", lambda : _settings())

    window_a = SimpleNamespace(
        window_id = "A-w0",
        video_id = "A",
        start_s = 0.0,
        end_s = 60.0,
        transcript = "alpha",
        first_stage_score = 0.4,
        reranker_score = 0.1,
        final_score = 0.2,
        reranked = True,
    )
    window_b = SimpleNamespace(
        window_id = "B-w0",
        video_id = "B",
        start_s = 45.0,
        end_s = 105.0,
        transcript = "beta",
        first_stage_score = 0.8,
        reranker_score = 99.0,
        final_score = 99.0,
        reranked = True,
    )
    hits = (
        SimpleNamespace(
            rank = 1,
            video_id = "A",
            first_stage_rank = 2,
            first_stage_score = 0.4,
            reranker_score = 0.1,
            final_score = 0.2,
            reranked = True,
            windows = (window_a,),
        ),
        SimpleNamespace(
            rank = 2,
            video_id = "B",
            first_stage_rank = 1,
            first_stage_score = 0.8,
            reranker_score = 99.0,
            final_score = 99.0,
            reranked = True,
            windows = (window_b,),
        ),
    )
    timings = SimpleNamespace(
        total_ms = 1.0,
        bm25_ms = 0.1,
        e5_encode_ms = 0.1,
        dense_search_ms = 0.1,
        first_stage_fusion_ms = 0.1,
        video_aggregation_ms = 0.1,
        candidate_selection_ms = 0.1,
        bge_ms = 0.1,
        candidate_fusion_ms = 0.1,
        result_build_ms = 0.1,
        candidate_pair_count = 2,
        reranker_batch_size = 2,
    )

    class FakeEngine :
        def search(self, query, **kwargs) :
            return SimpleNamespace(
                query = query,
                mode = "reranked",
                release_id = asr_service.RELEASE_ID,
                hits = hits,
                timings = timings,
            )

    monkeypatch.setattr(asr_service, "get_asr_engine", lambda : FakeEngine())
    result = asr_service.search_asr("query", top_k = 2)

    assert [hit["video_id"] for hit in result["hits"]] == ["A", "B"]
    assert [hit["rank"] for hit in result["hits"]] == [1, 2]
    assert result["hits"][1]["final_score"] == 99.0
    assert result["hits"][0]["windows"][0]["transcript"] == "alpha"
