# backend/app/evaluation/coverage.py
"""What a run was measured on: per-model index coverage and the provenance block stored in runtime_json.

Per-model coverage matters because each encoder searches only its own index. A frame missing from a
model's mapping is never a hit for that model and is skipped as a rerank neighbour (preprocess._fid_of
returns -1), so arms with different coverage see different candidate pools. The numbers are read from
the globals preprocess already loaded; nothing is re-read from disk.

Those globals are private names in preprocess.py. A renamed or missing one for a LOADED model (one in
preprocess.ACTIVE_MODELS, i.e. not excluded by AIC_MODELS) raises an error naming the attribute,
instead of recording zeros that look like an empty index. In a suite run that surfaces as a failed
query (video_coverage) or an "error" in the run's runtime_json (provenance), never as silent zeros.

Acceptance values for the first real run on the full index set (991,469 keyframes, 1,487 videos).
Compare provenance.json -> runtime_first_run.provenance.index_coverage with:
    metadata_frames 991469, videos 1487
    each of beit3, clip, siglip2: ntotal 991469, mapped 991469, in_metadata 991469
    by_prefix frames (covered equal to frames for every model): L 360531, M 336876, N 201221, S 92841
    loaded_models: ["beit3", "clip", "siglip2"]
Anything else (a model at 0, a prefix not fully covered) means the arms were not measured on the same
pool and the single-encoder rows must be read against it.

Provenance records enough to say later exactly what produced a table: full commit, VERSION, config
hash, query-set hash, the digests of every cached text used, index file identities, device and
library versions.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from importlib import metadata
from typing import Any

_MODEL_GLOBALS = {
    "beit3"   : ("_beit3_index", "_beit3_map"),
    "clip"    : ("_clip_index", "_clip_map"),
    "siglip2" : ("_siglip2_index", "_siglip2_map"),
}
_PREFIXES = ("L", "M", "N", "S", "K")

_NAME_SETS : dict[tuple, dict[str, frozenset[str]]] = {}


def _pp() :
    from app import preprocess
    return preprocess


def loaded_models() -> list[str] :
    """Models preprocess searches by default: ACTIVE_MODELS, which AIC_MODELS can narrow."""
    return [m for m in _MODEL_GLOBALS if m in _required(_pp(), "ACTIVE_MODELS")]


def _required(pp, attribute : str) :
    """A preprocess global this module depends on. Raises, naming it, when it is gone (renamed)."""
    if (not hasattr(pp, attribute)) :
        raise AttributeError(
            f"preprocess has no attribute {attribute!r}; coverage.py reads it to describe index coverage "
            f"and is out of date with preprocess.py"
        )
    return getattr(pp, attribute)


def _model_global(pp, model : str, attribute : str) :
    """A per-model index or mapping global. Required for a loaded model; a model that AIC_MODELS
    excluded may legitimately be absent, and then it reads as None (reported as not loaded)."""
    if (model in loaded_models()) :
        return _required(pp, attribute)
    return getattr(pp, attribute, None)


def _mapped_names() -> dict[str, frozenset[str]] :
    """Basenames each model's mapping covers, cached while the loaded mappings do not change."""
    pp = _pp()
    maps = {m : _model_global(pp, m, names[1]) for m, names in _MODEL_GLOBALS.items()}
    signature = tuple((m, id(v), len(v or {})) for m, v in maps.items())
    cached = _NAME_SETS.get(signature)
    if (cached is None) :
        _NAME_SETS.clear()
        cached = {
            m : frozenset(os.path.basename(p) for p in (mapping or {}).values() if p)
            for m, mapping in maps.items()
        }
        _NAME_SETS[signature] = cached
    return cached


def index_coverage() -> dict[str, Any] :
    """Per model: vectors in the index, mapping entries, entries present in the keyframe
    metadata, and for each video prefix the share of metadata frames the model covers."""
    pp = _pp()
    names = _mapped_names()
    meta_names = _required(pp, "_name2meta")
    by_prefix_frames : dict[str, int] = {}
    for name, meta in meta_names.items() :
        prefix = str(meta.get("video") or name)[ : 1]
        by_prefix_frames[prefix] = by_prefix_frames.get(prefix, 0) + 1

    models : dict[str, Any] = {}
    for model, (index_name, _map_name) in _MODEL_GLOBALS.items() :
        index = _model_global(pp, model, index_name)
        covered = names[model]
        per_prefix = {prefix : {"frames" : by_prefix_frames.get(prefix, 0), "covered" : 0} for prefix in by_prefix_frames}
        for name in covered :
            meta = meta_names.get(name)
            if (meta is not None) :
                per_prefix[str(meta.get("video") or name)[ : 1]]["covered"] += 1
        models[model] = {
            "loaded"      : model in loaded_models(),
            "ntotal"      : int(index.ntotal) if index is not None else 0,
            "mapped"      : len(covered),
            "in_metadata" : sum(p["covered"] for p in per_prefix.values()),
            "by_prefix"   : per_prefix,
        }
    return {"metadata_frames" : len(meta_names), "videos" : len(_required(pp, "_video_frames")), "models" : models}


def video_coverage(video_id : str) -> dict[str, float] :
    """Share of one video's keyframes each model covers (0.0 when the video is unknown)."""
    pp = _pp()
    frames = _required(pp, "_video_frames").get(video_id, [])
    if (not frames) :
        return {model : 0.0 for model in _MODEL_GLOBALS}
    names = _mapped_names()
    return {model : round(sum(1 for f in frames if f["name"] in names[model]) / len(frames), 4) for model in _MODEL_GLOBALS}


def _library_versions() -> dict[str, str] :
    versions = {}
    for package in ("torch", "faiss-cpu", "numpy", "transformers", "open_clip_torch") :
        try :
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError :
            versions[package] = "not installed"
    return versions


def _sha(parts : list[str]) -> str :
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def query_set_hash(conn : sqlite3.Connection, run : dict[str, Any]) -> str :
    """Dataset content hash plus the exact queries this run scores (a subset changes it)."""
    dataset = conn.execute("SELECT source_sha256 FROM evaluation_datasets WHERE id = ?", (run["dataset_id"],)).fetchone()
    keys = [r["query_key"] for r in conn.execute(
        "SELECT query_key FROM evaluation_query_results WHERE run_id = ? ORDER BY ordinal", (run["id"],))]
    return _sha([dataset["source_sha256"] if dataset else "", *keys])


def provenance(conn : sqlite3.Connection, run : dict[str, Any], cache_digests : list[str]) -> dict[str, Any] :
    from app.version import COMMIT, VERSION

    configuration = run.get("configuration") or {}
    return {
        "commit_full"       : COMMIT,
        "version"           : VERSION,
        "config_hash"       : configuration.get("config_hash"),
        "query_set_hash"    : query_set_hash(conn, run),
        "cache_key_digest"  : _sha(sorted(cache_digests)),
        "cache_key_count"   : len(cache_digests),
        "loaded_models"     : loaded_models(),
        "index_coverage"    : index_coverage(),
        "libraries"         : _library_versions(),
        "aic_models_env"    : os.environ.get("AIC_MODELS", ""),
    }
