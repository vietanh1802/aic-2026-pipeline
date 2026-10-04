# scripts/ablation_analysis/stats.py
"""Statistics used by every table: intervals, paired tests, multiplicity, rank correlation.

Everything is deterministic: bootstrap functions take a seed (default SEED) and draw one index matrix per
call, so a paired comparison resamples the same queries for both sides.

Choices that matter for reading the output
  proportions   Wilson 95% score interval (Hit@k, R@k, rates): well behaved at 0 and 1 and for n of 28.
  MRR, median   percentile bootstrap over queries, 2000 resamples.
  paired tests  exact two-sided McNemar on the discordant pairs (gained, lost) for a binary hit, paired
                bootstrap of the difference for MRR.
  multiplicity  Holm step-down adjustment, applied by the caller over the whole family it states.
  correlation   Spearman (average ranks for ties) and Kendall tau-b, with a bootstrap interval over queries.
"""
from __future__ import annotations

import math
from typing import Callable, Sequence

import numpy as np

SEED = 20261004
N_BOOT = 2000
Z95 = 1.959963984540054


def wilson(k : int, n : int, z : float = Z95) -> tuple[float, float] :
    """Wilson score interval for k successes in n trials. (nan, nan) when n is 0."""
    if (n <= 0) :
        return float("nan"), float("nan")
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    # The score interval is exactly 0 at k = 0 and exactly 1 at k = n; floating point leaves 1e-17 otherwise.
    return (0.0 if k == 0 else max(0.0, centre - half)), (1.0 if k == n else min(1.0, centre + half))


def half_width_at_half(n : int) -> float :
    """Half-width of the Wilson interval at p = 0.5, the widest case: what '95% interval' means for this n."""
    low, high = wilson(n // 2, n)
    return (high - low) / 2


def mcnemar_exact(gained : int, lost : int) -> float :
    """Exact two-sided McNemar p from the discordant counts: twice the binomial(n, 0.5) tail at min(b, c),
    capped at 1. Only discordant pairs carry information, so equal counts give p = 1 and no pairs give 1."""
    n = gained + lost
    if (n == 0) :
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(gained, lost) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def holm(pvalues : Sequence[float]) -> list[float] :
    """Holm step-down adjusted p-values, in the input order. Adjusted values are monotone and capped at 1."""
    m = len(pvalues)
    order = sorted(range(m), key = lambda i : pvalues[i])
    adjusted = [0.0] * m
    running = 0.0
    for position, index in enumerate(order) :
        running = max(running, min(1.0, (m - position) * pvalues[index]))
        adjusted[index] = running
    return adjusted


def resample_indices(n : int, n_boot : int = N_BOOT, seed : int = SEED) -> np.ndarray :
    return np.random.default_rng(seed).integers(0, n, size = (n_boot, n))


def bootstrap_ci(values : Sequence[float], stat : Callable[..., np.ndarray] = np.mean, n_boot : int = N_BOOT, seed : int = SEED) -> tuple[float, float] :
    """Percentile 95% interval of stat(values) over resampled queries. (nan, nan) for no values.
    stat must accept axis, like np.mean and np.median: it is applied to all resamples at once."""
    array = np.asarray(values, dtype = float)
    if (array.size == 0) :
        return float("nan"), float("nan")
    draws = array[resample_indices(array.size, n_boot, seed)]
    low, high = np.nanpercentile(stat(draws, axis = 1), [2.5, 97.5])
    return float(low), float(high)


def paired_bootstrap_diff(a : Sequence[float], b : Sequence[float], n_boot : int = N_BOOT, seed : int = SEED) -> tuple[float, float, float] :
    """(mean(a) - mean(b), low, high) with the same resampled queries on both sides."""
    x, y = np.asarray(a, dtype = float), np.asarray(b, dtype = float)
    if (x.size != y.size) :
        raise ValueError("paired samples must have the same length")
    if (x.size == 0) :
        return float("nan"), float("nan"), float("nan")
    idx = resample_indices(x.size, n_boot, seed)
    diffs = (x[idx] - y[idx]).mean(axis = 1)
    low, high = np.percentile(diffs, [2.5, 97.5])
    return float((x - y).mean()), float(low), float(high)


def rank_average(values : Sequence[float]) -> np.ndarray :
    """1-based ranks, ties get the mean of the ranks they span."""
    array = np.asarray(values, dtype = float)
    _unique, inverse, counts = np.unique(array, return_inverse = True, return_counts = True)
    last = np.cumsum(counts)                       # rank of the last member of each tie group
    return (last - (counts - 1) / 2.0)[inverse.ravel()]


def spearman(x : Sequence[float], y : Sequence[float]) -> float :
    """Spearman rho: Pearson correlation of the average ranks. nan when either side is constant or n < 2."""
    a, b = np.asarray(x, dtype = float), np.asarray(y, dtype = float)
    if (a.size < 2 or a.size != b.size) :
        return float("nan")
    ra, rb = rank_average(a) - (a.size + 1) / 2, rank_average(b) - (a.size + 1) / 2   # ranks have mean (n + 1) / 2
    denom = math.sqrt(float(ra @ ra) * float(rb @ rb))
    return float(ra @ rb) / denom if denom > 0 else float("nan")


def kendall_tau(x : Sequence[float], y : Sequence[float]) -> float :
    """Kendall tau-b (ties corrected). nan when either side is constant or n < 2."""
    a, b = np.asarray(x, dtype = float), np.asarray(y, dtype = float)
    n = a.size
    if (n < 2 or n != b.size) :
        return float("nan")
    da, db = np.sign(a[:, None] - a[None, :]), np.sign(b[:, None] - b[None, :])
    upper = np.triu_indices(n, k = 1)
    concordant = float((da[upper] * db[upper]).sum())
    ties_a, ties_b = float((da[upper] == 0).sum()), float((db[upper] == 0).sum())
    pairs = n * (n - 1) / 2
    denom = math.sqrt((pairs - ties_a) * (pairs - ties_b))
    return concordant / denom if denom > 0 else float("nan")


def correlation_ci(x : Sequence[float], y : Sequence[float], fn : Callable[[Sequence[float], Sequence[float]], float] = spearman, n_boot : int = N_BOOT, seed : int = SEED) -> tuple[float, float, float] :
    """(statistic, low, high), bootstrapping pairs of queries."""
    a, b = np.asarray(x, dtype = float), np.asarray(y, dtype = float)
    if (a.size < 3) :
        return fn(a, b), float("nan"), float("nan")
    idx = resample_indices(a.size, n_boot, seed)
    draws = np.array([fn(a[i], b[i]) for i in idx])
    low, high = np.nanpercentile(draws, [2.5, 97.5]) if np.isfinite(draws).any() else (float("nan"), float("nan"))
    return fn(a, b), float(low), float(high)
