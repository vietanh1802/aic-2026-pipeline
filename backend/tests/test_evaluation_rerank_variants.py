# backend/tests/test_evaluation_rerank_variants.py
"""rerank_variants: the "shipped" variant equals production rerank_one_model exactly, the other
neighbourhoods pick the frames they claim to, and the "variant" rerank mode goes through the shared
search without disturbing the memo the other arms read.

A small fake corpus: two videos, one with stored neighbour links and one on the fallback path, a vector
per frame, and three models that share one id space (as CLIP-id mapping does for BEiT-3 in production).
"""
from __future__ import annotations

import copy

import numpy as np
import pytest

from app import preprocess
from app.evaluation import rerank_variants, shared_search
from app.evaluation.config import RerankVariant, RunConfig, config_hash

DIM = 8


class FakeIndex :
    def __init__(self, vectors : np.ndarray) :
        self.vectors = vectors
        self.ntotal = len(vectors)

    def reconstruct(self, i : int) :
        return self.vectors[i]


def _corpus() :
    rng = np.random.default_rng(7)
    meta = []
    # V01: 10 frames in 3 shots, stored links (offsets -3..-1, +1..+3, self excluded) as the corpus has them.
    # V02: 8 frames in 2 shots, no stored links (the fallback path).
    for video, n, shots, linked in (("V01", 10, (0, 0, 0, 1, 1, 1, 1, 2, 2, 2), True), ("V02", 8, (0, 0, 0, 0, 1, 1, 1, 1), False)) :
        base = len(meta)
        for k in range(n) :
            meta.append({
                "name" : f"{video}-{shots[k]:04d}-{k * 30}.jpg", "video" : video, "scene_id" : shots[k],
                "frame_idx" : k * 30, "timestamp_ms" : k * 1000, "fps" : 30.0,
                "faiss_id_clip" : base + k, "faiss_id_beit3" : base + k,
                "neighbors_clip" : [base + j for j in range(max(0, k - 3), min(n, k + 4)) if j != k] if linked else [],
            })
    vectors = rng.normal(size = (len(meta), DIM)).astype("float32")
    vectors /= np.linalg.norm(vectors, axis = 1, keepdims = True)
    return meta, vectors


@pytest.fixture()
def fake_corpus(monkeypatch) :
    meta, vectors = _corpus()
    index = FakeIndex(vectors)
    query = np.random.default_rng(3).normal(size = (1, DIM)).astype("float32")

    def encode(text) :
        return query

    def search_one(model, text, top_m) :
        scores = vectors @ query.ravel()
        order = np.argsort(-scores)[ : top_m]
        return [{"name" : meta[i]["name"], "faiss_id" : int(i), "score" : float(scores[i]), "raw_score" : float(scores[i]),
                 "video" : meta[i]["video"], "frame_idx" : meta[i]["frame_idx"], "timestamp" : ""} for i in order]

    video_frames : dict[str, list[dict]] = {}
    for m in meta :
        video_frames.setdefault(m["video"], []).append(m)
    monkeypatch.setattr(preprocess, "_meta", meta)
    monkeypatch.setattr(preprocess, "_meta_loaded", True)
    monkeypatch.setattr(preprocess, "_name2meta", {m["name"] : m for m in meta})
    monkeypatch.setattr(preprocess, "_clipid2meta", {m["faiss_id_clip"] : m for m in meta})
    monkeypatch.setattr(preprocess, "_video_frames", video_frames)
    monkeypatch.setattr(preprocess, "_model_parts", lambda model : (index, None, encode, "faiss_id_clip"))
    monkeypatch.setattr(preprocess, "_load_indexes", lambda : None)
    monkeypatch.setattr(preprocess, "_search_one", search_one)
    monkeypatch.setattr(preprocess, "_image_url", lambda name : f"img/{name}")
    monkeypatch.setattr(preprocess, "_has_image", lambda name : True)
    rerank_variants.clear_caches()
    shared_search.clear_memo()
    yield meta, vectors, query.ravel(), search_one
    rerank_variants.clear_caches()
    shared_search.clear_memo()


