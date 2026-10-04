# scripts/ablation_analysis/tables_rerank.py
"""T4b: does the neighbour rerank behave differently for videos that have stored neighbour links?

What the shipped rerank does (preprocess.rerank_one_model and _neighbor_faiss_ids, read only):
  * the score of a candidate frame is the SUM of dot(query, vector) over its neighbours. Its own cosine is
    replaced, and the sum is not divided by the number of neighbours;
  * with stored links (keyframe_metadata "neighbors_clip") the neighbours are the stored ones: 6 frames at
    offsets -3..-1 and +1..+3 in the video's frame order, SELF EXCLUDED (3 to 5 at the ends of a video);
  * without them (an empty list) the fallback is the 2 keyframes either side, SELF INCLUDED: 5 frames, fewer at
    the ends. The frame's own, query-matched vector is then one of the summands;
  * link status is a property of the VIDEO, not of the frame: on the local Batch 1 metadata 251 of the 873 L
    videos have links on every keyframe and 622 on none (no mixed video); M, N and S are said to have them
    (not measured here, see docs/rerank-diagnosis.md).
So two different neighbourhood definitions, with different summand counts, are applied inside one ranking, and the
per-model fusion divides each model's list by its own maximum.

This table reads the stored results only (no rerun): for the L reference videos it compares each rerank-on arm
with its rerank-off arm separately for reference videos with stored links and without. It can say whether the
change from off to on differs between the two groups. It cannot say why: link status follows the video series
(the same batch, content and encoder behaviour), so the groups differ in more than the neighbourhood definition,
and no arm applies the same neighbourhood to both. A causal reading needs a rerun with one definition for all.
Needs the features folder written by scripts/dump_corpus_features.py (column share_with_links).
"""
from __future__ import annotations

from typing import Any

from ablation_analysis import metrics as M
from ablation_analysis.context import Ctx
from ablation_analysis.data import Result
from ablation_analysis.tablefmt import Table, fmt_p, num, pct

SETTINGS = (("all three encoders", "base", "all:off"), ("beit3 alone", "single:beit3", "single:beit3:off"),
            ("clip alone", "single:clip", "single:clip:off"), ("siglip2 alone", "single:siglip2", "single:siglip2:off"))


def _has_links(ctx : Ctx, video : str) -> bool | None :
    """True when most keyframes of the video carry stored links (in the real metadata a video has all or none)."""
    row = ctx.features.videos.get(video) if ctx.features else None
    if (row is None or row.get("share_with_links") in (None, "")) :
        return None
    return float(row["share_with_links"]) >= 0.5


def _mean(values : list[float]) -> float | None :
    return sum(values) / len(values) if values else None


def _interval_score(results : list[Result]) -> float | None :
    return _mean([r.final_score for r in results if r.task in ("KIS", "QA") and r.final_score is not None])


def _distinct_videos(results : list[Result]) -> float | None :
    return _mean([len({f["video"] for f in r.frames}) for r in results if r.frames])


def _linked_frame_share(ctx : Ctx, results : list[Result]) -> float | None :
    """Mean share of the returned frames that come from a video with stored links (frames of unknown videos left out)."""
    shares = []
    for r in results :
        known = [_has_links(ctx, f["video"]) for f in r.frames]
        known = [k for k in known if k is not None]
        if (known) :
            shares.append(sum(known) / len(known))
    return _mean(shares)


