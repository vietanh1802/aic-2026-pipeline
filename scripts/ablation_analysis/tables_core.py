# scripts/ablation_analysis/tables_core.py
"""T1 to T6 and T13: corpus and benchmarks, the main ablation, encoder grid, rerank, text policy,
per task and prefix, sensitivity. Each builder returns a list of Table and never raises on missing
optional input: it calls ctx.skip() and returns what it can."""
from __future__ import annotations

import statistics
from typing import Any

import numpy as np

from ablation_analysis import metrics as M
from ablation_analysis.context import Ctx
from ablation_analysis.data import Result
from ablation_analysis.errors import words
from ablation_analysis.tablefmt import Table, best_cells, fmt_p, interval, num, pct

BENCH_LABEL = {"A" : "Benchmark A (rounds 1 to 3)", "B" : "Benchmark B (final)"}


def _row_values(s : dict[str, Any]) -> list[float] :
    return [s["hit_at_1"], s["r_at_5"], s["r_at_10"], s["mrr"]]


def _cells(s : dict[str, Any]) -> list[str] :
    return [pct(s["hit_at_1"]), pct(s["r_at_5"]), pct(s["r_at_10"]), num(s["mrr"])]


def _n(ctx : Ctx, bench : str) -> int :
    return len(ctx.data.results_of(ctx.base, bench))


# ─── T1 ────────────────────────────────────────────────────────────────────

def t1_corpus_and_benchmarks(ctx : Ctx) -> list[Table] :
    tables = []
    if (ctx.features is None) :
        ctx.skip("T1a corpus", "no --features folder (run scripts/dump_corpus_features.py)")
    else :
        by_shot = ctx.features.shots_by_video()
        rows, records = [], []
        for label in ("L", "M", "N", "S", "All") :
            videos = [v for v in ctx.features.videos.values() if label == "All" or v["prefix"] == label]
            shots = [s for v in videos for s in by_shot.get(v["video"], [])]
            per_shot = [s["n_keyframes"] for s in shots]
            record = {"prefix" : label, "videos" : len(videos), "hours_lower_bound" : round(sum(v["duration_s"] for v in videos) / 3600, 1),
                      "keyframes" : sum(v["n_keyframes"] for v in videos), "shots" : len(shots),
                      "keyframes_per_shot_mean" : round(statistics.mean(per_shot), 2) if per_shot else None,
                      "keyframes_per_shot_median" : statistics.median(per_shot) if per_shot else None}
            records.append(record)
            rows.append([label, f"{record['videos']:,}", f"{record['hours_lower_bound']:,.1f}", f"{record['keyframes']:,}", f"{record['shots']:,}",
                         num(record["keyframes_per_shot_mean"], 2), f"{record['keyframes_per_shot_median']:g}"])
        tables.append(Table(
            "T1a", "T1a_corpus", "Collection size by video batch, from the keyframe metadata.",
            ["Batch", "Videos", "Hours", "Keyframes", "Shots", "Keyframes per shot (mean)", "Keyframes per shot (median)"], rows, records = records,
            notes = ["Hours are the last keyframe's frame number divided by the frame rate, a lower bound of the true duration (frames after the last keyframe are not counted)."]))

    datasets = []
    for dataset in sorted({r.dataset for r in ctx.data.results_of(ctx.base)}) :
        datasets.append((dataset, [r for r in ctx.data.results_of(ctx.base) if r.dataset == dataset]))
    columns = [(d, rs) for d, rs in datasets if rs[0].bench == "A"]
    pooled_a = [r for _d, rs in columns for r in rs]
    columns.append(("A pooled", pooled_a))
    columns += [(d, rs) for d, rs in datasets if rs[0].bench == "B"]
    header = ["", *[c for c, _rs in columns]]
    body : list[list[str]] = []

    def add(label : str, fn) -> None :
        body.append([label, *[fn(rs) for _c, rs in columns]])

    add("Queries", lambda rs : str(len(rs)))
    for task in ("KIS", "QA", "TRAKE") :
        add(f"  {task}", lambda rs, t = task : str(sum(1 for r in rs if r.task == t)))
    for prefix in ("L", "M", "N", "S") :
        add(f"Reference video prefix {prefix}", lambda rs, p = prefix : str(sum(1 for r in rs if r.prefix == p)))
    add("Query length in words (mean)", lambda rs : f"{statistics.mean(words(r.query_vi) for r in rs):.1f}")
    add("  median", lambda rs : f"{statistics.median(words(r.query_vi) for r in rs):.0f}")
    add("  range", lambda rs : f"{min(words(r.query_vi) for r in rs)} to {max(words(r.query_vi) for r in rs)}")
    for flag in ("vfr_times", "whole_video_interval") :
        add(f"Flagged {flag}", lambda rs, f = flag : str(sum(1 for r in rs if f in r.flags)))
    add("Flagged, any", lambda rs : str(sum(1 for r in rs if r.flags)))

    def provenance(rs : list[Result]) -> str :
        kinds = sorted({(ctx.data.refs.get(r.uid) or {}).get("provenance") or "?" for r in rs})
        return "; ".join(k.replace("team_", "").replace("_", " ") for k in kinds)
    add("Label provenance", provenance)
    tables.append(Table(
        "T1b", "T1b_benchmarks", "The two benchmarks. A is the three preliminary rounds with team-made labels from manual review of intervals; B is the final round with the organisers' appeal answers (one timestamp, plus or minus 5 s).",
        header, body, small = True, align = "l" + "r" * len(columns),
        notes = ["Flags: vfr_times = reference video has keyframe timestamps that drift from the container clock (49 N videos); whole_video_interval = the valid interval covers the whole video.",
                 "The team filed remark requests on 7 final queries; the repository does not record which, so no flag exists for them."]))
    return tables


