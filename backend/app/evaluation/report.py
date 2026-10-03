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
    "event_accuracy", "event_queries",
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
