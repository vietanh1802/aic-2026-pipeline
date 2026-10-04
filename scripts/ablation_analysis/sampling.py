# scripts/ablation_analysis/sampling.py
"""Claim C1 (duration-adaptive keyframe sampling) from corpus statistics, plus a capped-at-four simulation.

Eq. 1:   n(T) = min(40, 2 + ceil(max(0, T - 1.67) / 2))   keyframes for a shot of T seconds.

There is no ablation arm for sampling. What can be done without a GPU:
  budget_check   how well the stored keyframes per shot follow Eq. 1. T is not stored, so it is estimated
                 as (first keyframe of the next shot - first keyframe of this shot) / fps; the last shot of
                 a video uses its own span, a lower bound. Read the match rate with that in mind.
  interval_coverage   per KIS and QA query, does the reference video still have a keyframe inside the valid
                 interval if every shot is capped at four evenly spaced keyframes. Exact: the reference
                 videos' keyframes are in frames_ref.csv.
  capped_retrieval    an APPROXIMATION by post-filtering the stored top-100 of the baseline: frames the
                 capped index would not contain are dropped and the video ranks recomputed. It cannot add
                 frames that would enter the list and ignores changed neighbour scores. For frames outside
                 the reference videos the position of a frame inside its shot is estimated from the shot's
                 first and last keyframe and its keyframe count (evenly spaced sampling makes this nearly
                 exact); capped_retrieval reports how often the estimate equals the true position on the
                 reference videos, where both are known.
"""
from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np

from ablation_analysis.data import Result
from ablation_analysis.features import Features

CAP = 4


def eq1(seconds : float) -> int :
    return min(40, 2 + math.ceil(max(0.0, seconds - 1.67) / 2))


def capped_positions(n : int, cap : int = CAP) -> set[int] :
    """Indexes (0-based) of the keyframes kept when a shot with n keyframes is capped: evenly spaced."""
    if (n <= cap) :
        return set(range(n))
    return {int(round(j * (n - 1) / (cap - 1))) for j in range(cap)}


def budget_check(features : Features) -> dict[str, Any] :
    """Observed keyframes per shot against Eq. 1, overall and per prefix and duration bin."""
    by_video = features.shots_by_video()
    rows = []
    for video, shots in by_video.items() :
        for index, shot in enumerate(shots) :
            last = index == len(shots) - 1
            rows.append((video[ : 1], shot["n_keyframes"], shot["duration_est_s"], eq1(shot["duration_est_s"]), last))
    if (not rows) :
        return {}
    observed = np.array([r[1] for r in rows], dtype = float)
    predicted = np.array([r[3] for r in rows], dtype = float)
    inner = np.array([not r[4] for r in rows])
    durations = np.array([r[2] for r in rows], dtype = float)

    def block(mask : np.ndarray) -> dict[str, Any] :
        o, p = observed[mask], predicted[mask]
        if (o.size == 0) :
            return {"shots" : 0}
        return {
            "shots" : int(o.size), "mean" : float(o.mean()), "median" : float(np.median(o)),
            "p5" : float(np.percentile(o, 5)), "p25" : float(np.percentile(o, 25)), "p75" : float(np.percentile(o, 75)),
            "p95" : float(np.percentile(o, 95)), "max" : float(o.max()), "capped_share" : float((o >= 40).mean()),
            "match_share" : float((o == p).mean()), "within_one_share" : float((np.abs(o - p) <= 1).mean()),
            "mean_signed_deviation" : float((o - p).mean()),
        }

    prefixes = np.array([r[0] for r in rows])
    out = {"all" : block(np.ones(len(rows), dtype = bool)), "excluding_last_shot_of_each_video" : block(inner)}
    for prefix in sorted(set(prefixes)) :
        out[prefix] = block(prefixes == prefix)
    edges = [0, 2, 4, 8, 16, 32, 64, float("inf")]
    bins = []
    for low, high in zip(edges[ : -1], edges[1 : ]) :
        mask = inner & (durations >= low) & (durations < high)
        if (mask.any()) :
            bins.append({"from_s" : low, "to_s" : high, "shots" : int(mask.sum()), "observed_mean" : float(observed[mask].mean()), "eq1_mean" : float(predicted[mask].mean())})
    out["duration_bins"] = bins
    # Rank correlation between the estimated duration and the keyframe count: longer shots get more keyframes.
    from ablation_analysis import stats
    out["spearman_duration_keyframes"] = stats.spearman(durations[inner], observed[inner]) if inner.sum() > 2 else float("nan")
    return out


