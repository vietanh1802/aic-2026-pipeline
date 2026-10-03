# backend/tests/test_evaluation_report.py
"""The report on a hand-made fixture: pooled metrics against a hand computation, flag exclusion,
rank-matrix flips, CSV and LaTeX headers.

Fixture (reference video rank per query; None = not retrieved, "failed" = the query failed):

    benchmark A, round1:  Q1 KIS L 1|2   Q2 KIS L 3|1   Q3 QA L None|5
    benchmark A, round2:  Q4 QA L 7|failed   Q5 KIS N 1|1 (flag vfr_times)   Q6 TRAKE L 12|11
    benchmark B, final:   F1 KIS M 1|4   F2 QA S 2|2

    each cell is "baseline | clip".
"""
from __future__ import annotations

import pytest

from app.evaluation import report

BASE = "C01 baseline"
CLIP = "C03 clip only"

FIXTURE = [
    # (slug, query_key, task, reference video, baseline rank, clip rank, flags)
    ("round1", "Q1", "KIS", "L01_V001", 1, 2, ()),
    ("round1", "Q2", "KIS", "L02_V001", 3, 1, ()),
    ("round1", "Q3", "QA", "L03_V001", None, 5, ()),
    ("round2", "Q4", "QA", "L04_V001", 7, "failed", ()),
    ("round2", "Q5", "KIS", "N05-V001", 1, 1, ("vfr_times",)),
    ("round2", "Q6", "TRAKE", "L06_V001", 12, 11, ()),
    ("final", "F1", "KIS", "M01_V001", 1, 4, ()),
    ("final", "F2", "QA", "S01-V001", 2, 2, ()),
]
DATASET = {"round1" : "round1-v3", "round2" : "round2-v2", "final" : "final-v1"}


def _row(config, slug, key, task, video, rank, flags) :
    failed = rank == "failed"
    rank = None if failed else rank
    return {
        "config" : config, "dataset" : DATASET[slug], "slug" : slug, "benchmark" : report.benchmark_of(slug),
        "query_key" : key, "task_type" : task, "reference_video" : video, "prefix" : video[0], "flags" : list(flags),
        "status" : "failed" if failed else "completed",
        "reference_video_rank" : rank,
        "hit_at_1" : None if failed else rank == 1,
        "hit_at_3" : None if failed else rank is not None and rank <= 3,
        "hit_at_5" : None if failed else rank is not None and rank <= 5,
        "hit_at_10" : None if failed else rank is not None and rank <= 10,
        "reciprocal_rank" : None if failed else (1.0 / rank if rank else 0.0),
        "not_retrieved" : None if failed else rank is None,
        "interval_rank" : None, "interval_hit" : None, "final_score" : None,
    }


@pytest.fixture()
def rows() :
    out = []
    for slug, key, task, video, base, clip, flags in FIXTURE :
        out.append(_row(BASE, slug, key, task, video, base, flags))
        out.append(_row(CLIP, slug, key, task, video, clip, flags))
    return out


def _pick(table, config, benchmark, flags = "all", task = "all", prefix = "all") :
    (match,) = [
        r for r in table
        if (r["config"], r["benchmark"], r["flags"], r["task_type"], r["prefix"]) == (config, benchmark, flags, task, prefix)
    ]
    return match


