# scripts/tests/test_ablation_analysis_core.py
"""Rank buckets, flips, oracle union and fusion gain, the capped-at-four shot logic, TRAKE stages, the
corpus dump, and that a synthetic or smoke run is stamped. Small fixtures, expected values worked out by hand."""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("numpy")
SCRIPTS = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, str(SCRIPTS))

from ablation_analysis import errors as E  # noqa: E402
from ablation_analysis import metrics as M  # noqa: E402
from ablation_analysis import sampling, tables_more  # noqa: E402
from ablation_analysis.context import Ctx  # noqa: E402
from ablation_analysis.data import ConfigInfo, Result, RunData, detect_mode, load_run_folder, role_of  # noqa: E402
from ablation_analysis.facts import load_facts  # noqa: E402


def result(code, key, rank, bench = "A", task = "KIS", prefix = "L", **extra) -> Result :
    return Result(code = code, config_name = code, run_id = 1, dataset = "ds-a" if bench == "A" else "ds-b", bench = bench, key = key, task = task, ref_video = f"{prefix}01_V001",
                  prefix = prefix, status = "completed", rank = rank, query_vi = "q", query_en = "q", intervals = [], ref_frame_idx = None, interval_hit = None, interval_rank = None,
                  final_score = None, retrieval_ms = None, frames = [], ranked = [], extra = extra)


def run_data(ranks : dict[str, list[int | None]], roles : dict[str, str]) -> RunData :
    data = RunData(folder = Path("."), results = [], configs = {c : ConfigInfo(c, c, {}, roles[c]) for c in ranks}, provenance = {}, suite = {})
    for code, values in ranks.items() :
        for i, rank in enumerate(values) :
            r = result(code, f"q{i}", rank)
            data.results.append(r)
            data.by_code.setdefault(code, {})[r.uid] = r
    return data


def test_rank_bucket_edges_and_hit_definitions() :
    assert [E.rank_bucket(r) for r in (1, 2, 5, 6, 10, 11, 100, None)] == ["top1", "2 to 5", "2 to 5", "6 to 10", "6 to 10", "11 to 100", "11 to 100", "not retrieved"]
    r = result("C01", "q", 5)
    assert (r.hit(1), r.hit(5), r.hit(10), r.rr) == (False, True, True, 0.2)
    assert result("C01", "q", None).rr == 0.0 and result("C01", "q", None).rank_or_miss == 101


def test_paired_flip_counts_and_summary() :
    base = [result("C01", f"q{i}", rank) for i, rank in enumerate([1, 1, 3, None, 12])]
    other = [result("C02", f"q{i}", rank) for i, rank in enumerate([1, 4, 1, 2, 12])]
    c = M.compare(base, other)
    # Hit@1: q2 gained (3 -> 1), q1 lost (1 -> 4); Hit@10: q3 gained (miss -> 2), nothing lost.
    assert (c["hit_at_1"]["gained"], c["hit_at_1"]["lost"]) == (1, 1) and c["hit_at_1"]["p"] == 1.0
    assert (c["r_at_10"]["gained"], c["r_at_10"]["lost"]) == (1, 0)
    s = M.summary(base)
    assert (s["n"], s["hits_1"], s["hits_10"], s["not_retrieved"]) == (5, 2, 3, 1)
    assert s["mrr"] == pytest.approx((1 + 1 + 1 / 3 + 0 + 1 / 12) / 5)
    assert s["median_rank"] == pytest.approx(2.0)          # ranks 1, 1, 3, 12 -> median 2


def test_oracle_union_exclusive_hits_and_fusion_gain_loss() :
    # Six queries, hit at k = 1 means rank 1. Singles: BEiT-3 hits q0 q1, CLIP q1 q2, SigLIP2 q1 q3.
    ranks = {
        "C01" : [1, 1, None, None, 1, None],          # fusion hits q0 q1 q4
        "C02" : [1, 1, 5, 5, None, None],
        "C03" : [5, 1, 1, 5, None, None],
        "C04" : [5, 1, 5, 1, None, None],
    }
    roles = {"C01" : "base", "C02" : "single:beit3", "C03" : "single:clip", "C04" : "single:siglip2"}
    data = run_data(ranks, roles)
    ctx = Ctx(data = data, features = None, labels = None, facts = load_facts(None), out = Path("."))
    first = tables_more.t8_complementarity(ctx)[0]
    row = next(r for r in first.records if r["bench"] == "A" and r["k"] == 1)
    assert (row["hits_beit3"], row["hits_clip"], row["hits_siglip2"]) == (2, 2, 2)
    assert row["union_oracle"] == 4 and row["intersection"] == 1                     # q0 q1 q2 q3 ; q1
    assert (row["exclusive_beit3"], row["exclusive_clip"], row["exclusive_siglip2"]) == (1, 1, 1)
    assert row["fusion_hits"] == 3 and row["fusion_gain"] == 1 and row["fusion_loss"] == 2   # gain q4; loss q2 q3
    assert row["oracle_minus_fusion"] == 1