def _in_shot_positions(frames : Sequence[tuple[str, int, int]]) -> dict[str, tuple[int, int]] :
    """{frame name: (index inside its shot, keyframes in the shot)} for one video's exact keyframes."""
    by_shot : dict[int, list[tuple[str, int]]] = {}
    for name, shot, idx in frames :
        by_shot.setdefault(shot, []).append((name, idx))
    positions = {}
    for members in by_shot.values() :
        members.sort(key = lambda m : m[1])
        for i, (name, _idx) in enumerate(members) :
            positions[name] = (i, len(members))
    return positions


def interval_coverage(results : Sequence[Result], features : Features) -> list[dict[str, Any]] :
    """KIS and QA queries: does a keyframe lie inside the valid interval, adaptive versus capped at four."""
    rows = []
    for r in results :
        frames = features.frames_ref.get(r.ref_video)
        if (r.task == "TRAKE" or not r.intervals or not frames) :
            continue
        positions = _in_shot_positions(frames)
        adaptive = [name for name, _shot, idx in frames if any(s <= idx <= e for s, e in r.intervals)]
        capped = [name for name in adaptive if positions[name][0] in capped_positions(positions[name][1])]
        rows.append({"dataset" : r.dataset, "query_key" : r.key, "bench" : r.bench, "prefix" : r.prefix, "adaptive_keyframes" : len(adaptive),
                     "capped_keyframes" : len(capped), "adaptive_has_keyframe" : bool(adaptive), "capped_has_keyframe" : bool(capped)})
    return rows


def _parse_name(name : str) -> tuple[str, int, int] | None :
    parts = name.rsplit(".", 1)[0].rsplit("-", 2)
    return (parts[0], int(parts[1]), int(parts[2])) if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit() else None


def capped_retrieval(base_results : Sequence[Result], features : Features) -> dict[str, Any] :
    """Post-filter the stored top-100 of the baseline to the frames a capped index would hold (approximation)."""
    shot_info = {(s["video"], int(s["shot"])) : (s["first_frame"], s["last_frame"], s["n_keyframes"]) for s in features.shots}

    def estimated_position(video : str, shot : int, idx : int) -> tuple[int, int] | None :
        info = shot_info.get((video, shot))
        if (info is None) :
            return None
        first, last, n = info
        return (int(round((idx - first) / (last - first) * (n - 1))) if last > first else 0), n

    # How good is the estimate? Compare with the exact positions on the reference videos.
    agree = total = 0
    for video, frames in features.frames_ref.items() :
        exact = _in_shot_positions(frames)
        for name, shot, idx in frames :
            estimate = estimated_position(video, shot, idx)
            if (estimate is not None) :
                total += 1
                agree += estimate[0] == exact[name][0]

    kept_ranks, dropped_frames, total_frames, unknown = [], 0, 0, 0
    for r in base_results :
        kept = []
        for frame in r.frames :
            parsed = _parse_name(frame.get("name", ""))
            total_frames += 1
            position = estimated_position(*parsed) if parsed else None
            if (position is None) :
                unknown += 1
                kept.append(frame)           # no shot information: keep, so nothing is dropped by guesswork
            elif (position[0] in capped_positions(position[1])) :
                kept.append(frame)
            else :
                dropped_frames += 1
        order, rank = [], None
        for frame in kept :
            if (frame["video"] not in order) :
                order.append(frame["video"])
        if (r.ref_video in order) :
            rank = order.index(r.ref_video) + 1
        kept_ranks.append((r, rank))

    n = len(kept_ranks)
    ks = {k : sum(1 for _r, rank in kept_ranks if rank is not None and rank <= k) / n for k in (1, 5, 10)} if n else {}
    mrr = sum(1 / rank for _r, rank in kept_ranks if rank) / n if n else float("nan")
    original = {k : sum(1 for r, _rank in kept_ranks if r.hit(k)) / n for k in (1, 5, 10)} if n else {}
    return {
        "n" : n, "cap" : CAP, "frames_dropped_share" : dropped_frames / total_frames if total_frames else float("nan"),
        "frames_without_shot_info" : unknown, "position_estimate_agreement" : agree / total if total else float("nan"),
        "capped" : {"hit_at_1" : ks.get(1), "r_at_5" : ks.get(5), "r_at_10" : ks.get(10), "mrr" : mrr},
        "adaptive" : {"hit_at_1" : original.get(1), "r_at_5" : original.get(5), "r_at_10" : original.get(10), "mrr" : sum(r.rr for r, _x in kept_ranks) / n if n else float("nan")},
    }


def total_keyframes(features : Features) -> dict[str, int] :
    """Keyframes in the index as sampled, and if every shot were capped at four (a size comparison, nothing more)."""
    adaptive = sum(s["n_keyframes"] for s in features.shots)
    return {"adaptive" : adaptive, "capped" : sum(min(s["n_keyframes"], CAP) for s in features.shots)}
