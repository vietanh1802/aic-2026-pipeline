# backend/app/evaluation/shared_search.py
"""Arm sharing for the ablation suite: search and rerank each model once per query text, then fuse
any subset of models from the stored per-model lists.

Why this is valid. In preprocess.ensemble_search each model's retrieval (_search_one) and neighbour
rerank (rerank_one_model) use only that model's index and the shared metadata. They do not depend on
which other models are active. Only the final _merge_ensemble does (weights renormalised over the
models that returned hits, each model divided by its own maximum score), and that is a pure function
of the per-model lists. So memoising the per-model lists and calling the production _merge_ensemble
on a subset reproduces ensemble_search(models = subset) by construction, ties included, provided the
models are fed in canonical order.

preprocess.py is not modified. Its private helpers are imported lazily, so importing this module
does not load torch or faiss.

rerank_mode
  per_model     the shipped pipeline: search -> rerank each model -> fuse
  off           search -> fuse on the raw cosine scores (ensemble_search(use_rerank = False))
  variant       search -> rerank each model with rerank_variants.rerank(variant) -> fuse. The variant
                "shipped/sum/own none" equals per_model; the others are the development grid.
  after_fusion  the order before commit d09cf9b (2026-08-05): fuse the raw per-model lists first,
                then rerank the fused list with neighbour scores. RE-CREATED, not recovered: git
                history has no code for it (the commit before d09cf9b has no rerank at all), so this
                follows its documented description, "ensemble first, then rerank the fused list".
                Concretely: the candidate pool is the fused list of the raw per-model lists; every
                candidate gets its neighbour score under every model (rerank_one_model, the same
                Algorithm 2 used per model); those lists are fused again with _merge_ensemble. With a
                single model this equals per_model, and in general the difference is that a frame
                found by one model also receives neighbour evidence from the others.
"""
from __future__ import annotations

import copy
import hashlib
import time
from typing import Any

from app.evaluation.config import CANONICAL_MODELS

_MEMO : dict[tuple[str, str, int], dict[str, Any]] = {}
_MEMO_LIMIT = 8192

# Timing of the most recent search() call, for the runner to persist per query (model_timings). One
# suite worker thread calls search(), so a module global is enough; it is replaced on every call.
_LAST : dict[str, Any] = {}


def _pp() :
    from app import preprocess
    return preprocess


def clear_memo() -> None :
    _MEMO.clear()
    _VARIANT_MEMO.clear()


def _text_hash(text : str) -> str :
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _entry(text : str, model : str, top_m : int) -> tuple[dict[str, Any], bool] :
    """The memo entry of (text, model, top_m) and whether it was already there.

    Besides the two lists the entry holds search_ms (text encoding plus the FAISS scan, one call to
    preprocess._search_one) and rerank_ms (rerank_one_model on those hits), measured when the entry is
    FIRST computed. A later arm that reuses it pays nothing, so the wall-clock time of an arm in the
    database is not its cost; the cost of a configuration is rebuilt offline as the sum of its models'
    stored search_ms and rerank_ms plus its fusion time."""
    key = (_text_hash(text), model, top_m)
    cached = _MEMO.get(key)
    if (cached is not None) :
        return cached, True
    pp = _pp()
    started = time.perf_counter()
    hits = pp._search_one(model, text, top_m)
    search_ms = (time.perf_counter() - started) * 1000.0
    if (not hits) :
        entry = {"raw" : [], "reranked" : [], "search_ms" : search_ms, "rerank_ms" : 0.0}
    else :
        raw = copy.deepcopy(hits)
        started = time.perf_counter()
        reranked = pp.rerank_one_model(hits, text, model)
        entry = {"raw" : raw, "reranked" : reranked, "search_ms" : search_ms, "rerank_ms" : (time.perf_counter() - started) * 1000.0}
    if (len(_MEMO) >= _MEMO_LIMIT) :
        _MEMO.pop(next(iter(_MEMO)))
    _MEMO[key] = entry
    return entry, False


def per_model_hits(text : str, model : str, top_m : int) -> dict[str, Any] :
    """{"raw": hits as _search_one returns them, "reranked": the same after Algorithm 2, plus the
    search_ms and rerank_ms of the first computation}.

    rerank_one_model rewrites each hit's score in place, so the raw list is copied first."""
    return _entry(text, model, top_m)[0]


def last_timing() -> dict[str, Any] :
    """Timing of the most recent search(): per model {search_ms, rerank_ms, reused}, fuse_ms, and for
    after_fusion pool_rerank_ms per model. Empty before the first call."""
    return copy.deepcopy(_LAST)