# ─── T2 ────────────────────────────────────────────────────────────────────

def t2_main_ablation(ctx : Ctx) -> list[Table] :
    codes = ctx.retrieval_codes()
    summaries = {b : {c : M.summary(ctx.data.results_of(c, b)) for c in codes} for b in ("A", "B")}
    note = M.power_note(ctx.data)
    rows, values, records = [], [], []
    for code in codes :
        row = [ctx.name(code)]
        value = [None]
        record : dict[str, Any] = {"configuration" : ctx.name(code)}
        for b in ("A", "B") :
            s = summaries[b][code]
            row += _cells(s)
            value += _row_values(s)
            record.update({f"{b}_hit_at_1" : s["hit_at_1"], f"{b}_r_at_5" : s["r_at_5"], f"{b}_r_at_10" : s["r_at_10"], f"{b}_mrr" : s["mrr"], f"{b}_n" : s["n"]})
        rows.append(row)
        values.append(value)
        records.append(record)
    main = Table(
        "T2", "T2_main_ablation", "Ablation of the retrieval pipeline. Hit@1, R@5 and R@10 in percent, MRR as a fraction; video level, best value per column in bold.",
        ["Configuration", "Hit@1", "R@5", "R@10", "MRR", "Hit@1", "R@5", "R@10", "MRR"], rows, align = "lrrrrrrrr",
        group_header = [("", 1), (f"{BENCH_LABEL['A']}, n = {_n(ctx, 'A')}", 4), (f"{BENCH_LABEL['B']}, n = {_n(ctx, 'B')}", 4)],
        bold = best_cells(rows, list(range(1, 9)), values), notes = [note] if note else [], records = records, small = True)
    tables = [main]
    for b in ("A", "B") :
        ext_rows, ext_records = [], []
        for code in codes :
            s = summaries[b][code]
            ext_rows.append([ctx.name(code), str(s["n"]), str(s["failed"]),
                             f"{pct(s['hit_at_1'])} {interval(*s['hit_at_1_ci'])}", pct(s["r_at_3"]), f"{pct(s['r_at_5'])} {interval(*s['r_at_5_ci'])}",
                             f"{pct(s['r_at_10'])} {interval(*s['r_at_10_ci'])}", pct(s["r_at_20"]), pct(s["r_at_50"]), pct(s["r_at_100"]),
                             f"{num(s['mrr'])} {interval(*s['mrr_ci'], scale = 1.0, digits = 3)}", num(s["median_rank"], 1), pct(s["not_retrieved_rate"])])
            ext_records.append({"configuration" : ctx.name(code), "n" : s["n"], "failed" : s["failed"], **{f"r_at_{k}" : s[f"r_at_{k}"] for k in (1, 3, 5, 10, 20, 50, 100)},
                                **{f"r_at_{k}_low" : s[f"r_at_{k}_ci"][0] for k in (1, 5, 10)}, **{f"r_at_{k}_high" : s[f"r_at_{k}_ci"][1] for k in (1, 5, 10)},
                                "mrr" : s["mrr"], "mrr_low" : s["mrr_ci"][0], "mrr_high" : s["mrr_ci"][1], "median_rank" : s["median_rank"],
                                "median_rank_low" : s["median_rank_ci"][0], "median_rank_high" : s["median_rank_ci"][1], "not_retrieved_rate" : s["not_retrieved_rate"]})
        tables.append(Table(
            f"T2x-{b}", f"T2x_extended_{b}", f"Extended metrics, {BENCH_LABEL[b]}. Brackets are 95% intervals (Wilson for proportions, bootstrap over queries for MRR). Median rank is over the queries where the reference video is returned.",
            ["Configuration", "n", "failed", "Hit@1 [95%]", "R@3", "R@5 [95%]", "R@10 [95%]", "R@20", "R@50", "R@100", "MRR [95%]", "Median rank", "Not retrieved"],
            ext_rows, align = "lrrlrlllrrlrr", small = True, records = ext_records, notes = [note] if note else []))
    return tables


