# backend/app/evaluation/report.py
"""Turns the result rows of a suite into the paper's tables.

Everything below the loader is a pure function of plain row dicts, so it is tested on a hand-made
fixture and does not need a database. Metrics come from scoring._video_metrics, the same function the
Benchmark page uses, so a number here is the number the page shows for the same rows.

Slices
  benchmark   A = rounds 1 to 3 pooled (team self-labels), B = final-v1, plus each round alone
  task type   KIS, QA, TRAKE
  prefix      first letter of the reference video: L, M, N, S
  flags       all queries, or without the queries that carry a label flag (the automatic flags and
              vfr_times; see flags.py)
A failed query stays in the denominator, as in scoring.py, so a run that lost queries reads as worse.
"""
from __future__ import annotations

import csv
import io
import re
import sqlite3
from typing import Any, Iterable

from app.evaluation.repository import get_results, get_run
from app.evaluation.scoring import _interval_metrics, _video_metrics

BENCHMARKS = ("A", "B", "round1", "round2", "round3")
FLAG_MODES = ("all", "exclude_flagged")
TASKS = ("KIS", "QA", "TRAKE")
PREFIXES = ("L", "M", "N", "S")
SLICES = [("all", "all"), *((t, "all") for t in TASKS), *(("all", p) for p in PREFIXES)]

LONG_FIELDS = (
    "config", "benchmark", "flags", "task_type", "prefix", "n", "failed",
    "hit_at_1", "r_at_5", "r_at_10", "mrr", "median_rank", "interval_final_score",
    "event_accuracy", "event_queries", "annotation_errors",
)


def benchmark_of(slug : str) -> str :
    return "B" if slug == "final" else "A"


def load_rows(conn : sqlite3.Connection, run_ids : Iterable[int]) -> list[dict[str, Any]] :
    """One row per (run, query), carrying the configuration name, the dataset and the frozen flags."""
    rows : list[dict[str, Any]] = []
    for run_id in run_ids :
        run = get_run(conn, run_id)
        slug = conn.execute("SELECT slug FROM evaluation_datasets WHERE id = ?", (run["dataset_id"],)).fetchone()["slug"]
        config = (run["configuration"] or {}).get("config") or {}
        name = config.get("name") or (run["configuration"] or {}).get("config_name") or f"run {run_id}"
        for result in get_results(conn, run_id) :
            if (result["status"] not in ("completed", "failed")) :
                continue   # queued or running queries of a suite still in progress are not misses
            rows.append({
                **result,
                "config"    : name,
                "dataset"   : run["dataset_version"],
                "slug"      : slug,
                "benchmark" : benchmark_of(slug),
                "prefix"    : str(result["reference_video"])[ : 1],
                "flags"     : list((result.get("extra") or {}).get("flags") or []),
                # Per-event TRAKE accuracy of this query, None unless a TRAKE-N run could score it.
                "event_accuracy" : (((result.get("extra") or {}).get("trake") or {}).get("events") or {}).get("accuracy"),
                "annotation_errors" : len((result.get("extra") or {}).get("text_signal_errors") or []),
                "text_signal"   : (result.get("extra") or {}).get("text_signal"),
                "text_coverage" : (result.get("extra") or {}).get("text_coverage"),
            })
    return rows


def _in_benchmark(row : dict[str, Any], benchmark : str) -> bool :
    return row["benchmark"] == benchmark if benchmark in ("A", "B") else row["slug"] == benchmark


def metrics(rows : list[dict[str, Any]]) -> dict[str, Any] :
    video = _video_metrics(rows)
    kis_qa = [r for r in rows if r["task_type"] in ("KIS", "QA")]
    scored_events = [r["event_accuracy"] for r in rows if r.get("event_accuracy") is not None]
    return {
        "n"                    : video["total"],
        "failed"               : video["failed"],
        "hit_at_1"             : video["hit_at_1"],
        "r_at_5"               : video["recall_at_5"],
        "r_at_10"              : video["recall_at_10"],
        "mrr"                  : video["mrr"],
        "median_rank"          : video["median_reference_rank"],
        "interval_final_score" : _interval_metrics(kis_qa)["final_score"] if kis_qa else None,
        # TRAKE-N only: mean share of events within the tolerance, over the queries with every event labelled.
        "event_accuracy"       : sum(scored_events) / len(scored_events) if scored_events else None,
        "event_queries"        : len(scored_events) or None,
        # Annotation or coverage failures recorded for these queries (they never cost a ranking).
        "annotation_errors"    : sum(r.get("annotation_errors") or 0 for r in rows),
    }


