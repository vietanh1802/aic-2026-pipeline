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
from typing import Any

from app.evaluation.config import CANONICAL_MODELS

_MEMO : dict[tuple[str, str, int], dict[str, list[dict]]] = {}
_MEMO_LIMIT = 8192


def _pp() :
    from app import preprocess
    return preprocess


def clear_memo() -> None :
    _MEMO.clear()


def _text_hash(text : str) -> str :
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def per_model_hits(text : str, model : str, top_m : int) -> dict[str, list[dict]] :
    """{"raw": hits as _search_one returns them, "reranked": the same after Algorithm 2}.

    rerank_one_model rewrites each hit's score in place, so the raw list is copied first."""
    key = (_text_hash(text), model, top_m)
    cached = _MEMO.get(key)
    if (cached is not None) :
        return cached
    pp = _pp()
    hits = pp._search_one(model, text, top_m)
    if (not hits) :
        entry = {"raw" : [], "reranked" : []}
    else :
        raw = copy.deepcopy(hits)
        entry = {"raw" : raw, "reranked" : pp.rerank_one_model(hits, text, model)}
    if (len(_MEMO) >= _MEMO_LIMIT) :
        _MEMO.pop(next(iter(_MEMO)))
    _MEMO[key] = entry
    return entry


def _after_fusion(text : str, models : list[str], top_k : int, top_m : int) -> list[dict] :
    pp = _pp()
    raw = {m : per_model_hits(text, m, top_m)["raw"] for m in models}
    raw = {m : hits for m, hits in raw.items() if hits}
    if (not raw) :
        return []

    # 1. fuse the raw lists. The fused list, not top_k, is the candidate pool.
    pool_size = sum(len(hits) for hits in raw.values())
    fused = pp._merge_ensemble(raw, pool_size)

    # 2. every candidate gets its neighbour score under every active model.
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
        rescored[model] = pp.rerank_one_model(pool, text, model)

    # 3. fuse the rescored lists, as the shipped merge does.
    return pp._merge_ensemble(rescored, top_k)


def search(
    text : str,
    models : list[str],
    top_k : int = 100,
    top_m : int = 50,
    rerank_mode : str = "per_model",
) -> list[dict] :
    """Same rows as preprocess.ensemble_search(text, top_k, top_m, use_rerank, models) for
    per_model and off; the after_fusion order for after_fusion."""
    pp = _pp()
    pp._load_indexes()
    pp._load_meta()
    ordered = [m for m in CANONICAL_MODELS if m in models and m in pp.MODEL_NAMES]

    if (rerank_mode == "after_fusion") :
        return _after_fusion(text, ordered, top_k, top_m)
    if (rerank_mode not in ("per_model", "off")) :
        raise ValueError(f"unknown rerank_mode {rerank_mode}")

    field = "reranked" if rerank_mode == "per_model" else "raw"
    per_model : dict[str, list[dict]] = {}
    for model in ordered :
        hits = per_model_hits(text, model, top_m)[field]
        if (hits) :
            per_model[model] = hits
    return pp._merge_ensemble(per_model, top_k)


def memo_size() -> int :
    return len(_MEMO)


def describe() -> dict[str, Any] :
    return {"memo_entries" : len(_MEMO), "canonical_models" : list(CANONICAL_MODELS)}