SHIPPED = RerankVariant()


def test_shipped_variant_equals_production_rerank_one_model(fake_corpus) :
    _meta, _vectors, _q, search_one = fake_corpus
    hits = search_one("clip", "q", 18)
    expected = preprocess.rerank_one_model(copy.deepcopy(hits), "q", "clip")
    actual = rerank_variants.rerank(copy.deepcopy(hits), "q", "clip", SHIPPED)
    assert [(h["name"], h["score"], h["n_neighbors"]) for h in actual] == [(h["name"], h["score"], h["n_neighbors"]) for h in expected]


def test_variant_mode_with_the_shipped_variant_equals_per_model_for_every_subset(fake_corpus) :
    for models in (["clip"], ["beit3", "clip"], ["beit3", "clip", "siglip2"]) :
        expected = shared_search.search("q", models, 10, 12, "per_model")
        actual = shared_search.search("q", models, 10, 12, "variant", SHIPPED)
        assert [(r["frame"], r["distance"], r["routes"]) for r in actual] == [(r["frame"], r["distance"], r["routes"]) for r in expected]


def test_a_variant_does_not_touch_the_raw_lists_the_rerank_off_arms_read(fake_corpus) :
    before = shared_search.search("q", ["clip"], 10, 12, "off")
    shared_search.search("q", ["clip"], 10, 12, "variant", RerankVariant(neighbourhood = "stored_style", aggregate = "mean", own_weight = 1.0))
    after = shared_search.search("q", ["clip"], 10, 12, "off")
    assert [(r["frame"], r["distance"]) for r in before] == [(r["frame"], r["distance"]) for r in after]


def _names(meta, ids) :
    by_id = {m["faiss_id_clip"] : m["name"] for m in meta}
    return sorted(by_id[i] for i in ids)


def test_neighbourhoods_pick_the_frames_they_claim(fake_corpus) :
    meta, _vectors, _q, _search = fake_corpus
    v2 = [m for m in meta if m["video"] == "V02"]
    frame = v2[3]                                                  # last frame of shot 0, on the fallback path
    shipped = rerank_variants.neighbour_ids(frame, "clip", SHIPPED)
    assert _names(meta, shipped) == sorted(m["name"] for m in v2[1 : 6])                      # -2..+2 with self
    stored = rerank_variants.neighbour_ids(frame, "clip", RerankVariant(neighbourhood = "stored_style"))
    assert _names(meta, stored) == sorted(m["name"] for m in v2[0 : 7] if m is not frame)     # -3..+3 without self
    shot = rerank_variants.neighbour_ids(frame, "clip", RerankVariant(neighbourhood = "same_shot"))
    assert _names(meta, shot) == sorted(m["name"] for m in v2[0 : 3])                         # shot 0 only
    window = rerank_variants.neighbour_ids(frame, "clip", RerankVariant(neighbourhood = "time_window", window_s = 2.0))
    assert _names(meta, window) == sorted(m["name"] for m in (v2[1], v2[2], v2[4], v2[5]))   # |t - 3 s| <= 2 s


def test_mean_and_own_weight_scores(fake_corpus) :
    meta, vectors, q, search_one = fake_corpus
    hit = next(h for h in search_one("clip", "q", 18) if h["name"] == meta[4]["name"])
    neighbours = [vectors[i] @ q for i in (1, 2, 3, 5, 6, 7)]
    own = float(vectors[4] @ q)
    mean = rerank_variants.rerank([dict(hit)], "q", "clip", RerankVariant(neighbourhood = "stored_style", aggregate = "mean"))[0]
    assert mean["score"] == pytest.approx(float(np.mean(neighbours))) and mean["n_neighbors"] == 6
    mixed = rerank_variants.rerank([dict(hit)], "q", "clip", RerankVariant(neighbourhood = "stored_style", aggregate = "mean", own_weight = 0.5))[0]
    assert mixed["score"] == pytest.approx(own + 0.5 * float(np.mean(neighbours)))