def configs_in_order(rows : list[dict[str, Any]]) -> list[str] :
    seen : dict[str, None] = {}
    for row in rows :
        seen.setdefault(row["config"], None)
    return list(seen)


def long_table(rows : list[dict[str, Any]], benchmarks : Iterable[str] = BENCHMARKS) -> list[dict[str, Any]] :
    """Every configuration x benchmark x flag mode x slice that has at least one query."""
    table : list[dict[str, Any]] = []
    for config in configs_in_order(rows) :
        mine = [r for r in rows if r["config"] == config]
        for benchmark in benchmarks :
            in_benchmark = [r for r in mine if _in_benchmark(r, benchmark)]
            for flag_mode in FLAG_MODES :
                kept = [r for r in in_benchmark if flag_mode == "all" or not r["flags"]]
                for task, prefix in SLICES :
                    subset = [
                        r for r in kept
                        if (task == "all" or r["task_type"] == task) and (prefix == "all" or r["prefix"] == prefix)
                    ]
                    if (subset) :
                        table.append({"config" : config, "benchmark" : benchmark, "flags" : flag_mode,
                                      "task_type" : task, "prefix" : prefix, **metrics(subset)})
    return table


def _csv(fields : list[str], records : list[dict[str, Any]]) -> str :
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames = fields, lineterminator = "\n", extrasaction = "ignore")
    writer.writeheader()
    for record in records :
        writer.writerow({f : ("" if record.get(f) is None else record[f]) for f in fields})
    return out.getvalue()


def long_csv(table : list[dict[str, Any]]) -> str :
    return _csv(list(LONG_FIELDS), table)


# ─── per-query rank matrix ─────────────────────────────────────────────────

def _hit_at(rank : int | None, k : int) -> bool :
    return rank is not None and rank <= k


def rank_matrix(rows : list[dict[str, Any]], baseline : str, benchmark : str | None = None) -> list[dict[str, Any]] :
    """One row per query, the reference video's rank under each configuration (None = not
    retrieved or failed), and for every other configuration whether it gained or lost the hit at
    k = 1 and k = 5 compared with the baseline."""
    configs = configs_in_order(rows)
    if (baseline not in configs) :
        raise ValueError(f"baseline {baseline!r} is not among {configs}")
    by_query : dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows :
        if (benchmark is not None and not _in_benchmark(row, benchmark)) :
            continue
        key = (row["dataset"], row["query_key"])
        entry = by_query.setdefault(key, {
            "dataset" : row["dataset"], "query_key" : row["query_key"], "task_type" : row["task_type"],
            "reference_video" : row["reference_video"], "flags" : ";".join(row["flags"]), "ranks" : {},
        })
        entry["ranks"][row["config"]] = row["reference_video_rank"] if row["status"] == "completed" else None

    matrix = []
    for entry in by_query.values() :
        base = entry["ranks"].get(baseline)
        record = {k : v for k, v in entry.items() if k != "ranks"}
        for config in configs :
            rank = entry["ranks"].get(config)
            record[config] = rank
            if (config == baseline) :
                continue
            for k in (1, 5) :
                before, after = _hit_at(base, k), _hit_at(rank, k)
                record[f"{config} flip@{k}"] = "gained" if (after and not before) else "lost" if (before and not after) else ""
        matrix.append(record)
    return matrix


def rank_matrix_csv(matrix : list[dict[str, Any]]) -> str :
    fields = list(matrix[0].keys()) if matrix else []
    return _csv(fields, matrix)


def flip_counts(matrix : list[dict[str, Any]], config : str, k : int = 1) -> dict[str, int] :
    column = f"{config} flip@{k}"
    return {kind : sum(1 for r in matrix if r.get(column) == kind) for kind in ("gained", "lost")}


# ─── LaTeX ─────────────────────────────────────────────────────────────────

_LATEX_SPECIAL = {"&" : r"\&", "%" : r"\%", "$" : r"\$", "#" : r"\#", "_" : r"\_", "{" : r"\{", "}" : r"\}",
                  "~" : r"\textasciitilde{}", "^" : r"\textasciicircum{}", "\\" : r"\textbackslash{}"}


def latex_escape(text : str) -> str :
    return re.sub(r"[&%$#_{}~^\\]", lambda m : _LATEX_SPECIAL[m.group(0)], text)