def t4b_rerank_by_links(ctx : Ctx) -> list[Table] :
    if (ctx.features is None) :
        ctx.skip("T4b rerank by stored links", "no --features folder (run scripts/dump_corpus_features.py)")
        return []
    if (not any("share_with_links" in v for v in ctx.features.videos.values())) :
        ctx.skip("T4b rerank by stored links", "videos.csv has no share_with_links column: rerun scripts/dump_corpus_features.py (it now writes it)")
        return []

    rows, records = [], []
    slices = (("A", lambda r : r.bench == "A"), ("B, L videos", lambda r : r.bench == "B" and r.prefix == "L"), ("A + B, L videos", lambda r : r.prefix == "L"))
    for label, on_role, off_role in SETTINGS :
        on_code, off_code = ctx.data.code_for(on_role), ctx.data.code_for(off_role)
        if (not on_code or not off_code) :
            continue
        for slice_name, in_slice in slices :
            for group, wanted in (("all L", None), ("stored links", True), ("fallback (no links)", False)) :
                def pick(code : str) -> list[Result] :
                    return [r for r in ctx.data.results_of(code) if r.prefix == "L" and in_slice(r) and (wanted is None or _has_links(ctx, r.ref_video) is wanted)]

                on, off = pick(on_code), pick(off_code)
                if (not on or not off) :
                    continue
                s_on, s_off = M.summary(on, with_ci = False), M.summary(off, with_ci = False)
                c = M.compare(off, on)
                h1, h10 = c["hit_at_1"], c["r_at_10"]
                values = (_interval_score(on), _interval_score(off), _distinct_videos(on), _distinct_videos(off), _linked_frame_share(ctx, on), _linked_frame_share(ctx, off))
                rows.append([label, slice_name, group, str(s_on["n"]),
                             pct(s_on["hit_at_1"]), pct(s_off["hit_at_1"]), f"+{h1['gained']}/-{h1['lost']}", fmt_p(h1["p"]),
                             pct(s_on["r_at_10"]), pct(s_off["r_at_10"]), f"+{h10['gained']}/-{h10['lost']}",
                             num(s_on["mrr"]), num(s_off["mrr"]),
                             num(values[0]), num(values[1]), num(values[2], 1), num(values[3], 1), pct(values[4]), pct(values[5])])
                records.append({"setting" : label, "slice" : slice_name, "reference_videos" : group, "n" : s_on["n"],
                                "hit_at_1_on" : s_on["hit_at_1"], "hit_at_1_off" : s_off["hit_at_1"], "hit_at_1_gained" : h1["gained"], "hit_at_1_lost" : h1["lost"], "hit_at_1_p_raw" : h1["p"],
                                "r_at_10_on" : s_on["r_at_10"], "r_at_10_off" : s_off["r_at_10"], "r_at_10_gained" : h10["gained"], "r_at_10_lost" : h10["lost"],
                                "mrr_on" : s_on["mrr"], "mrr_off" : s_off["mrr"],
                                "interval_score_on" : values[0], "interval_score_off" : values[1], "distinct_videos_on" : values[2], "distinct_videos_off" : values[3],
                                "linked_frame_share_on" : values[4], "linked_frame_share_off" : values[5]})
    if (not rows) :
        ctx.skip("T4b rerank by stored links", "no rerank on/off pair in the run folder")
        return []
    known = [_has_links(ctx, r.ref_video) for r in ctx.data.results_of(ctx.base) if r.prefix == "L"]
    counted = f"L reference queries of the baseline: {sum(1 for k in known if k)} with stored links, {sum(1 for k in known if k is False)} without, {sum(1 for k in known if k is None)} not in the features."
    return [Table(
        "T4b", "T4b_rerank_by_links",
        "Rerank on against off for L reference videos, split by whether the reference video has stored neighbour links (stored links: 6 neighbours, self excluded; none: the fallback of 2 either side, self included).",
        ["Setting", "Slice", "Reference videos", "n", "Hit@1 on", "off", "+/-", "raw p", "R@10 on", "off", "+/-", "MRR on", "off", "Interval score on", "off",
         "Distinct videos in top 100, on", "off", "Frames from linked videos %, on", "off"],
        rows, small = True, records = records, align = "lllr" + "r" * 15,
        notes = [counted,
                 "Video level: Hit@1, R@10 and MRR from the stored fused top-100 frames; +/- counts queries gained and lost with rerank on against off (paired); raw p is the exact McNemar p of Hit@1, NOT adjusted for the many rows, read it only as a size indicator. Interval score: mean official R-Score over the KIS and QA queries. Distinct videos and frames from linked videos: means over the queries, computed from the stored top-100 frames.",
                 "Read n first: a cell of 18 queries cannot separate a difference of a few queries from noise. The stored data cannot say WHY the groups differ (link status follows the video series), and no arm applied one neighbourhood definition to both groups; only the difference between on and off within a group is observed.",
                 M.power_note(ctx.data)])]