def test_a_frame_alone_in_its_shot_keeps_its_own_score_under_a_mean(fake_corpus) :
    meta, vectors, q, search_one = fake_corpus
    lone = dict(meta[0], scene_id = 9)
    hit = {"name" : lone["name"], "faiss_id" : 0, "score" : 0.3, "raw_score" : 0.3, "video" : "V01", "frame_idx" : 0, "timestamp" : ""}
    preprocess._name2meta[lone["name"]] = lone
    out = rerank_variants.rerank([hit], "q", "clip", RerankVariant(neighbourhood = "same_shot", aggregate = "mean"))[0]
    assert out["n_neighbors"] == 0 and out["score"] == pytest.approx(0.3)


def test_config_hash_of_older_configs_is_unchanged_and_variants_differ() :
    import hashlib
    import json

    plain = RunConfig(rerank_mode = "per_model")
    # The hash as computed before the field existed: every field but name, the new one absent.
    old_payload = {k : v for k, v in plain.model_dump().items() if k not in ("name", "rerank_variant")}
    old_hash = hashlib.sha256(json.dumps(old_payload, sort_keys = True, separators = (",", ":"), ensure_ascii = False).encode("utf-8")).hexdigest()
    assert config_hash(plain) == old_hash
    a = RunConfig(rerank_mode = "variant", rerank_variant = RerankVariant(neighbourhood = "same_shot", aggregate = "mean"))
    b = RunConfig(rerank_mode = "variant", rerank_variant = RerankVariant(neighbourhood = "same_shot", aggregate = "sum"))
    assert len({config_hash(plain), config_hash(a), config_hash(b)}) == 3
    with pytest.raises(ValueError) :
        RunConfig(rerank_mode = "variant")
    with pytest.raises(ValueError) :
        RunConfig(rerank_mode = "off", rerank_variant = RerankVariant())


# ─── the development grid, the selection script and the final table ────────

def test_rerank_diag_is_the_declared_grid_on_both_expand_texts() :
    from app.evaluation.presets import preset_configs

    configs = preset_configs("rerank_diag")
    codes = [c.name.split()[0] for c in configs]
    assert codes == [f"R{i:02d}S" for i in range(1, 13)] + [f"R{i:02d}K" for i in range(1, 13)]
    assert len({config_hash(c) for c in configs}) == 24
    assert all(c.models == ["beit3", "clip", "siglip2"] for c in configs)
    assert {c.text_policy for c in configs[ : 12]} == {"expand_gemini"} and {c.text_policy for c in configs[12 : ]} == {"expand_keywords"}
    assert configs[0].rerank_mode == "off" and configs[1].rerank_variant == RerankVariant()


def _diag_csv(path, scores, extra_rows = ()) :
    import csv

    from app.evaluation.presets import preset_configs

    fields = ["config", "benchmark", "flags", "task_type", "prefix", "n", "failed", "hit_at_1", "r_at_5", "r_at_10", "mrr"]
    with path.open("w", encoding = "utf-8", newline = "") as handle :
        writer = csv.DictWriter(handle, fieldnames = fields)
        writer.writeheader()
        for config in preset_configs("rerank_diag") :
            hit, mrr = scores.get(config.name.split()[0], (0.30, 0.40))
            writer.writerow({"config" : config.name, "benchmark" : "A", "flags" : "all", "task_type" : "all", "prefix" : "all",
                             "n" : 86, "failed" : 0, "hit_at_1" : hit, "r_at_5" : 0.6, "r_at_10" : 0.7, "mrr" : mrr})
        for row in extra_rows :
            writer.writerow(row)