# ─── T3 ────────────────────────────────────────────────────────────────────

def _grid_table(ctx : Ctx, bench : str, codes : list[str], slug : str, title : str, caption : str) -> Table :
    fam = M.family(ctx.data, bench, ctx.base, codes)
    rows, records = [], []
    for code in [ctx.base, *[c for c in codes if c != ctx.base]] :
        s = M.summary(ctx.data.results_of(code, bench), with_ci = False)
        row = [ctx.name(code)]
        record : dict[str, Any] = {"configuration" : ctx.name(code), "n" : s["n"]}
        for metric, k in M.HIT_METRICS :
            row.append(pct(s[metric]))
            record[metric] = s[metric]
            if (code == ctx.base) :
                row += ["", "", ""]
                continue
            c = fam[code][metric]
            row += [f"{100 * c['delta']:+.1f}", f"+{c['gained']}/-{c['lost']}", fmt_p(c["p_holm"])]
            record.update({f"{metric}_delta" : c["delta"], f"{metric}_gained" : c["gained"], f"{metric}_lost" : c["lost"], f"{metric}_p" : c["p"], f"{metric}_p_holm" : c["p_holm"]})
        row.append(num(s["mrr"]))
        if (code == ctx.base) :
            row.append("")
        else :
            m = fam[code]["mrr"]
            row.append(f"{m['delta']:+.3f} {interval(*m['ci'], scale = 1.0, digits = 3)}")
            record.update({"mrr_delta" : m["delta"], "mrr_delta_low" : m["ci"][0], "mrr_delta_high" : m["ci"][1]})
        record["mrr"] = s["mrr"]
        rows.append(row)
        records.append(record)
    columns = ["Configuration"]
    for name in ("Hit@1", "R@5", "R@10") :
        columns += [name, "delta", "+/-", "p Holm"]
    columns += ["MRR", "delta MRR [95%]"]
    return Table(title, slug, caption, columns, rows, align = "l" + "rrrr" * 3 + "rl", small = True, records = records,
                 group_header = [("", 1), ("Hit@1", 4), ("R@5", 4), ("R@10", 4), ("MRR", 2)],
                 notes = ["delta is in percentage points against the baseline (first row); +/- counts the queries gained and lost against it. p Holm: exact two-sided McNemar on those discordant pairs, Holm-adjusted over every configuration and every metric compared with the baseline in this benchmark.",
                          M.power_note(ctx.data)])


def t3_encoder_grid(ctx : Ctx) -> list[Table] :
    codes = ctx.codes("base", "single:", "pair:")
    codes = [c for c in codes if ctx.info(c).role in ("base", *[f"single:{m}" for m in ("beit3", "clip", "siglip2")], "pair:beit3+clip", "pair:beit3+siglip2", "pair:clip+siglip2")]
    # The Holm family is every comparison with the baseline in the benchmark, so it is computed over all retrieval configurations.
    out = []
    for b in ("A", "B") :
        full = M.family(ctx.data, b, ctx.base, ctx.retrieval_codes())
        table = _grid_table(ctx, b, codes, f"T3_encoder_grid_{b}", f"T3-{b}", f"Encoder grid, {BENCH_LABEL[b]} (n = {_n(ctx, b)}): each encoder alone, each pair, and all three (baseline).")
        # Replace the family-restricted p values by the full-family ones so they match T2 and T4.
        for r, code in enumerate([ctx.base, *[c for c in codes if c != ctx.base]]) :
            if (code == ctx.base) :
                continue
            for i, (metric, _k) in enumerate(M.HIT_METRICS) :
                table.rows[r][1 + 4 * i + 3] = fmt_p(full[code][metric]["p_holm"])
                table.records[r][f"{metric}_p_holm"] = full[code][metric]["p_holm"]
        out.append(table)
    return out