def test_cross_labels_and_trake_stage() :
    ranks = {"C01" : [1, 20, 1], "C02" : [30, 20, 1], "C03" : [30, 20, 1], "C04" : [30, 20, 1], "C08" : [30, 20, 1]}
    roles = {"C01" : "base", "C02" : "single:beit3", "C03" : "single:clip", "C04" : "single:siglip2", "C08" : "all:off"}
    labels = E.cross_labels(run_data(ranks, roles), "A")
    assert labels[("ds-a", "q0")]["rescued_by_fusion@1"] is True and labels[("ds-a", "q0")]["rerank_gained@1"] is True
    assert labels[("ds-a", "q1")]["hard"] is True
    assert labels[("ds-a", "q2")]["rescued_by_fusion@1"] is False

    def stage(rank, shortlisted, feasible, correct = 0, total = 3) :
        return E.trake_stage(result("T01", "t", rank, task = "TRAKE", trake = {"discovery" : {"in_shortlist" : shortlisted, "feasible_chain" : feasible}, "events" : {"correct" : correct, "total" : total}}))
    assert stage(None, False, False) == "not shortlisted"
    assert stage(None, True, False) == "shortlisted, no feasible chain"
    assert stage(4, True, True) == "chain found, reference video not ranked first"
    assert stage(1, True, True, correct = 2) == "right video, wrong event frame"
    assert stage(1, True, True, correct = 3) == "success"


def test_capped_at_four_logic_and_eq1() :
    assert sampling.capped_positions(3) == {0, 1, 2} and sampling.capped_positions(4) == {0, 1, 2, 3}
    assert sampling.capped_positions(10) == {0, 3, 6, 9}                  # round(j * 9 / 3)
    assert sampling.capped_positions(40) == {0, 13, 26, 39}
    assert [sampling.eq1(t) for t in (0, 1.67, 1.68, 3.67, 3.68, 1000)] == [2, 2, 3, 3, 4, 40]


def test_capped_interval_coverage_on_a_tiny_video() :
    from ablation_analysis.features import Features
    frames = [(f"V-0000-{i * 10}.jpg", 0, i * 10) for i in range(10)]       # one shot, keyframes at 0, 10, ..., 90
    features = Features(folder = Path("."), frames_ref = {"L01_V001" : frames})
    inside_kept = result("C01", "a", 1)
    inside_kept.intervals = [(25, 35)]                                      # keyframe 30 is position 3: kept by the cap
    inside_lost = result("C01", "b", 1)
    inside_lost.intervals = [(45, 55)]                                      # keyframe 50 is position 5: dropped by the cap
    rows = sampling.interval_coverage([inside_kept, inside_lost], features)
    assert [(r["adaptive_has_keyframe"], r["capped_has_keyframe"]) for r in rows] == [(True, True), (True, False)]


def test_run_mode_detection() :
    assert detect_mode({"synthetic" : True}, {}, set())[0] == "SYNTHETIC"
    assert detect_mode({}, {"limit_queries" : 3}, set())[0] == "SMOKE"
    assert detect_mode({}, {"verify" : {"skipped" : True}}, set())[0] == "SMOKE"
    assert detect_mode({}, {}, {"test"})[0] == "SMOKE"
    assert detect_mode({}, {"limit_queries" : None, "verify" : {"ok" : True}}, {"cpu"}) == ("REAL", [])
    assert role_of({"models" : ["beit3", "clip", "siglip2"], "rerank_mode" : "per_model", "text_policy" : "translate_gtx", "task_mode" : "ensemble"}) == "base"
    assert role_of({"models" : ["clip"], "rerank_mode" : "off", "text_policy" : "translate_gtx", "task_mode" : "ensemble"}) == "single:clip:off"