def _select(monkeypatch, run_dir, out) :
    import importlib
    import sys
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    sys.modules.pop("select_rerank_variant", None)
    script = importlib.import_module("select_rerank_variant")
    monkeypatch.setattr(sys, "argv", ["select_rerank_variant.py", "--run-dir", str(run_dir), "--out", str(out)])
    return script.main()


def test_selection_picks_text_first_then_variant_and_ties_go_by_mrr(monkeypatch, tmp_path) :
    import json

    run = tmp_path / "run"
    run.mkdir()
    # Keywords beat the sentence with rerank off; R05K and R11K tie on Hit@1, R11K has the higher MRR.
    # R03S is the best of all rows but on the text that lost step 1, so it cannot win.
    _diag_csv(run / "results_long.csv", {"R01S" : (0.40, 0.50), "R01K" : (0.42, 0.50), "R03S" : (0.60, 0.70),
                                         "R05K" : (0.45, 0.55), "R11K" : (0.45, 0.56)})
    out = tmp_path / "frozen.json"
    assert _select(monkeypatch, run, out) == 0
    frozen = json.loads(out.read_text(encoding = "utf-8"))
    assert frozen["text_policy"] == "expand_keywords" and frozen["winner"].startswith("R11K ")
    assert len(frozen["candidates"]) == 24 and frozen["config"]["rerank_variant"]["own_weight"] == 0.5


def test_selection_refuses_a_run_that_holds_benchmark_b(monkeypatch, tmp_path) :
    run = tmp_path / "run"
    run.mkdir()
    b_row = {"config" : "R01S rerank off, Expand sentence", "benchmark" : "B", "flags" : "all", "task_type" : "all", "prefix" : "all",
             "n" : 28, "failed" : 0, "hit_at_1" : 0.5, "r_at_5" : 0.6, "r_at_10" : 0.7, "mrr" : 0.6}
    _diag_csv(run / "results_long.csv", {}, [b_row])
    with pytest.raises(SystemExit, match = "Benchmark B") :
        _select(monkeypatch, run, tmp_path / "frozen.json")


def test_final_table_reads_the_frozen_selection(monkeypatch, tmp_path) :
    import json

    from app.evaluation import presets

    winner = RunConfig(name = "R11K x", text_policy = "expand_keywords", rerank_mode = "variant",
                       rerank_variant = RerankVariant(neighbourhood = "same_shot", aggregate = "mean", own_weight = 0.5))
    frozen = tmp_path / "frozen_selection.json"
    frozen.write_text(json.dumps({"config" : json.loads(winner.model_dump_json())}), encoding = "utf-8")
    monkeypatch.setattr(presets, "FROZEN_SELECTION", frozen)
    rows = {c.name.split()[0] : c for c in presets.preset_configs("final_table")}
    assert list(rows) == ["F01", "F02", "F03", "F04", "F05", "F06", "F07"]
    assert rows["F01"].rerank_variant == winner.rerank_variant and rows["F01"].models == ["beit3", "clip", "siglip2"]
    assert rows["F02"].rerank_mode == "off" and rows["F02"].rerank_variant is None
    assert rows["F03"].text_policy == "translate_gtx" and rows["F07"].text_policy == "expand_gemini"
    assert rows["F04"].models == ["clip", "siglip2"] and rows["F01"].text_filter.sources == ["ocr", "asr"]
    assert len({config_hash(c) for c in rows.values()}) == 7

    off = RunConfig(name = "R01S x", text_policy = "expand_gemini", rerank_mode = "off")
    frozen.write_text(json.dumps({"config" : json.loads(off.model_dump_json())}), encoding = "utf-8")
    assert [c.name.split()[0] for c in presets.preset_configs("final_table")] == ["F01", "F03", "F04", "F05", "F06", "F07"]
    monkeypatch.setattr(presets, "FROZEN_SELECTION", tmp_path / "absent.json")
    with pytest.raises(ValueError, match = "select_rerank_variant") :
        presets.preset_configs("final_table")