# ─── T4 ────────────────────────────────────────────────────────────────────

def t4_rerank(ctx : Ctx) -> list[Table] :
    pairs = [("all three encoders", ctx.data.code_for("base"), ctx.data.code_for("all:off"))]
    pairs += [(f"{m} alone", ctx.data.code_for(f"single:{m}"), ctx.data.code_for(f"single:{m}:off")) for m in ("beit3", "clip", "siglip2")]
    after = ctx.data.code_for("all:after_fusion")
    rows, records = [], []
    comparisons = []
    for label, on, off in pairs :
        if (not on or not off) :
            continue
        for b in ("A", "B") :
            fam_c = M.compare(ctx.data.results_of(off, b), ctx.data.results_of(on, b))
            comparisons.append((label, b, "all", fam_c))
    adjusted = {}
    if (comparisons) :
        from ablation_analysis import stats
        keys = [(i, m) for i, c in enumerate(comparisons) for m, _k in M.HIT_METRICS]
        adj = stats.holm([comparisons[i][3][m]["p"] for i, m in keys])
        adjusted = {k : p for k, p in zip(keys, adj)}
    for i, (label, b, _slice, c) in enumerate(comparisons) :
        on = next(p for p in pairs if p[0] == label)
        for variant, code in (("rerank per model (shipped)", on[1]), ("rerank off", on[2])) :
            s = M.summary(ctx.data.results_of(code, b), with_ci = False)
            rows.append([label, b, "all", variant, str(s["n"]), *_cells(s), "", "", ""])
            records.append({"setting" : label, "bench" : b, "slice" : "all", "variant" : variant, "n" : s["n"], "hit_at_1" : s["hit_at_1"], "r_at_5" : s["r_at_5"], "r_at_10" : s["r_at_10"], "mrr" : s["mrr"]})
        h = c["hit_at_1"]
        rows[-2][-3:] = [f"{100 * h['delta']:+.1f}", f"+{h['gained']}/-{h['lost']}", fmt_p(adjusted.get((i, "hit_at_1")))]
        records[-2].update({"hit_at_1_delta_vs_off" : h["delta"], "gained" : h["gained"], "lost" : h["lost"], "p_holm_hit_at_1" : adjusted.get((i, "hit_at_1")),
                            "p_holm_r_at_10" : adjusted.get((i, "r_at_10")), "r_at_10_delta_vs_off" : c["r_at_10"]["delta"]})
    if (after) :
        for b in ("A", "B") :
            s = M.summary(ctx.data.results_of(after, b), with_ci = False)
            rows.append(["all three encoders", b, "all", "rerank after fusion (our implementation)", str(s["n"]), *_cells(s), "", "", ""])
            records.append({"setting" : "all three encoders", "bench" : b, "slice" : "all", "variant" : "rerank after fusion", "n" : s["n"], "hit_at_1" : s["hit_at_1"], "r_at_5" : s["r_at_5"], "r_at_10" : s["r_at_10"], "mrr" : s["mrr"]})
    # Per prefix: benchmark A is all L; B has all four. Raw p only, small n.
    for code, label in ((ctx.data.code_for("base"), "rerank per model (shipped)"), (ctx.data.code_for("all:off"), "rerank off"), (after, "rerank after fusion (our implementation)")) :
        if (not code) :
            continue
        for b in ("A", "B") :
            for prefix in ("L", "M", "N", "S") :
                results = ctx.data.results_of(code, b, prefix = prefix)
                if (not results) :
                    continue
                s = M.summary(results, with_ci = False)
                rows.append(["all three encoders", b, prefix, label, str(s["n"]), *_cells(s), "", "", ""])
                records.append({"setting" : "all three encoders", "bench" : b, "slice" : prefix, "variant" : label, "n" : s["n"], "hit_at_1" : s["hit_at_1"], "r_at_5" : s["r_at_5"], "r_at_10" : s["r_at_10"], "mrr" : s["mrr"]})
    table = Table(
        "T4", "T4_rerank", "Neighbour-frame reranking: per-model rerank (shipped), none, and a post-fusion variant, overall and by reference-video prefix.",
        ["Setting", "Bench", "Slice", "Variant", "n", "Hit@1", "R@5", "R@10", "MRR", "delta Hit@1 vs off", "+/-", "p Holm"], rows, small = True, records = records, align = "lllllrrrrrrr",
        notes = ["Rerank on versus off is paired on queries (delta in points, +/- gained and lost at k = 1, exact McNemar, Holm over the four settings, two benchmarks and three metrics; the R@5 and R@10 p values are in the CSV).",
                 "Neighbour definition differs by prefix: for L videos (all of benchmark A) neighbors_clip is empty for 263,895 of 360,531 frames, so rerank uses the fallback of 2 keyframes either side INCLUDING the frame itself; M, N and S use the stored neighbour links (none empty). A difference between L and the other prefixes mixes the data with this definition.",
                 "Rows by prefix are descriptive: raw counts per prefix are small. Post-fusion rerank is our re-created implementation, not the earlier code."])
    return [table]


