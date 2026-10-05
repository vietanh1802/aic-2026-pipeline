# backend/app/evaluation/rerank_variants.py
"""Evaluation-side re-implementation of the per-model neighbour rerank (Algorithm 2), with parameters.

preprocess.rerank_one_model is production code and is not edited. This module copies its logic so the
neighbourhood, the aggregation and the use of the frame's own score can be varied for the ablation's
development grid (Benchmark A only, see HANDOVER/rerank_selection_rule.md). With

    RerankVariant(neighbourhood = "shipped", aggregate = "sum", own_weight = None)

it computes exactly what rerank_one_model computes (pinned by tests/test_evaluation_rerank_variants.py and by
verify_shared_search on the real indexes).

Why the variants exist (facts from the corpus check of 2026-10-05, /opt/aic/indexes v002):
  - shipped: stored neighbours (offsets -3..-1, +1..+3 in frame order, self excluded) where neighbors_clip is
    set; for the 263,895 L frames without it, offsets -2..+2 WITH self. Two formulas on one scale.
  - the source method (Tran et al., CVPRW 2025, Sec. 3.3) motivates the neighbourhood as "within a shot" and
    samples 4 keyframes per shot; this corpus samples up to 40 per shot, so +-3 frames often crosses shots.
  - the frame's own cosine is replaced, not added: a frame that matches alone (short shot, a cut next to it)
    loses its own evidence.

neighbourhood
  shipped       preprocess._neighbor_faiss_ids, unchanged
  stored_style  offsets -3..-1 and +1..+3 in frame order for EVERY video, self excluded
  same_shot     stored_style, keeping only frames with the frame's own scene_id
  time_window   every frame of the video with |t - t0| <= window_s seconds (timestamp_ms), self excluded
aggregate       sum (shipped) or mean of the neighbours' cosines
own_weight      None: the score is the aggregate (shipped). lambda: own cosine + lambda * aggregate.
                With no usable neighbour, a mean is undefined: the frame's own cosine stands in for it.
"""
from __future__ import annotations

from typing import Any

_QUERY_VECTORS : dict[tuple[str, str], Any] = {}
_POSITIONS : dict[str, dict[str, int]] = {}


def _pp() :
    from app import preprocess
    return preprocess


def clear_caches() -> None :
    _QUERY_VECTORS.clear()
    _POSITIONS.clear()


def _query_vector(model : str, query : str, encode_fn) :
    key = (model, query)
    if (key not in _QUERY_VECTORS) :
        if (len(_QUERY_VECTORS) >= 4096) :
            _QUERY_VECTORS.pop(next(iter(_QUERY_VECTORS)))
        _QUERY_VECTORS[key] = encode_fn(query).ravel()
    return _QUERY_VECTORS[key]


def _position(frames : list[dict], video : str, name : str) -> int | None :
    table = _POSITIONS.get(video)
    if (table is None) :
        table = {m["name"] : i for i, m in enumerate(frames)}
        _POSITIONS[video] = table
    return table.get(name)


def neighbour_ids(meta : dict, model : str, variant) -> list[int] :
    """FAISS ids (in this model's id space) of the frames whose cosines the variant aggregates."""
    pp = _pp()
    if (variant.neighbourhood == "shipped") :
        return pp._neighbor_faiss_ids(meta, model)
    _, _, _, id_field = pp._model_parts(model)
    video = meta.get("video", "")
    frames = pp._video_frames.get(video, [])
    pos = _position(frames, video, meta["name"]) if frames else None
    if (pos is None) :
        return []
    if (variant.neighbourhood == "time_window") :
        t0 = meta.get("timestamp_ms")
        if (t0 is None) :
            return []
        limit = variant.window_s * 1000.0
        chosen = []
        # frames are in frame order, so walk out from pos in both directions and stop past the window.
        for step in (-1, 1) :
            i = pos + step
            while (0 <= i < len(frames)) :
                t = frames[i].get("timestamp_ms")
                if (t is None or abs(t - t0) > limit) :
                    break
                chosen.append(frames[i])
                i += step
    else :
        chosen = [frames[i] for i in range(max(0, pos - 3), min(len(frames), pos + 4)) if i != pos]
        if (variant.neighbourhood == "same_shot") :
            chosen = [m for m in chosen if m.get("scene_id") == meta.get("scene_id")]
    ids = [pp._fid_of(m, id_field) for m in chosen]
    return [i for i in ids if i >= 0]


def rerank(hits : list[dict], query : str, model : str, variant) -> list[dict] :
    """rerank_one_model with the variant's neighbourhood, aggregation and own-score rule. Same output shape."""
    import numpy as np

    pp = _pp()
    pp._load_meta()
    index, _, encode_fn, _ = pp._model_parts(model)
    if (index is None or not hits or not pp._meta) :
        return hits
    q_emb = _query_vector(model, query, encode_fn)

    def compute_score(nid : int) :
        try :
            vec = index.reconstruct(int(nid)).astype("float32").ravel()
            return float(np.dot(q_emb, vec))
        except Exception :
            return None

    for h in hits :
        meta = pp._name2meta.get(h["name"])
        if (not meta) :
            h["score"], h["n_neighbors"] = 0.0, 0
            continue
        scores = [s for s in (compute_score(n) for n in neighbour_ids(meta, model, variant)) if s is not None]
        own = float(h.get("raw_score", h["score"]))
        if (variant.aggregate == "sum") :
            aggregate = sum(scores)
        else :
            aggregate = sum(scores) / len(scores) if scores else own
        h["score"] = aggregate if variant.own_weight is None else own + variant.own_weight * aggregate
        h["n_neighbors"] = len(scores)

    hits.sort(key = lambda h : -h["score"])
    return hits


def variant_key(variant) -> str :
    """A short stable label for memo keys and logs."""
    own = "none" if variant.own_weight is None else f"{variant.own_weight:g}"
    window = f":{variant.window_s:g}s" if variant.neighbourhood == "time_window" else ""
    return f"{variant.neighbourhood}{window}:{variant.aggregate}:own={own}"