def tiny_run_folder(folder : Path, synthetic : bool) -> None :
    """A minimal ablation.db: only the baseline, two datasets, three queries each."""
    folder.mkdir(parents = True)
    conn = sqlite3.connect(folder / "ablation.db")
    conn.executescript("""
        CREATE TABLE evaluation_datasets (id INTEGER PRIMARY KEY, slug TEXT, version TEXT);
        CREATE TABLE evaluation_queries (id INTEGER PRIMARY KEY, query_key TEXT);
        CREATE TABLE evaluation_references (id INTEGER PRIMARY KEY, reference_set_id INTEGER, query_id INTEGER, confidence TEXT, provenance TEXT, status TEXT, notes TEXT, trake_events_json TEXT);
        CREATE TABLE evaluation_runs (id INTEGER PRIMARY KEY, dataset_id INTEGER, reference_set_id INTEGER, configuration_json TEXT, runtime_json TEXT, status TEXT);
        CREATE TABLE evaluation_query_results (id INTEGER PRIMARY KEY, run_id INTEGER, query_key TEXT, ordinal INTEGER, task_type TEXT, status TEXT, query_vi TEXT, query_en TEXT, reference_video TEXT,
            reference_intervals_json TEXT, reference_frame_idx INTEGER, reference_video_rank INTEGER, interval_hit INTEGER, interval_rank INTEGER, final_score REAL, retrieval_ms REAL,
            frame_results_json TEXT, ranked_videos_json TEXT, extra_json TEXT, error TEXT);
    """)
    config = {"config" : {"name" : "C01 baseline", "models" : ["beit3", "clip", "siglip2"], "rerank_mode" : "per_model", "text_policy" : "translate_gtx", "task_mode" : "ensemble"}, "config_name" : "C01 baseline"}
    for i, (slug, version) in enumerate((("round1", "round1-v3"), ("final", "final-v1")), start = 1) :
        conn.execute("INSERT INTO evaluation_datasets VALUES (?, ?, ?)", (i, slug, version))
        conn.execute("INSERT INTO evaluation_runs VALUES (?, ?, ?, ?, ?, 'completed')", (i, i, i, json.dumps(config), json.dumps({"device" : "cpu"})))
        for j, rank in enumerate((1, 3, None)) :
            conn.execute("INSERT INTO evaluation_queries VALUES (?, ?)", (i * 10 + j, f"{slug}-{j}"))
            conn.execute("INSERT INTO evaluation_references VALUES (?, ?, ?, 'manual_review_interval', 'team', 'ok', '', NULL)", (i * 10 + j, i, i * 10 + j))
            conn.execute("INSERT INTO evaluation_query_results VALUES (?, ?, ?, ?, 'KIS', 'completed', 'vi', 'en', 'L01_V001', '[]', NULL, ?, NULL, NULL, NULL, 5.0, '[]', '[]', '{}', NULL)", (i * 10 + j, i, f"{slug}-{j}", j, rank))
    conn.commit()
    conn.close()
    (folder / "provenance.json").write_text(json.dumps({"synthetic" : synthetic, "commit_full" : "abc"}), encoding = "utf-8")


@pytest.mark.parametrize("synthetic, folder_suffix", [(True, "analysis_SYNTHETIC"), (False, "analysis")])
def test_synthetic_run_is_stamped_and_a_real_one_is_not(tmp_path, synthetic, folder_suffix) :
    pytest.importorskip("matplotlib")
    folder = tmp_path / "run"
    tiny_run_folder(folder, synthetic)
    data = load_run_folder(folder)
    assert data.mode == ("SYNTHETIC" if synthetic else "REAL") and len(data.results) == 6
    process = subprocess.run([sys.executable, str(SCRIPTS / "analyze_ablation.py"), "--run-dir", str(folder), "--skip-figures"], capture_output = True, text = True, encoding = "utf-8")
    assert process.returncode == 0, process.stdout + process.stderr
    out = folder / folder_suffix
    assert out.is_dir()
    main_table = (out / "tables" / "T2_main_ablation.tex").read_text(encoding = "utf-8")
    assert ("SYNTHETIC RUN" in main_table) == synthetic
    assert ((out / "claims_check.md").read_text(encoding = "utf-8").lstrip().startswith("# Claims check")) is True
    assert ("SYNTHETIC RUN" in (out / "claims_check.md").read_text(encoding = "utf-8")) == synthetic
    assert ("SYNTHETIC RUN" in (out / "tables" / "T2_main_ablation.csv").read_text(encoding = "utf-8")) == synthetic
    assert json.loads((out / "analysis_provenance.json").read_text(encoding = "utf-8"))["synthetic"] is synthetic


def test_corpus_dump_shots_and_hyphenated_ids() :
    sys.path.insert(0, str(SCRIPTS))
    import dump_corpus_features as dump

    assert dump.name_parts("N001-V001-0012-345.jpg") == ("N001-V001", 12, 345)
    assert dump.name_parts("L25_V001-0000-3.jpg") == ("L25_V001", 0, 3)
    records = [{"name" : "L25_V001-0000-3.jpg", "video" : "L25_V001", "scene_id" : 0, "frame_idx" : 3, "fps" : 25.0, "timestamp_ms" : 120},
               {"name" : "L25_V001-0000-53.jpg", "video" : "L25_V001", "scene_id" : 0, "frame_idx" : 53, "fps" : 25.0, "timestamp_ms" : 2120},
               {"name" : "L25_V001-0001-103.jpg", "video" : "L25_V001", "scene_id" : 1, "frame_idx" : 103, "fps" : 25.0, "timestamp_ms" : 4120}]
    videos, shots, refs, disagree = dump.build(records, {}, {"L25_V001" : "round1-v3"})
    assert videos[0]["n_keyframes"] == 3 and videos[0]["n_shots"] == 2 and videos[0]["duration_s"] == pytest.approx(103 / 25)
    # Shot 0: keyframes 3 and 53, next shot starts at 103 -> estimated duration (103 - 3) / 25 = 4 s; shot 1 is the last, its own span is 0.
    assert shots[0]["n_keyframes"] == 2 and shots[0]["duration_est_s"] == pytest.approx(4.0) and shots[1]["duration_est_s"] == 0.0
    assert len(refs) == 3 and all(v == 0 for v in disagree.values())
    records[1]["scene_id"] = 5                                             # disagreement with the file name is counted, not hidden
    assert dump.build(records, {}, {})[3]["shot_vs_name"] == 1