def latex_table(
    table : list[dict[str, Any]],
    benchmark : str = "A",
    flags : str = "all",
    task_type : str = "all",
    prefix : str = "all",
) -> str :
    """Configuration & Hit@1 & R@5 & R@10 & MRR, one row per configuration, best value of each
    column in bold (every tied value). Hit@1, R@5 and R@10 are percentages with one decimal, MRR has
    three."""
    rows = [
        r for r in table
        if (r["benchmark"], r["flags"], r["task_type"], r["prefix"]) == (benchmark, flags, task_type, prefix)
    ]
    columns = (("hit_at_1", 100.0, 1), ("r_at_5", 100.0, 1), ("r_at_10", 100.0, 1), ("mrr", 1.0, 3))
    best = {
        field : max(round(r[field] * scale, digits) for r in rows)
        for field, scale, digits in columns
    } if rows else {}

    lines = [r"\begin{tabular}{lrrrr}", r"\hline", r"Configuration & Hit@1 & R@5 & R@10 & MRR \\", r"\hline"]
    for r in rows :
        cells = []
        for field, scale, digits in columns :
            value = round(r[field] * scale, digits)
            text = f"{value:.{digits}f}"
            cells.append(rf"\textbf{{{text}}}" if value == best[field] else text)
        lines.append(f"{latex_escape(r['config'])} & " + " & ".join(cells) + r" \\")
    lines += [r"\hline", r"\end{tabular}"]
    return "\n".join(lines) + "\n"


# ─── paired bootstrap ──────────────────────────────────────────────────────

BOOTSTRAP_METRICS = {
    "hit_at_1" : lambda r : 1.0 if r and r["status"] == "completed" and r["hit_at_1"] is True else 0.0,
    "r_at_5"   : lambda r : 1.0 if r and r["status"] == "completed" and r["hit_at_5"] is True else 0.0,
    "r_at_10"  : lambda r : 1.0 if r and r["status"] == "completed" and r["hit_at_10"] is True else 0.0,
    "mrr"      : lambda r : float(r["reciprocal_rank"] or 0.0) if r and r["status"] == "completed" else 0.0,
}


def paired_bootstrap(
    rows : list[dict[str, Any]],
    baseline : str,
    benchmark : str = "A",
    n_resamples : int = 2000,
    seed : int = 0,
) -> list[dict[str, Any]] :
    """Difference to the baseline per metric with a 95% percentile interval, resampling queries.

    The same resampled query indices are used for every configuration and every metric, so the
    comparison is paired. A query a configuration did not complete counts as a miss. Fixed seed, so
    the same rows always give the same interval."""
    import numpy as np

    by_config : dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
    for row in rows :
        if (_in_benchmark(row, benchmark)) :
            by_config.setdefault(row["config"], {})[(row["dataset"], row["query_key"])] = row
    keys = sorted(by_config.get(baseline, {}))
    if (not keys) :
        return []

    indices = np.random.default_rng(seed).integers(0, len(keys), size = (n_resamples, len(keys)))
    out = []
    for config, mine in by_config.items() :
        if (config == baseline) :
            continue
        for metric, value in BOOTSTRAP_METRICS.items() :
            base = np.array([value(by_config[baseline][k]) for k in keys])
            other = np.array([value(mine.get(k)) for k in keys])
            boot = (other[indices] - base[indices]).mean(axis = 1)
            low, high = np.percentile(boot, [2.5, 97.5])
            out.append({"config" : config, "benchmark" : benchmark, "metric" : metric, "n" : len(keys),
                        "delta" : float((other - base).mean()), "ci_low" : float(low), "ci_high" : float(high)})
    return out


def bootstrap_csv(records : list[dict[str, Any]]) -> str :
    return _csv(["config", "benchmark", "metric", "n", "delta", "ci_low", "ci_high"], records)


# ─── OCR and ASR annotation measures ───────────────────────────────────────

TEXT_SIGNAL_FIELDS = (
    "config", "benchmark", "kind", "variant", "slice", "n", "n_flagged_ref", "flag_rate_ref", "here_rate",
    "in_interval", "precision", "base_rate", "rescue_potential",
    "strict_flag_rate_ref", "strict_precision", "strict_base_rate",
)


def _has_coverage(row : dict[str, Any], variant : str) -> bool :
    coverage = row.get("text_coverage") or {}
    return any((coverage.get(s) or 0) > 0 for s in (("ocr", "asr") if variant == "both" else (variant,)))