# ─── T5 ────────────────────────────────────────────────────────────────────

TEXT_LABEL = {
    "expand_gemini" : "Expand (LLM-prepared English)",
    "translate_gtx" : "plain translation (Google Translate)",
    "raw_vi"        : "raw Vietnamese",
}


def _text_policy(ctx : Ctx, code : str) -> str :
    return ctx.info(code).config.get("text_policy", "translate_gtx")


def t5_text_policy(ctx : Ctx) -> list[Table] :
    """The text ablation: the baseline's text against the other English text (plain translation against an Expand
    baseline, or the reverse in a folder from the first run). Raw Vietnamese is a sanity check, see T5s."""
    other = ctx.data.code_for("plain_text") or ctx.data.code_for("expand_gemini")
    if (not other) :
        ctx.skip("T5 text policy", "no arm with a different English text (plain translation or Expand) in the run folder")
        return []
    pairs = [(f"{TEXT_LABEL[_text_policy(ctx, ctx.base)]} (baseline)", ctx.base), (TEXT_LABEL[_text_policy(ctx, other)], other)]
    rows, records = [], []
    for b in ("A", "B") :
        fam_ = M.family(ctx.data, b, ctx.base, ctx.retrieval_codes())[other]
        for label, code in pairs :
            s = M.summary(ctx.data.results_of(code, b), with_ci = False)
            row = [b, "all", label, str(s["n"]), *_cells(s)]
            if (code == other) :
                row += [f"{100 * fam_['hit_at_1']['delta']:+.1f}", f"+{fam_['hit_at_1']['gained']}/-{fam_['hit_at_1']['lost']}", fmt_p(fam_["hit_at_1"]["p_holm"])]
            else :
                row += ["", "", ""]
            rows.append(row)
            records.append({"bench" : b, "slice" : "all", "text" : label, "n" : s["n"], "hit_at_1" : s["hit_at_1"], "r_at_5" : s["r_at_5"], "r_at_10" : s["r_at_10"], "mrr" : s["mrr"]})
    # Terciles of query length (words in the Vietnamese query), over all queries of both benchmarks.
    everyone = ctx.data.results_of(ctx.base)
    lengths = np.array([words(r.query_vi) for r in everyone], dtype = float)
    cuts = np.quantile(lengths, [1 / 3, 2 / 3])
    def tercile(r : Result) -> int :
        w = words(r.query_vi)
        return 0 if w <= cuts[0] else 1 if w <= cuts[1] else 2
    names = [f"short (<= {cuts[0]:.0f} words)", f"medium (<= {cuts[1]:.0f})", f"long (> {cuts[1]:.0f})"]
    for t in range(3) :
        uids = {r.uid for r in everyone if tercile(r) == t}
        for label, code in pairs :
            results = [r for r in ctx.data.results_of(code) if r.uid in uids]
            s = M.summary(results, with_ci = False)
            rows.append(["A+B", names[t], label, str(s["n"]), *_cells(s), "", "", ""])
            records.append({"bench" : "A+B", "slice" : names[t], "text" : label, "n" : s["n"], "hit_at_1" : s["hit_at_1"], "r_at_5" : s["r_at_5"], "r_at_10" : s["r_at_10"], "mrr" : s["mrr"]})
    return [Table("T5", "T5_text_policy", f"Text policy: {pairs[0][0]} against {pairs[1][0]}, overall and by query-length tercile.",
                  ["Bench", "Slice", "Text", "n", "Hit@1", "R@5", "R@10", "MRR", "delta Hit@1", "+/-", "p Holm"], rows, small = True, records = records, align = "lllrrrrrrrr",
                  notes = ["Both arms search the same queries with the text recorded for them. delta, +/- and p Holm as in T3 (Holm family: all ablation arms against the baseline). Tercile rows pool A and B and are descriptive.", M.power_note(ctx.data)])]


