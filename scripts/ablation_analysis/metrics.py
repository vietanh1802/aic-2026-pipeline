# scripts/ablation_analysis/metrics.py
"""Metrics, intervals and the paired comparisons against the baseline.

Definitions (the same as backend/app/evaluation/scoring.py, video level):
  Hit@1     the reference video is first in the ranked video list
  R@k       the reference video is within the first k videos (k = 3, 5, 10, 20, 50, 100)
  MRR       mean of 1 / rank of the reference video, 0 when it is not returned
  median    median rank over the queries where the reference video IS returned
  A failed query stays in the denominator as a miss. Ranks come from the stored top-100 fused frames, so
  a reference video that does not appear among those 100 frames counts as not retrieved.

Comparisons with the baseline are paired on queries. For each benchmark the family of tests is every
(configuration, metric in Hit@1 / R@5 / R@10) pair against the baseline over the retrieval configurations;
Holm adjusts over that whole family. MRR gets a paired bootstrap interval and no p-value.
"""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from ablation_analysis import stats
from ablation_analysis.data import HIT_KS, Result, RunData

HIT_METRICS = (("hit_at_1", 1), ("r_at_5", 5), ("r_at_10", 10))


def summary(results : Sequence[Result], with_ci : bool = True) -> dict[str, Any] :
    n = len(results)
    out : dict[str, Any] = {"n" : n, "failed" : sum(1 for r in results if r.status == "failed")}
    for k in HIT_KS :
        count = sum(1 for r in results if r.hit(k))
        out[f"hits_{k}"] = count
        out[f"r_at_{k}"] = count / n if n else float("nan")
        out[f"r_at_{k}_ci"] = stats.wilson(count, n) if with_ci else (float("nan"), float("nan"))
    out["hit_at_1"], out["hit_at_1_ci"] = out["r_at_1"], out["r_at_1_ci"]
    rr = np.array([r.rr for r in results], dtype = float)
    out["mrr"] = float(rr.mean()) if n else float("nan")
    out["mrr_ci"] = stats.bootstrap_ci(rr) if (with_ci and n) else (float("nan"), float("nan"))
    ranks = np.array([r.rank for r in results if r.rank is not None], dtype = float)
    out["median_rank"] = float(np.median(ranks)) if ranks.size else float("nan")
    out["median_rank_ci"] = stats.bootstrap_ci(ranks, np.median) if (with_ci and ranks.size) else (float("nan"), float("nan"))
    out["not_retrieved"] = sum(1 for r in results if r.rank is None)
    out["not_retrieved_rate"] = out["not_retrieved"] / n if n else float("nan")
    return out


def aligned(a : Sequence[Result], b : Sequence[Result]) -> list[tuple[Result, Result]] :
    """Pairs of the same query in two result lists, in the order of the first."""
    other = {r.uid : r for r in b}
    return [(r, other[r.uid]) for r in a if r.uid in other]


def compare(base : Sequence[Result], other : Sequence[Result]) -> dict[str, Any] :
    """Paired comparison of `other` against `base` on the queries both have."""
    pairs = aligned(base, other)
    out : dict[str, Any] = {"n" : len(pairs)}
    for metric, k in HIT_METRICS :
        gained = sum(1 for b, o in pairs if o.hit(k) and not b.hit(k))
        lost = sum(1 for b, o in pairs if b.hit(k) and not o.hit(k))
        out[metric] = {"gained" : gained, "lost" : lost, "delta" : (gained - lost) / len(pairs) if pairs else float("nan"),
                       "p" : stats.mcnemar_exact(gained, lost)}
    if (pairs) :
        delta, low, high = stats.paired_bootstrap_diff([o.rr for _b, o in pairs], [b.rr for b, _o in pairs])
    else :
        delta = low = high = float("nan")
    out["mrr"] = {"delta" : delta, "ci" : (low, high)}
    return out


def family(data : RunData, bench : str, baseline : str, codes : Sequence[str], clean : bool = False) -> dict[str, dict[str, Any]] :
    """compare() for every code against the baseline, with Holm-adjusted p over the whole family."""
    base = data.results_of(baseline, bench, clean = clean)
    table = {code : compare(base, data.results_of(code, bench, clean = clean)) for code in codes if code != baseline and data.by_code.get(code)}
    keys = [(code, metric) for code in table for metric, _k in HIT_METRICS]
    adjusted = stats.holm([table[c][m]["p"] for c, m in keys])
    for (code, metric), p_adj in zip(keys, adjusted) :
        table[code][metric]["p_holm"] = p_adj
    return table


def hit_matrix(results : Sequence[Result], k : int) -> np.ndarray :
    return np.array([1 if r.hit(k) else 0 for r in results], dtype = int)


def power_note(data : RunData) -> str :
    """The sentence every table with intervals carries: how wide a 95% interval is at these n."""
    parts = []
    for bench in ("A", "B") :
        base = data.code_for("base")
        n = len(data.results_of(base, bench)) if base else 0
        if (n) :
            parts.append(f"about {100 * stats.half_width_at_half(n):.0f} points at n = {n} (benchmark {bench})")
    if (not parts) :
        return ""
    return ("A 95% Wilson interval on a proportion near 0.5 is " + " and ".join(parts) +
            " wide on each side, so unpaired differences smaller than that are not evidence.")
