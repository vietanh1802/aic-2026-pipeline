# backend/tests/test_evaluation_ablation_core.py
"""Core of the ablation benchmark: production defaults, arm sharing, preflight and replay.

Three things are pinned here:
  (a) a default RunConfig is what the production UI sends, except the baseline text policy;
  (b) the shared per-model search reproduces preprocess.ensemble_search for every model subset
      with per-model rerank and with rerank off (the after_fusion order is a different pipeline
      and is not part of this equality);
  (c) preflight answers 422 when a needed text is neither cached nor fetchable, and a run over a
      full cache makes no network or LLM call.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import re
from pathlib import Path

import pytest
from fastapi import HTTPException

from app import preprocess
from app.db.connection import utcnow_iso
from app.evaluation import diagnostics, shared_search, text_cache, verify
from app.evaluation.config import RunConfig
from app.evaluation.runner import process_run
from app.evaluation.seed import SEEDS_DIR, import_seed
from app.routers import evaluation as evaluation_router

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"
ROUND1 = SEEDS_DIR / "round1-v3.json"


# ─── (a) production defaults ───────────────────────────────────────────────

def test_default_run_config_equals_production_defaults() :
    from app import main

    config = RunConfig()
    request = main.EnsembleSearchRequest(query = "x")
    assert (config.top_k, config.top_m, config.use_rerank) == (request.limit, request.top_m, request.use_rerank)
    assert config.models == list(preprocess.MODEL_NAMES)

    store = (FRONTEND / "store" / "queryStore.ts").read_text(encoding = "utf-8")
    models = re.search(r"ensembleModels: \[([^\]]*)\]", store).group(1)
    assert config.models == re.findall(r'"(\w+)"', models)
    assert config.top_m == int(re.search(r"topM: (\d+)", store).group(1))
    assert config.top_k == int(re.search(r'resultLimit: "(\d+)"', store).group(1))
    assert re.search(r"useRerank: true", store)

    # The temporal route sits next to it with a different gap, so read only the TRAKE function.
    api = (FRONTEND / "types" / "api.ts").read_text(encoding = "utf-8")
    trake_call = api[api.index("async trakeSearchText(") : ]
    assert config.trake.gap_c == int(re.search(r"gap_c: options\?\.gapC \?\? (\d+)", trake_call).group(1))
    assert config.trake.local_model == re.search(r'model: options\?\.model \?\? "(\w+)"', trake_call).group(1)
    assert config.trake.top_videos == int(re.search(r"topVideos: (\d+)", (FRONTEND / "App.tsx").read_text(encoding = "utf-8")).group(1))

    # The one deliberate difference: production has no automatic text step.
    assert config.rerank_mode == "per_model"
    assert config.task_mode == "ensemble"
    assert config.text_policy == "translate_gtx"


# ─── (b) shared search equals ensemble_search ──────────────────────────────

def _unit(*parts : str) -> float :
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[ : 4], "big") / 2**32


def _fake_search_one(model : str, query : str, top_m : int) -> list[dict] :
    if (model == "siglip2" and query == "q-empty") :
        return []
    hits = []
    for index in range(60) :
        name = f"V{index % 7:02d}-0001-{index}.jpg"
        # Each model covers a different part of the corpus, like indexes of different completeness.
        if (model == "clip" and index % 5 == 0) or (model == "siglip2" and index % 3 == 0) :
            continue
        # Eighths on purpose: many equal scores, so tie order is exercised.
        score = 0.5 + round(_unit(model, query, name) * 8) / 16
        hits.append({
            "name" : name, "faiss_id" : index, "score" : score, "raw_score" : score,
            "video" : name.split("-")[0], "frame_idx" : index, "timestamp" : "",
        })
    hits.sort(key = lambda h : -h["score"])
    return hits[ : top_m]


def _fake_rerank(hits : list[dict], query : str, model : str) -> list[dict] :
    for hit in hits :
        total = round(_unit("rr", model, query, hit["name"]) * 6) - 1
        # q-neg makes one model's scores all negative, which hits the s_max fallback in the merge.
        hit["score"] = -abs(total) - 1.0 if (model == "beit3" and query == "q-neg") else float(total)
        hit["n_neighbors"] = 3
    hits.sort(key = lambda h : -h["score"])
    return hits


@pytest.fixture()
def fake_preprocess(monkeypatch) :
    monkeypatch.setattr(preprocess, "_load_indexes", lambda : None)
    monkeypatch.setattr(preprocess, "_load_meta", lambda : None)
    monkeypatch.setattr(preprocess, "_search_one", _fake_search_one)
    monkeypatch.setattr(preprocess, "rerank_one_model", _fake_rerank)
    monkeypatch.setattr(preprocess, "_image_url", lambda name : f"img/{name}")
    monkeypatch.setattr(preprocess, "_has_image", lambda name : True)
    shared_search.clear_memo()
    yield
    shared_search.clear_memo()


@pytest.mark.parametrize("query", ["q-a", "q-empty", "q-neg"])
def test_shared_search_equals_ensemble_search_for_every_subset(fake_preprocess, query) :
    subsets = [list(combo) for size in (1, 2, 3) for combo in itertools.combinations(preprocess.MODEL_NAMES, size)]
    assert len(subsets) == 7
    for subset in subsets :
        for mode, use_rerank in (("per_model", True), ("off", False)) :
            expected = preprocess.ensemble_search(query, top_k = 100, top_m = 20, use_rerank = use_rerank, models = subset)
            actual = shared_search.search(query, list(reversed(subset)), 100, 20, mode)
            assert actual == expected, (query, subset, mode)
    # The three models were searched once each however many arms asked.
    assert shared_search.memo_size() == 3


@pytest.mark.parametrize("query", ["q-a", "q-neg"])
def test_after_fusion_with_a_single_model_equals_per_model(fake_preprocess, query) :
    for model in preprocess.MODEL_NAMES :
        expected = shared_search.search(query, [model], 100, 20, "per_model")
        actual = shared_search.search(query, [model], 100, 20, "after_fusion")
        assert verify.first_difference(expected, actual) is None, (query, model)
        assert expected, model


# ─── (c) preflight and replay ──────────────────────────────────────────────

def _admin(conn) :
    cursor = conn.execute(
        "INSERT INTO users (username, display_name, role, password_hash, "
        "must_change_password, disabled, created_at) VALUES ('admin', 'admin', 'admin', 'x', 0, 0, ?)",
        (utcnow_iso(),),
    )
    return conn.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()


def _fill_cache(conn, policy : str) -> int :
    rows = text_cache.query_rows(conn, "round1-v3")
    for row in rows :
        task = row["task_type"] if policy == "expand_gemini" else ""
        key = text_cache.make_key(policy, row["query_vi"], task)
        output = {"eng_query" : f"EN::{row['query_key']}", "check_units" : ["a"]} if policy == "expand_gemini" else {"text" : f"EN::{row['query_key']}"}
        text_cache.store(conn, key, row["query_vi"], output, "gemini" if policy == "expand_gemini" else "google_gtx")
    return len(rows)


def _request(policy : str) -> evaluation_router.EvaluationRunCreate :
    return evaluation_router.EvaluationRunCreate(
        dataset_version = "round1-v3", reference_set_version = "r1-manual-v3", config = {"text_policy" : policy},
    )


def test_preflight_422_on_missing_key_and_missing_cache(conn, monkeypatch) :
    monkeypatch.delenv("GEMINI_API_KEY", raising = False)
    monkeypatch.setattr(evaluation_router, "enqueue_run", lambda run_id : None)
    user = _admin(conn)
    import_seed(conn, ROUND1)

    # Expand needs the key; nothing is cached; no key: refused before a run exists.
    with pytest.raises(HTTPException) as refused :
        evaluation_router.start_run(_request("expand_gemini"), user, conn)
    assert refused.value.status_code == 422
    assert refused.value.detail["missing"] == 24
    assert refused.value.detail["blocked_policies"] == ["expand_gemini"]
    assert len(refused.value.detail["first_missing"]) == 20
    assert conn.execute("SELECT COUNT(*) FROM evaluation_runs").fetchone()[0] == 0

    # gtx needs no key: the same empty cache is accepted and left to prefetch.
    assert evaluation_router.start_run(_request("translate_gtx"), user, conn)["run"]["status"] == "queued"

    # Expand with every text cached is accepted even without a key.
    conn.execute("DELETE FROM evaluation_runs")
    _fill_cache(conn, "expand_gemini")
    run = evaluation_router.start_run(_request("expand_gemini"), user, conn)["run"]
    assert run["configuration"]["config"]["text_policy"] == "expand_gemini"
    assert run["configuration"]["use_rerank"] is True


def test_replay_over_a_full_cache_makes_no_network_call(conn, monkeypatch) :
    from app import expansion, translation
    import urllib.request

    monkeypatch.delenv("GEMINI_API_KEY", raising = False)
    monkeypatch.setattr(evaluation_router, "enqueue_run", lambda run_id : None)
    user = _admin(conn)
    import_seed(conn, ROUND1)
    count = _fill_cache(conn, "translate_gtx")

    calls : list[str] = []

    def _forbidden(*args, **kwargs) :
        calls.append("network")
        raise AssertionError("the network must not be touched when the cache is full")

    monkeypatch.setattr(translation, "translate_vi_to_en", _forbidden)
    monkeypatch.setattr(expansion, "expand_query", _forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", _forbidden)

    def _stub_search(text, models, top_k, top_m, rerank_mode) :
        return [{"video" : "L21_V001", "name" : "L21_V001-0001-1.jpg", "frame_idx" : 1, "distance" : 1.0}]

    monkeypatch.setattr(shared_search, "search", _stub_search)

    run = evaluation_router.start_run(_request("translate_gtx"), user, conn)["run"]
    process_run(run["id"], runtime_snapshot_fn = lambda : {"device" : "test"})

    row = conn.execute("SELECT status, completed_count, failed_count FROM evaluation_runs WHERE id = ?", (run["id"],)).fetchone()
    assert (row["status"], row["completed_count"], row["failed_count"]) == ("completed", count, 0)
    first = conn.execute(
        "SELECT query_en, translation_ms FROM evaluation_query_results WHERE run_id = ? ORDER BY ordinal LIMIT 1", (run["id"],)
    ).fetchone()
    assert first["query_en"].startswith("EN::") and first["translation_ms"] == 0.0
    assert calls == []


# ─── annotation is a side feature ──────────────────────────────────────────

def test_annotation_failures_are_recorded_and_never_cost_a_query_its_ranking(conn, monkeypatch) :
    from app import asr_text, ocr_search, text_signal
    from app.evaluation import report

    monkeypatch.setattr(evaluation_router, "enqueue_run", lambda run_id : None)
    user = _admin(conn)
    import_seed(conn, ROUND1)
    _fill_cache(conn, "translate_gtx")

    refs = [row["video_id"] for row in text_cache.query_rows(conn, "round1-v3")]
    pool = list(dict.fromkeys(refs))

    def stub_search(text, models, top_k, top_m, rerank_mode) :
        return [{"video" : v, "name" : f"{v}-0001-1.jpg", "frame_idx" : 1, "distance" : 1.0} for v in pool]

    def missing_files(*args, **kwargs) :
        raise FileNotFoundError("no OCR file for this video")

    monkeypatch.setattr(shared_search, "search", stub_search)
    monkeypatch.setattr(text_signal, "annotate_request", missing_files)      # annotation raises
    monkeypatch.setattr(preprocess, "frames_for_video", lambda video : [f"{video}-0001-1.jpg"])
    monkeypatch.setattr(ocr_search, "get_text", missing_files)               # coverage raises for OCR
    monkeypatch.setattr(asr_text, "get_text", lambda name : "")
    monkeypatch.setattr(asr_text, "status", lambda : {"ready" : True})        # a loaded index that has no text for these frames

    request = evaluation_router.EvaluationRunCreate(
        dataset_version = "round1-v3", reference_set_version = "r1-manual-v3",
        config = {"text_policy" : "translate_gtx", "text_filter" : {"sources" : ["ocr", "asr"]}},
    )
    run = evaluation_router.start_run(request, user, conn)["run"]
    process_run(run["id"], runtime_snapshot_fn = lambda : {"device" : "test"})

    stored = conn.execute("SELECT status, completed_count, failed_count FROM evaluation_runs WHERE id = ?", (run["id"],)).fetchone()
    assert (stored["status"], stored["completed_count"], stored["failed_count"]) == ("completed", 24, 0)

    rows = report.load_rows(conn, [run["id"]])
    assert len(rows) == 24
    for row in rows :
        assert row["status"] == "completed"
        assert row["reference_video_rank"] == pool.index(row["reference_video"]) + 1      # the ranking is intact
    assert report.metrics(rows)["hit_at_1"] == pytest.approx(sum(1 for r in refs if r == pool[0]) / 24)

    errors = [e for row in rows for e in (row["extra"] or {}).get("text_signal_errors", [])]
    assert {e["part"] for e in errors} == {"annotation", "coverage"}
    assert {e["error_type"] for e in errors} == {"FileNotFoundError"}
    assert {e["variant"] for e in errors if e["part"] == "annotation"} == {"ocr", "asr", "both"}
    assert {e["source"] for e in errors if e["part"] == "coverage"} == {"ocr"}
    # The report shows the count.
    assert report.metrics(rows)["annotation_errors"] == len(errors) > 0


# ─── what the analysis needs is persisted per query ────────────────────────

def test_search_reports_per_model_timings_and_marks_reused_entries(fake_preprocess) :
    shared_search.search("q-a", ["beit3", "clip"], 100, 20, "per_model")
    first = shared_search.last_timing()
    assert set(first["models"]) == {"beit3", "clip"}
    assert all(not m["reused"] and m["search_ms"] >= 0 and m["rerank_ms"] >= 0 for m in first["models"].values())
    assert first["fuse_ms"] >= 0 and first["rerank_mode"] == "per_model"

    # A later arm over the same text pays nothing for a model that is already memoised, and reports the
    # time of its first computation.
    shared_search.search("q-a", ["clip", "siglip2"], 100, 20, "off")
    second = shared_search.last_timing()
    assert second["models"]["clip"]["reused"] is True and second["models"]["siglip2"]["reused"] is False
    assert second["models"]["clip"]["search_ms"] == first["models"]["clip"]["search_ms"]

    shared_search.search("q-a", ["beit3", "clip", "siglip2"], 100, 20, "after_fusion")
    third = shared_search.last_timing()
    assert set(third["pool_rerank_ms"]) == {"beit3", "clip", "siglip2"} and third["fuse_ms"] >= 0


def test_interval_gap_inside_before_after_and_missing() :
    frames = [
        {"video" : "A", "frame_idx" : 50}, {"video" : "L1", "frame_idx" : 40}, {"video" : "L1", "frame_idx" : 130},
        {"video" : "L1", "frame_idx" : 155}, {"video" : "L1", "frame_idx" : 118},
    ]
    intervals = [{"start" : 100, "end" : 120}, {"start" : 300, "end" : 320}]
    gap = diagnostics.interval_gap(frames, "L1", intervals, 25.0)
    # 118 is inside the first interval (rank 5); 130 is 10 frames past it; 40 is 60 before it.
    assert (gap["gap_frames"], gap["nearest_frame_rank"], gap["nearest_frame_idx"], gap["inside"]) == (0, 5, 118, True)
    assert (gap["n_ref_frames"], gap["first_ref_frame_rank"]) == (4, 2)

    outside = diagnostics.interval_gap(frames[ : 4], "L1", intervals, 25.0)
    assert (outside["gap_frames"], outside["gap_s"], outside["inside"]) == (10, 0.4, False)

    assert diagnostics.interval_gap(frames, "L1", None, 25.0) is None                  # TRAKE: no interval
    missing = diagnostics.interval_gap(frames, "L9", intervals, 25.0)
    assert (missing["n_ref_frames"], missing["gap_frames"], missing["inside"]) == (0, None, False)


def test_configured_run_persists_model_timings_and_interval_gap(conn, monkeypatch, fake_preprocess) :
    monkeypatch.setattr(evaluation_router, "enqueue_run", lambda run_id : None)
    user = _admin(conn)
    import_seed(conn, ROUND1)
    _fill_cache(conn, "translate_gtx")
    request = evaluation_router.EvaluationRunCreate(
        dataset_version = "round1-v3", reference_set_version = "r1-manual-v3",
        config = {"text_policy" : "translate_gtx", "top_m" : 20},
    )
    run = evaluation_router.start_run(request, user, conn)["run"]
    process_run(run["id"], runtime_snapshot_fn = lambda : {"device" : "test"})

    rows = conn.execute("SELECT query_key, task_type, extra_json FROM evaluation_query_results WHERE run_id = ?", (run["id"],)).fetchall()
    assert len(rows) == 24
    for row in rows :
        extra = json.loads(row["extra_json"])
        assert set(extra["model_timings"]["models"]) == {"beit3", "clip", "siglip2"}
        assert extra["model_timings"]["fuse_ms"] >= 0
        # TRAKE has no interval; KIS and QA record the gap (the fake corpus never returns the reference video).
        assert ("interval_gap" in extra) == (row["task_type"] != "TRAKE")
        assert "text_signal_errors" not in extra