def test_pooled_metrics_match_a_hand_computation(rows) :
    table = report.long_table(rows)

    # Benchmark A pools round1 and round2: baseline ranks 1, 3, none, 7, 1, 12.
    base = _pick(table, BASE, "A")
    assert (base["n"], base["failed"]) == (6, 0)
    assert base["hit_at_1"] == pytest.approx(2 / 6)
    assert base["r_at_5"] == pytest.approx(3 / 6)
    assert base["r_at_10"] == pytest.approx(4 / 6)
    assert base["mrr"] == pytest.approx((1 + 1 / 3 + 0 + 1 / 7 + 1 + 1 / 12) / 6)
    assert base["median_rank"] == 3          # retrieved ranks 1, 1, 3, 7, 12

    # The failed query stays in the denominator and out of the numerators.
    clip = _pick(table, CLIP, "A")
    assert (clip["n"], clip["failed"]) == (6, 1)
    assert clip["hit_at_1"] == pytest.approx(2 / 6)
    assert clip["r_at_5"] == pytest.approx(4 / 6)
    assert clip["mrr"] == pytest.approx((1 / 2 + 1 + 1 / 5 + 0 + 1 + 1 / 11) / 6)

    # Other slices: a round alone, a task type, a prefix, the final.
    assert _pick(table, BASE, "round2")["n"] == 3
    assert _pick(table, BASE, "A", task = "QA")["n"] == 2
    assert _pick(table, BASE, "A", task = "QA")["r_at_10"] == pytest.approx(1 / 2)
    assert _pick(table, BASE, "A", prefix = "N")["hit_at_1"] == 1.0
    assert _pick(table, BASE, "B")["n"] == 2


def test_flag_exclusion_drops_the_flagged_queries(rows) :
    table = report.long_table(rows)

    # Q5 carries vfr_times; without it A has five queries: ranks 1, 3, none, 7, 12.
    kept = _pick(table, BASE, "A", flags = "exclude_flagged")
    assert kept["n"] == 5
    assert kept["hit_at_1"] == pytest.approx(1 / 5)
    assert kept["r_at_5"] == pytest.approx(2 / 5)
    assert kept["r_at_10"] == pytest.approx(3 / 5)
    assert kept["mrr"] == pytest.approx((1 + 1 / 3 + 0 + 1 / 7 + 1 / 12) / 5)

    # The N slice has only the flagged query, so it disappears instead of reading 0 of 0.
    assert not [r for r in table if r["flags"] == "exclude_flagged" and r["prefix"] == "N" and r["benchmark"] == "A"]
    # Unflagged benchmark B is unchanged.
    assert _pick(table, BASE, "B", flags = "exclude_flagged")["n"] == 2


def test_rank_matrix_flips_against_the_baseline(rows) :
    matrix = report.rank_matrix(rows, BASE, "A")
    by_key = {m["query_key"] : m for m in matrix}

    assert len(matrix) == 6
    assert by_key["Q1"][BASE] == 1 and by_key["Q1"][CLIP] == 2
    assert by_key["Q4"][CLIP] is None                    # a failed query has no rank
    assert by_key["Q5"]["flags"] == "vfr_times"
    assert by_key["Q1"][f"{CLIP} flip@1"] == "lost"      # 1 -> 2
    assert by_key["Q2"][f"{CLIP} flip@1"] == "gained"    # 3 -> 1
    assert by_key["Q3"][f"{CLIP} flip@5"] == "gained"    # none -> 5
    assert by_key["Q1"][f"{CLIP} flip@5"] == ""          # hit at 5 in both
    assert report.flip_counts(matrix, CLIP, 1) == {"gained" : 1, "lost" : 1}
    assert report.flip_counts(matrix, CLIP, 5) == {"gained" : 1, "lost" : 0}

    # The CSV keeps the baseline column first among the configurations and one line per query.
    lines = report.rank_matrix_csv(matrix).splitlines()
    assert lines[0].startswith("dataset,query_key,task_type,reference_video,flags,C01 baseline,C03 clip only")
    assert len(lines) == 7


def test_csv_and_latex_headers_and_bold_best(rows) :
    table = report.long_table(rows)

    assert report.long_csv(table).splitlines()[0] == ",".join(report.LONG_FIELDS)

    latex = report.latex_table(table, "A", "all").splitlines()
    assert r"Configuration & Hit@1 & R@5 & R@10 & MRR \\" in latex
    body = {line.split(" & ")[0] : line for line in latex if line.startswith(("C01", "C03"))}
    # Hit@1 ties at 33.3 and R@10 ties at 66.7, so both are bold; R@5 and MRR are won by clip.
    assert body[BASE] == r"C01 baseline & \textbf{33.3} & 50.0 & \textbf{66.7} & 0.427 \\"
    assert body[CLIP] == r"C03 clip only & \textbf{33.3} & \textbf{66.7} & \textbf{66.7} & \textbf{0.465} \\"