def t5s_sanity(ctx : Ctx) -> list[Table] :
    """Raw Vietnamese text against the English-only encoders: a sanity check that the encoders really need English,
    not an ablation arm, so it is kept out of T2 to T6 and shown here once."""
    codes = ctx.sanity_codes()
    if (not codes) :
        ctx.skip("T5s sanity", "no sanity configuration in the run folder")
        return []
    rows, records = [], []
    for b in ("A", "B") :
        for label, code in [("baseline", ctx.base), *[(ctx.name(c), c) for c in codes]] :
            results = ctx.data.results_of(code, b)
            s = M.summary(results, with_ci = False)
            rows.append([b, ctx.name(code) if label == "baseline" else label, str(s["n"]), *_cells(s), pct(s["not_retrieved_rate"])])
            records.append({"bench" : b, "configuration" : ctx.name(code), "n" : s["n"], "hit_at_1" : s["hit_at_1"], "r_at_5" : s["r_at_5"], "r_at_10" : s["r_at_10"], "mrr" : s["mrr"], "not_retrieved_rate" : s["not_retrieved_rate"]})
    return [Table("T5s", "T5s_sanity", "Sanity check: raw Vietnamese text against the baseline. BEiT-3 and OpenCLIP are English-only, so this is expected to collapse; it is not an ablation arm and appears in no other table.",
                  ["Bench", "Configuration", "n", "Hit@1", "R@5", "R@10", "MRR", "Not retrieved"], rows, small = True, records = records, align = "llrrrrrr")]


# ─── T6 ────────────────────────────────────────────────────────────────────

def t6_by_task_and_prefix(ctx : Ctx) -> list[Table] :
    singles = [c for c in (ctx.data.code_for(f"single:{m}") for m in ("beit3", "clip", "siglip2")) if c]
    rows, records = [], []
    for b in ("A", "B") :
        slices = [("task", t) for t in ("KIS", "QA", "TRAKE")] + [("prefix", p) for p in ("L", "M", "N", "S")]
        for kind, value in slices :
            kwargs = {"task" : value} if kind == "task" else {"prefix" : value}
            base = ctx.data.results_of(ctx.base, b, **kwargs)
            if (not base) :
                continue
            sb = M.summary(base, with_ci = False)
            best = max(singles, key = lambda c : M.summary(ctx.data.results_of(c, b, **kwargs), with_ci = False)["mrr"]) if singles else None
            sbest = M.summary(ctx.data.results_of(best, b, **kwargs), with_ci = False) if best else None
            rows.append([b, value, str(sb["n"]), *_cells(sb), ctx.name(best) if best else "", *(_cells(sbest) if sbest else ["", "", "", ""])])
            records.append({"bench" : b, "slice" : value, "n" : sb["n"], "baseline_hit_at_1" : sb["hit_at_1"], "baseline_r_at_5" : sb["r_at_5"], "baseline_r_at_10" : sb["r_at_10"], "baseline_mrr" : sb["mrr"],
                            "best_single" : ctx.name(best) if best else None, **({f"single_{k}" : sbest[k] for k in ("hit_at_1", "r_at_5", "r_at_10", "mrr")} if sbest else {})})
    return [Table("T6", "T6_task_and_prefix", "Baseline by task type and by reference-video prefix, with the best single encoder of each slice (by MRR) beside it.",
                  ["Bench", "Slice", "n", "Hit@1", "R@5", "R@10", "MRR", "Best single", "Hit@1", "R@5", "R@10", "MRR"], rows, small = True, records = records, align = "llrrrrrlrrrr",
                  notes = ["Slices are small (see n); read them as descriptions. The best single encoder is chosen on the same queries it is then reported on, so its numbers are optimistic."])]