def text_signal_table(rows : list[dict[str, Any]], benchmarks : Iterable[str] = BENCHMARKS) -> list[dict[str, Any]] :
    """Annotation-level measures per configuration that carries them, benchmark, cue kind and variant.

    kind     confirmed (reviewed cues) or legacy_leaky (the seed's old filter_terms, an upper bound)
    variant  ocr, asr or both (annotation only: none of them changes a ranking)
    slice    all             every query of the benchmark, flagged or not
             cue             queries with at least one cue of this kind for the variant's sources
             cue+coverage    cue, and the loaded OCR or ASR artifacts cover the reference video

    flag_rate_ref     share of queries whose reference video is annotated as matched
    here_rate         of those, share whose matched frame is one of the returned frames
    in_interval       of the flagged KIS/QA queries, share with a matched frame inside a valid interval
    precision         flagged reference videos / flagged videos, over the queries that flagged any
    base_rate         mean share of the result list's videos that are flagged
    rescue_potential  share of queries where the reference is flagged but not ranked first: what an
                      injection could fix. It is NOT a ranking effect of anything that shipped.
    strict_*          flag_rate_ref, precision and base_rate again under the strict rule (a video is flagged for
                      a source only when it holds EVERY term of the cue, see text_measures.py). The plain
                      columns are an OR over the terms and are inflated by short common terms.
    """
    table : list[dict[str, Any]] = []
    for config in configs_in_order(rows) :
        mine = [r for r in rows if r["config"] == config and r.get("text_signal") is not None]
        for benchmark in benchmarks :
            scoped = [r for r in mine if _in_benchmark(r, benchmark)]
            for kind in ("confirmed", "legacy_leaky") :
                for variant in ("ocr", "asr", "both") :
                    # No query has a cue of this kind for this variant (no confirmed cues yet): nothing to measure.
                    if (not any((r["text_signal"].get(kind) or {}).get(variant) for r in scoped)) :
                        continue
                    for slice_name in ("all", "cue", "cue+coverage") :
                        picked = []
                        for r in scoped :
                            block = (r["text_signal"].get(kind) or {}).get(variant)
                            if (slice_name == "all") :
                                # A query without a cue still counts, as unflagged.
                                picked.append(block)
                            elif (block is not None and (slice_name == "cue" or _has_coverage(r, variant))) :
                                picked.append(block)
                        if (not picked or (slice_name != "all" and not any(picked))) :
                            continue
                        table.append({"config" : config, "benchmark" : benchmark, "kind" : kind, "variant" : variant,
                                      "slice" : slice_name, **_text_signal_metrics(picked)})
    return table


def _text_signal_metrics(blocks : list[dict[str, Any] | None]) -> dict[str, Any] :
    n = len(blocks)
    flagged = [b for b in blocks if b and b["ref_flagged"]]
    with_flags = [b for b in blocks if b and b["n_flagged"] > 0]
    interval_scored = [b for b in flagged if b["ref_in_interval"] is not None]
    seen = [b for b in blocks if b and b["n_videos"] > 0]
    return {
        "n"                : n,
        "n_flagged_ref"    : len(flagged),
        "flag_rate_ref"    : len(flagged) / n,
        "here_rate"        : sum(1 for b in flagged if b["ref_location"] == "here") / len(flagged) if flagged else None,
        "in_interval"      : sum(1 for b in interval_scored if b["ref_in_interval"]) / len(interval_scored) if interval_scored else None,
        "precision"        : len(flagged) / sum(b["n_flagged"] for b in with_flags) if with_flags else None,
        "base_rate"        : sum(b["n_flagged"] / b["n_videos"] for b in seen) / len(seen) if seen else None,
        "rescue_potential" : sum(1 for b in flagged if b["ref_rank"] is None or b["ref_rank"] > 1) / n,
        **_strict_metrics(blocks),
    }


def _strict_metrics(blocks : list[dict[str, Any] | None]) -> dict[str, Any] :
    """flag rate, precision and base rate of the strict rule; None where the blocks carry no strict part
    (a run from before it existed, or BM25 mode)."""
    n = len(blocks)
    strict = [(b, b["strict"]) for b in blocks if b and b.get("strict")]
    if (not strict) :
        return {"strict_flag_rate_ref" : None, "strict_precision" : None, "strict_base_rate" : None}
    flagged = [s for _b, s in strict if s["ref_flagged"]]
    with_flags = [s for _b, s in strict if s["n_flagged"] > 0]
    seen = [(b, s) for b, s in strict if b["n_videos"] > 0]
    return {
        "strict_flag_rate_ref" : len(flagged) / n,
        "strict_precision"     : len(flagged) / sum(s["n_flagged"] for s in with_flags) if with_flags else None,
        "strict_base_rate"     : sum(s["n_flagged"] / b["n_videos"] for b, s in seen) / len(seen) if seen else None,
    }


def text_signal_csv(table : list[dict[str, Any]]) -> str :
    return _csv(list(TEXT_SIGNAL_FIELDS), table)
