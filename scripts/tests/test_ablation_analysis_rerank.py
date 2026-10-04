# scripts/tests/test_ablation_analysis_rerank.py
"""Stored neighbour links per video (corpus dump) and T4b, rerank on against off split by whether the reference
video has stored links. Small fixtures with expected values worked out by hand."""
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("numpy")
SCRIPTS = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, str(SCRIPTS))

import dump_corpus_features as dump  # noqa: E402
from ablation_analysis import tables_rerank  # noqa: E402
from ablation_analysis.context import Ctx  # noqa: E402
from ablation_analysis.data import ConfigInfo, RunData  # noqa: E402
from ablation_analysis.features import Features  # noqa: E402
from tests.test_ablation_analysis_core import result  # noqa: E402


def record(video, shot, frame, links) :
    return {"name" : f"{video}-{shot:04d}-{frame}.jpg", "video" : video, "scene_id" : shot, "frame_idx" : frame, "fps" : 25.0, "timestamp_ms" : frame * 40,
            "neighbors_clip" : [1, 2, 3, 4, 5, 6] if links else []}


def test_dump_counts_stored_links_per_video_and_in_the_totals() :
    records = [record("L25_V001", 0, f, True) for f in (3, 53, 103)] + [record("L21_V001", 0, f, False) for f in (3, 53)] + \
              [record("L30_V001", 0, 3, True), record("L30_V001", 0, 53, False)]
    videos, shots, _refs, _disagree = dump.build(records, {}, {})
    by_video = {v["video"] : v for v in videos}
    assert (by_video["L25_V001"]["n_with_links"], by_video["L25_V001"]["share_with_links"]) == (3, 1.0)
    assert (by_video["L21_V001"]["n_with_links"], by_video["L21_V001"]["share_with_links"]) == (0, 0.0)
    assert by_video["L30_V001"]["share_with_links"] == 0.5                              # a mixed video is reported, not rounded away
    total = dump.totals(videos, shots)["L"]
    assert (total["keyframes_with_links"], total["videos_all_links"], total["videos_no_links"], total["videos_mixed_links"]) == (4, 1, 1, 1)


def features() -> Features :
    return Features(folder = Path("."), videos = {"L01_V001" : {"video" : "L01_V001", "share_with_links" : 1.0}, "L02_V001" : {"video" : "L02_V001", "share_with_links" : 0.0}})


def data_with_pairs() -> RunData :
    """Four L queries: q0 and q1 have a reference video with links, q2 and q3 without. Rank per arm, on then off."""
    ranks = {"ON" : [1, 1, 2, 1], "OFF" : [1, 3, 1, 5]}
    roles = {"ON" : "base", "OFF" : "all:off"}
    data = RunData(folder = Path("."), results = [], configs = {c : ConfigInfo(c, c, {}, roles[c]) for c in ranks}, provenance = {}, suite = {})
    for code, values in ranks.items() :
        for i, rank in enumerate(values) :
            r = result(code, f"q{i}", rank, task = "KIS")
            r.ref_video = "L01_V001" if i < 2 else "L02_V001"
            r.frames = [{"video" : "L01_V001", "name" : "a"}, {"video" : "L02_V001", "name" : "b"}, {"video" : "L02_V001", "name" : "c"}]
            r.final_score = 0.5 if code == "ON" else 0.25
            data.results.append(r)
            data.by_code.setdefault(code, {})[r.uid] = r
    return data


def test_t4b_splits_by_link_status_and_counts_gained_and_lost() :
    ctx = Ctx(data = data_with_pairs(), features = features(), labels = None, facts = {}, out = Path("."))
    (table,) = tables_rerank.t4b_rerank_by_links(ctx)
    rows = {(r[1], r[2]) : r for r in table.rows if r[0] == "all three encoders"}
    all_l, linked, fallback = rows[("A", "all L")], rows[("A", "stored links")], rows[("A", "fallback (no links)")]
    assert (all_l[3], linked[3], fallback[3]) == ("4", "2", "2")
    # Hit@1 on vs off. Stored links: on 1,1 vs off 1,3 -> 100.0 vs 50.0, +1/-0. Fallback: on 2,1 vs off 1,5 -> 50.0 vs 50.0, +1/-1.
    assert (linked[4], linked[5], linked[6]) == ("100.0", "50.0", "+1/-0")
    assert (fallback[4], fallback[5], fallback[6]) == ("50.0", "50.0", "+1/-1")
    assert (all_l[4], all_l[5], all_l[6]) == ("75.0", "50.0", "+2/-1")
    assert linked[13] == "0.500" and linked[14] == "0.250"                                # interval score on and off
    assert linked[15] == "2.0"                                                             # two distinct videos in the stored frames
    assert linked[17] == "33.3"                                                            # one of the three frames is from a linked video
    assert "2 with stored links, 2 without" in table.notes[0]


def test_t4b_needs_the_link_column_and_says_so() :
    ctx = Ctx(data = data_with_pairs(), features = Features(folder = Path("."), videos = {"L01_V001" : {"video" : "L01_V001"}}), labels = None, facts = {}, out = Path("."))
    assert tables_rerank.t4b_rerank_by_links(ctx) == []
    assert "share_with_links" in ctx.skipped[0] and "dump_corpus_features" in ctx.skipped[0]
    ctx = Ctx(data = data_with_pairs(), features = None, labels = None, facts = {}, out = Path("."))
    assert tables_rerank.t4b_rerank_by_links(ctx) == [] and "--features" in ctx.skipped[0]