# ─── T13 ───────────────────────────────────────────────────────────────────

def t13_sensitivity(ctx : Ctx) -> list[Table] :
    tables = []
    rows, records = [], []
    for b in ("A", "B") :
        for code in ctx.retrieval_codes() :
            allq = M.summary(ctx.data.results_of(code, b), with_ci = False)
            clean = M.summary(ctx.data.results_of(code, b, clean = True), with_ci = False)
            rows.append([b, ctx.name(code), str(allq["n"]), pct(allq["hit_at_1"]), num(allq["mrr"]), str(clean["n"]), pct(clean["hit_at_1"]), num(clean["mrr"])])
            records.append({"bench" : b, "configuration" : ctx.name(code), "n_all" : allq["n"], "hit_at_1_all" : allq["hit_at_1"], "mrr_all" : allq["mrr"], "n_clean" : clean["n"], "hit_at_1_clean" : clean["hit_at_1"], "mrr_clean" : clean["mrr"]})
    tables.append(Table("T13a", "T13a_without_flagged", "Sensitivity to the flagged queries (vfr_times, whole_video_interval): all queries against the queries without a flag.",
                        ["Bench", "Configuration", "n all", "Hit@1", "MRR", "n unflagged", "Hit@1", "MRR"], rows, small = True, records = records, align = "llrrrrrr",
                        notes = ["Rounds 1 to 3 are all L videos and carry no flag, so benchmark A rows are identical. Both flags concern interval-level labels; the unflagged rows here still drop those queries from the video-level metrics."]))

    rounds = sorted({r.dataset for r in ctx.data.results_of(ctx.base, "A")})
    rows, records = [], []
    for code in ctx.retrieval_codes() :
        row, record = [ctx.name(code)], {"configuration" : ctx.name(code)}
        for left_out in rounds :
            results = [r for r in ctx.data.results_of(code, "A") if r.dataset != left_out]
            s = M.summary(results, with_ci = False)
            row += [pct(s["hit_at_1"]), num(s["mrr"])]
            record.update({f"without_{left_out}_hit_at_1" : s["hit_at_1"], f"without_{left_out}_mrr" : s["mrr"], f"without_{left_out}_n" : s["n"]})
        rows.append(row)
        records.append(record)
    columns = ["Configuration"] + [x for r in rounds for x in (f"Hit@1 without {r}", "MRR")]
    tables.append(Table("T13b", "T13b_leave_one_round_out", "Benchmark A with one round left out in turn.", columns, rows, small = True, records = records,
                        notes = ["A change in a configuration's rank order when a round is dropped means the ordering is not stable across rounds."]))

    rows, records = [], []
    for code in ctx.retrieval_codes() :
        a, bs = M.summary(ctx.data.results_of(code, "A")), M.summary(ctx.data.results_of(code, "B"))
        rows.append([ctx.name(code), f"{pct(a['hit_at_1'])} {interval(*a['hit_at_1_ci'])}", f"{pct(bs['hit_at_1'])} {interval(*bs['hit_at_1_ci'])}", num(a["mrr"]), num(bs["mrr"])])
        records.append({"configuration" : ctx.name(code), "A_hit_at_1" : a["hit_at_1"], "A_low" : a["hit_at_1_ci"][0], "A_high" : a["hit_at_1_ci"][1], "B_hit_at_1" : bs["hit_at_1"], "B_low" : bs["hit_at_1_ci"][0], "B_high" : bs["hit_at_1_ci"][1], "A_mrr" : a["mrr"], "B_mrr" : bs["mrr"]})
    tables.append(Table("T13c", "T13c_A_versus_B", "Benchmark A against benchmark B (different queries, different label sources, different video prefixes), Hit@1 with Wilson intervals.",
                        ["Configuration", "Hit@1 A [95%]", "Hit@1 B [95%]", "MRR A", "MRR B"], rows, small = True, records = records, align = "lllrr",
                        notes = ["Unpaired: the two benchmarks do not share queries. A is all L videos with team labels; B has M, N and S videos and the organisers' appeal answers, so a gap between them is not attributable to one cause."]))
    return tables