def _after_fusion(text : str, models : list[str], top_k : int, top_m : int, timing : dict[str, Any]) -> list[dict] :
    pp = _pp()
    entries = {m : _entry(text, m, top_m) for m in models}
    timing["models"] = {m : {"search_ms" : e["search_ms"], "rerank_ms" : e["rerank_ms"], "reused" : reused} for m, (e, reused) in entries.items()}
    raw = {m : e["raw"] for m, (e, _reused) in entries.items() if e["raw"]}
    timing["pool_rerank_ms"] = {}
    timing["fuse_ms"] = 0.0
    if (not raw) :
        return []

    # 1. fuse the raw lists. The fused list, not top_k, is the candidate pool.
    pool_size = sum(len(hits) for hits in raw.values())
    started = time.perf_counter()
    fused = pp._merge_ensemble(raw, pool_size)
    timing["fuse_ms"] += (time.perf_counter() - started) * 1000.0

    # 2. every candidate gets its neighbour score under every active model.
    # rerank_one_model reads only h["name"] (to find the frame's neighbours) and overwrites h["score"]
    # and h["n_neighbors"]; faiss_id is never read, so -1 is harmless. raw_score is used only by
    # _merge_ensemble for the route cosine shown in "routes" and never affects the ranking. A frame
    # outside this model's own top_m has no stored cosine, so it shows 0.0 there: a display
    # placeholder, not a measurement.
    cosine = {m : {h["name"] : h["raw_score"] for h in hits} for m, hits in raw.items()}
    rescored : dict[str, list[dict]] = {}
    for model in raw :
        pool = [
            {
                "name"      : row["name"],
                "faiss_id"  : -1,
                "score"     : 0.0,
                "raw_score" : cosine[model].get(row["name"], 0.0),
                "video"     : row.get("video"),
                "frame_idx" : row.get("frame_idx"),
                "timestamp" : row.get("timestamp", ""),
            }
            for row in fused
        ]
        started = time.perf_counter()
        rescored[model] = pp.rerank_one_model(pool, text, model)
        timing["pool_rerank_ms"][model] = (time.perf_counter() - started) * 1000.0

    # 3. fuse the rescored lists, as the shipped merge does.
    started = time.perf_counter()
    merged = pp._merge_ensemble(rescored, top_k)
    timing["fuse_ms"] += (time.perf_counter() - started) * 1000.0
    return merged


_VARIANT_MEMO : dict[tuple[str, str, int, str], tuple[list[dict], float]] = {}


def _variant(text : str, models : list[str], top_k : int, top_m : int, variant, timing : dict[str, Any]) -> list[dict] :
    """Per-model search from the shared memo, then the variant rerank of a COPY of the raw list (the memo's
    lists stay untouched for the other arms), then the production merge."""
    from app.evaluation import rerank_variants

    if (variant is None) :
        raise ValueError("rerank_mode variant needs a variant")
    pp = _pp()
    label = rerank_variants.variant_key(variant)
    timing["variant"] = label
    timing["models"] = {}
    per_model : dict[str, list[dict]] = {}
    for model in models :
        entry, reused = _entry(text, model, top_m)
        key = (_text_hash(text), model, top_m, label)
        cached = _VARIANT_MEMO.get(key)
        if (cached is None) :
            started = time.perf_counter()
            hits = rerank_variants.rerank(copy.deepcopy(entry["raw"]), text, model, variant) if entry["raw"] else []
            cached = (hits, (time.perf_counter() - started) * 1000.0)
            if (len(_VARIANT_MEMO) >= _MEMO_LIMIT) :
                _VARIANT_MEMO.pop(next(iter(_VARIANT_MEMO)))
            _VARIANT_MEMO[key] = cached
        timing["models"][model] = {"search_ms" : entry["search_ms"], "rerank_ms" : cached[1], "reused" : reused}
        if (cached[0]) :
            per_model[model] = copy.deepcopy(cached[0])
    started = time.perf_counter()
    rows = pp._merge_ensemble(per_model, top_k)
    timing["fuse_ms"] = (time.perf_counter() - started) * 1000.0
    return rows


def search(
    text : str,
    models : list[str],
    top_k : int = 100,
    top_m : int = 50,
    rerank_mode : str = "per_model",
    variant = None,
) -> list[dict] :
    """Same rows as preprocess.ensemble_search(text, top_k, top_m, use_rerank, models) for
    per_model and off; the after_fusion order for after_fusion."""
    pp = _pp()
    pp._load_indexes()
    pp._load_meta()
    ordered = [m for m in CANONICAL_MODELS if m in models and m in pp.MODEL_NAMES]
    timing : dict[str, Any] = {"rerank_mode" : rerank_mode}

    if (rerank_mode == "after_fusion") :
        rows = _after_fusion(text, ordered, top_k, top_m, timing)
        _LAST.clear()
        _LAST.update(timing)
        return rows
    if (rerank_mode == "variant") :
        rows = _variant(text, ordered, top_k, top_m, variant, timing)
        _LAST.clear()
        _LAST.update(timing)
        return rows
    if (rerank_mode not in ("per_model", "off")) :
        raise ValueError(f"unknown rerank_mode {rerank_mode}")

    field = "reranked" if rerank_mode == "per_model" else "raw"
    per_model : dict[str, list[dict]] = {}
    timing["models"] = {}
    for model in ordered :
        entry, reused = _entry(text, model, top_m)
        timing["models"][model] = {"search_ms" : entry["search_ms"], "rerank_ms" : entry["rerank_ms"], "reused" : reused}
        if (entry[field]) :
            per_model[model] = entry[field]
    started = time.perf_counter()
    rows = pp._merge_ensemble(per_model, top_k)
    timing["fuse_ms"] = (time.perf_counter() - started) * 1000.0
    _LAST.clear()
    _LAST.update(timing)
    return rows


def memo_size() -> int :
    return len(_MEMO)


def describe() -> dict[str, Any] :
    return {"memo_entries" : len(_MEMO), "canonical_models" : list(CANONICAL_MODELS)}
