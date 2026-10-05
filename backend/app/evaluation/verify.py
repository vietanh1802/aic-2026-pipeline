# backend/app/evaluation/verify.py
"""Check that shared_search reproduces the live ensemble_search on the REAL loaded indexes.

shared_search is only valid if fusing memoised per-model lists gives exactly what ensemble_search
gives. The unit test proves that on fakes; this proves it on the real encoders and FAISS indexes,
for every one of the 7 model subsets with rerank per_model and off. Frame order and every score
(the fused distance and each model's route rank and cosine) must match within 1e-6.

A fourth check covers the re-created after_fusion order: with a single model there is nothing to
fuse, so after_fusion must equal per_model for each of the 3 models. That cannot prove the
multi-model after_fusion variant is right (no reference exists), but it does prove its candidate
pool and second rerank pass are wired to the real encoders and indexes. Plus one line: the evaluation-side
rerank (rerank_variants) with the shipped parameters equals ensemble_search with rerank on. Total: 14 + 3 + 1 = 18 lines.

The suite script runs this before a full run and refuses to continue on a failure.
"""
from __future__ import annotations

import itertools
import json
from typing import Any, Callable

from app.evaluation import shared_search
from app.evaluation.config import CANONICAL_MODELS
from app.evaluation.seed import SEEDS_DIR

TOLERANCE = 1e-6
MODES = (("per_model", True), ("off", False))


def seed_queries(dataset_version : str, n : int) -> list[str] :
    """The first n Vietnamese query texts of a seed file. The text policy does not matter for an
    equivalence check; raw text needs no network and no key."""
    seed = json.loads((SEEDS_DIR / f"{dataset_version}.json").read_text(encoding = "utf-8"))
    return [q["query_vi"] for q in seed["queries"][ : n]]


def subsets() -> list[list[str]] :
    return [list(c) for size in (1, 2, 3) for c in itertools.combinations(CANONICAL_MODELS, size)]


def first_difference(expected : list[dict], actual : list[dict]) -> str | None :
    """Describe the first row where the two rankings differ, or None when they match."""
    if (len(expected) != len(actual)) :
        return f"length {len(expected)} (ensemble_search) vs {len(actual)} (shared_search)"
    for index, (e, a) in enumerate(zip(expected, actual)) :
        if (e["name"] != a["name"]) :
            return f"rank {index + 1}: frame {e['name']} (distance {e['distance']}) vs frame {a['name']} (distance {a['distance']})"
        if (abs(e["distance"] - a["distance"]) > TOLERANCE) :
            return f"rank {index + 1} frame {e['name']}: distance {e['distance']} vs {a['distance']}"
        for model in set(e["routes"]) | set(a["routes"]) :
            er, ar = e["routes"].get(model), a["routes"].get(model)
            if (er is None or ar is None or er["rank"] != ar["rank"] or abs(er["score"] - ar["score"]) > TOLERANCE) :
                return f"rank {index + 1} frame {e['name']}: route {model} {er} vs {ar}"
    return None


def verify_shared_search(
    queries : list[str],
    say : Callable[[str], None] = print,
    top_k : int = 100,
    top_m : int = 50,
) -> dict[str, Any] :
    """Compare shared_search with ensemble_search for every subset and rerank mode over `queries`.
    One line per subset and mode, then one per single model for the after_fusion check. Returns {"ok": bool, "results": [...]}."""
    from app import preprocess

    shared_search.clear_memo()
    results = []
    for subset in subsets() :
        for mode, use_rerank in MODES :
            label = f"{'+'.join(subset)} {mode}"
            problem = None
            for number, text in enumerate(queries, start = 1) :
                expected = preprocess.ensemble_search(text, top_k = top_k, top_m = top_m, use_rerank = use_rerank, models = subset)
                actual = shared_search.search(text, subset, top_k, top_m, mode)
                problem = first_difference(expected, actual)
                if (problem) :
                    problem = f"query {number}: {problem}"
                    break
            say(f"{'FAIL' if problem else 'PASS'} {label} ({len(queries)} queries){': ' + problem if problem else ''}")
            results.append({"subset" : subset, "mode" : mode, "ok" : problem is None, "detail" : problem})

    for model in CANONICAL_MODELS :
        label = f"{model} after_fusion == per_model"
        problem = None
        for number, text in enumerate(queries, start = 1) :
            expected = shared_search.search(text, [model], top_k, top_m, "per_model")
            actual = shared_search.search(text, [model], top_k, top_m, "after_fusion")
            problem = first_difference(expected, actual)
            if (problem) :
                problem = f"query {number}: {problem}"
                break
        say(f"{'FAIL' if problem else 'PASS'} {label} ({len(queries)} queries){': ' + problem if problem else ''}")
        results.append({"subset" : [model], "mode" : "after_fusion==per_model", "ok" : problem is None, "detail" : problem})

    # The evaluation-side rerank (rerank_variants) with the shipped parameters must reproduce the live search,
    # so every other variant differs from production only in the parameter it changes.
    from app.evaluation.config import RerankVariant

    subset = list(CANONICAL_MODELS)
    problem = None
    for number, text in enumerate(queries, start = 1) :
        expected = preprocess.ensemble_search(text, top_k = top_k, top_m = top_m, use_rerank = True, models = subset)
        actual = shared_search.search(text, subset, top_k, top_m, "variant", RerankVariant())
        problem = first_difference(expected, actual)
        if (problem) :
            problem = f"query {number}: {problem}"
            break
    say(f"{'FAIL' if problem else 'PASS'} shipped rerank variant == ensemble_search ({len(queries)} queries){': ' + problem if problem else ''}")
    results.append({"subset" : subset, "mode" : "variant(shipped)", "ok" : problem is None, "detail" : problem})
    return {"ok" : all(r["ok"] for r in results), "queries" : len(queries), "results" : results}
