# scripts/ablation_analysis/tables_more.py
"""T7 to T12 and T14, T15: TRAKE, complementarity, interval level, error taxonomy, text-signal measures,
efficiency, keyframe sampling."""
from __future__ import annotations

import statistics
from typing import Any

import numpy as np

from ablation_analysis import errors as E
from ablation_analysis import metrics as M
from ablation_analysis import sampling, stats
from ablation_analysis.context import Ctx
from ablation_analysis.data import Result
from ablation_analysis.tablefmt import Table, interval, num, pct

MODEL_LABEL = {"beit3" : "BEiT-3", "clip" : "OpenCLIP", "siglip2" : "SigLIP2"}
BENCH_LABEL = {"A" : "Benchmark A", "B" : "Benchmark B"}


# ─── T7 TRAKE ──────────────────────────────────────────────────────────────

def t7_trake(ctx : Ctx) -> list[Table] :
    t01, t02 = ctx.data.code_for("trake_n"), ctx.data.code_for("trake_plain")
    if (not t01 and not t02) :
        ctx.skip("T7 TRAKE", "no TRAKE configuration in the run folder (run --preset trake)")
        return []
    rows, records = [], []
    for code, label in ((t01, "TRAKE-N (T01)"), (t02, "plain ensemble over the whole text (T02)")) :
        if (not code) :
            continue
        results = ctx.data.results_of(code)
        s = M.summary(results, with_ci = False)
        events = [r.extra["trake"]["events"] for r in results if (r.extra.get("trake") or {}).get("events")]
        correct, total = sum(e["correct"] for e in events), sum(e["total"] for e in events)
        low, high = stats.wilson(correct, total) if total else (float("nan"), float("nan"))
        rows.append([label, str(s["n"]), pct(s["hit_at_1"]), pct(s["r_at_5"]), pct(s["r_at_10"]), num(s["mrr"]),
                     f"{correct}/{total}" if total else "", f"{pct(correct / total)} {interval(low, high)}" if total else "not scored"])
        records.append({"configuration" : label, "n" : s["n"], "hit_at_1" : s["hit_at_1"], "r_at_5" : s["r_at_5"], "r_at_10" : s["r_at_10"], "mrr" : s["mrr"],
                        "events_correct" : correct if total else None, "events_total" : total or None, "event_accuracy" : correct / total if total else None})
    main = Table("T7a", "T7a_trake", "TRAKE queries: TRAKE-N (separate event searches, coverage shortlist, ordered frame selection) against one search over the whole description.",
                 ["Configuration", "n", "Hit@1", "R@5", "R@10", "MRR", "Events correct", "Event accuracy [95%]"], rows, small = True, records = records, align = "lrrrrrrl",
                 notes = ["Eight queries and 31 events support only descriptive statements. Video-level scores as elsewhere; an event is correct when the chosen frame is within 5 s of the team's reference frame (each event has one reference frame, no interval).",
                          "The event interval uses all events of the 8 queries as if independent; events of one query are not."])
    tables = [main]
    if (t01) :
        results = ctx.data.results_of(t01)
        stages : dict[str, int] = {}
        listing = []
        for r in results :
            stage = E.trake_stage(r)
            stages[stage] = stages.get(stage, 0) + 1
            d = (r.extra.get("trake") or {}).get("discovery") or {}
            ev = (r.extra.get("trake") or {}).get("events") or {}
            listing.append({"dataset" : r.dataset, "query_key" : r.key, "ref_video" : r.ref_video, "stage" : stage, "video_rank" : r.rank,
                            "shortlist_rank" : d.get("reference_rank"), "events_found_in_discovery" : d.get("reference_events"), "events_correct" : ev.get("correct"), "events_total" : ev.get("total")})
        order = ["not shortlisted", "shortlisted, no feasible chain", "chain found, reference video not ranked first", "right video, wrong event frame", "success", "right video, events not scored", "unknown (no discovery block)"]
        rows = [[s, str(stages[s])] for s in order if s in stages]
        tables.append(Table("T7b", "T7b_trake_stages", "Where each TRAKE-N query stopped, from the stored shortlist stage.", ["Stage", "Queries"], rows, align = "lr", records = listing,
                            notes = ["not shortlisted: the reference video is not among the K = 20 videos of the coverage shortlist. no feasible chain: shortlisted but no ordered pick under the gap rule. Stages follow the order the pipeline applies them; one query counts once, in the first stage where it stops. The shortlist is rebuilt from the same rule as the production function (see the stored consistent flag)."]))
    return tables


# ─── T8 complementarity ────────────────────────────────────────────────────

def t8_complementarity(ctx : Ctx) -> list[Table] :
    models = ("beit3", "clip", "siglip2")
    codes = {m : ctx.data.code_for(f"single:{m}") for m in models}
    if (not all(codes.values())) :
        ctx.skip("T8 complementarity", "the three single-encoder runs are not all present")
        return []
    rows, records, corr_rows, corr_records = [], [], [], []
    for b in ("A", "B") :
        uids = ctx.data.query_ids(b)
        by = {m : {r.uid : r for r in ctx.data.results_of(codes[m], b)} for m in models}
        base = {r.uid : r for r in ctx.data.results_of(ctx.base, b)}
        uids = [u for u in uids if all(u in by[m] for m in models) and u in base]
        if (not uids) :
            continue
        for k in (1, 10) :
            hit = {m : np.array([by[m][u].hit(k) for u in uids]) for m in models}
            fusion = np.array([base[u].hit(k) for u in uids])
            union, inter = np.any([hit[m] for m in models], axis = 0), np.all([hit[m] for m in models], axis = 0)
            excl = {m : int((hit[m] & ~np.any([hit[o] for o in models if o != m], axis = 0)).sum()) for m in models}
            gain, loss = int((fusion & ~union).sum()), int((~fusion & union).sum())
            row = [b, str(k), str(len(uids)), *[str(int(hit[m].sum())) for m in models], str(int(union.sum())), str(int(inter.sum())),
                   *[str(excl[m]) for m in models], str(int(fusion.sum())), str(gain), str(loss), str(int(union.sum() - fusion.sum()))]
            rows.append(row)
            records.append({"bench" : b, "k" : k, "n" : len(uids), **{f"hits_{m}" : int(hit[m].sum()) for m in models}, "union_oracle" : int(union.sum()), "intersection" : int(inter.sum()),
                            **{f"exclusive_{m}" : excl[m] for m in models}, "fusion_hits" : int(fusion.sum()), "fusion_gain" : gain, "fusion_loss" : loss, "oracle_minus_fusion" : int(union.sum() - fusion.sum())})
            for i, a in enumerate(models) :
                for c in models[i + 1 : ] :
                    agree = float((hit[a] == hit[c]).mean()) if uids else float("nan")
                    records[-1][f"agree_{a}_{c}"] = agree
        for i, a in enumerate(models) :
            for c in models[i + 1 : ] :
                x = [by[a][u].rank_or_miss for u in uids]
                y = [by[c][u].rank_or_miss for u in uids]
                rho, low, high = stats.correlation_ci(x, y)
                tau = stats.kendall_tau(x, y)
                agree1 = float(np.mean([by[a][u].hit(1) == by[c][u].hit(1) for u in uids])) if uids else float("nan")
                agree10 = float(np.mean([by[a][u].hit(10) == by[c][u].hit(10) for u in uids])) if uids else float("nan")
                corr_rows.append([b, f"{MODEL_LABEL[a]} vs {MODEL_LABEL[c]}", str(len(uids)), pct(agree1), pct(agree10), num(rho, 2), interval(low, high, scale = 1.0, digits = 2), num(tau, 2)])
                corr_records.append({"bench" : b, "pair" : f"{a} vs {c}", "n" : len(uids), "agree_at_1" : agree1, "agree_at_10" : agree10, "spearman" : rho, "spearman_low" : low, "spearman_high" : high, "kendall_tau_b" : tau})
    columns = ["Bench", "k", "n", "BEiT-3", "OpenCLIP", "SigLIP2", "Union (oracle)", "All three", "Only BEiT-3", "Only OpenCLIP", "Only SigLIP2", "Fusion", "Fusion gain", "Fusion loss", "Oracle - fusion"]
    first = Table("T8a", "T8a_complementarity", "Complementarity of the three encoders: queries where the reference video is within the first k videos, per single-encoder run, and what fusion does with them.",
                  columns, rows, small = True, records = records, align = "lrr" + "r" * 12,
                  notes = ["Union is the best-of-three oracle. Fusion gain: fusion hits and no single encoder does. Fusion loss: a single encoder hits and fusion does not. Oracle - fusion is the gap an ideal selector would close. All counts are queries; rerank is on in every run here."])
    second = Table("T8b", "T8b_rank_agreement", "Agreement between encoders on the same queries: hit agreement at k = 1 and 10, and rank correlation of the reference video's rank.",
                   ["Bench", "Pair", "n", "Agree @1", "Agree @10", "Spearman", "[95%]", "Kendall tau-b"], corr_rows, records = corr_records, align = "llrrrrlr", small = True,
                   notes = ["A reference video that is not returned counts as rank 101 in the correlations. Agree @k is the share of queries where both encoders hit, or both miss."])
    return [first, second]


# ─── T9 interval level ─────────────────────────────────────────────────────

def t9_interval_level(ctx : Ctx) -> list[Table] :
    rows, records = [], []
    for b in ("A", "B") :
        for clean, label in ((False, "all"), (True, "without flagged")) :
            results = [r for r in ctx.data.results_of(ctx.base, b, clean = clean) if r.task != "TRAKE"]
            if (not results) :
                continue
            n = len(results)
            returned = [r for r in results if r.rank is not None]
            right_video_no_interval = [r for r in returned if not r.interval_hit]
            buckets = {g : sum(1 for r in right_video_no_interval if E.gap_bucket(r) == g) for g in ("within 5 s", "5 to 30 s", "over 30 s")}
            scores = [r.final_score for r in results if r.final_score is not None]
            rows.append([b, label, str(n), pct(sum(1 for r in results if r.hit(1)) / n), pct(sum(1 for r in results if r.hit(10)) / n), pct(sum(1 for r in results if r.interval_hit) / n),
                         num(statistics.mean(scores) if scores else None), f"{len(right_video_no_interval)} ({pct(len(right_video_no_interval) / n)})",
                         str(buckets["within 5 s"]), str(buckets["5 to 30 s"]), str(buckets["over 30 s"]), str(sum(1 for r in results if r.rank is None))])
            records.append({"bench" : b, "flags" : label, "n" : n, "video_hit_at_1" : sum(1 for r in results if r.hit(1)) / n, "video_r_at_10" : sum(1 for r in results if r.hit(10)) / n,
                            "interval_hit_top100" : sum(1 for r in results if r.interval_hit) / n, "interval_r_score" : statistics.mean(scores) if scores else None,
                            "right_video_no_frame_inside" : len(right_video_no_interval), **{f"gap_{k.replace(' ', '_')}" : v for k, v in buckets.items()}, "reference_not_returned" : sum(1 for r in results if r.rank is None)})
    return [Table("T9", "T9_interval_level", "Interval level (KIS and QA, baseline): video-level hit against the interval R-Score, and how far the nearest returned frame of the right video was from the valid interval.",
                  ["Bench", "Subset", "n", "Hit@1 (video)", "R@10 (video)", "Frame inside interval (top 100)", "Interval R-Score", "Right video, none inside", "within 5 s", "5 to 30 s", "over 30 s", "Video not returned"],
                  rows, small = True, records = records, align = "llrrrrrlrrrr",
                  notes = ["Interval R-Score is the mean over queries of the official R@k average (k = 1, 5, 20, 50, 100) at interval level. The distance columns count queries whose reference video was returned but no returned frame lies in a valid interval; the distance is from the stored top-100 frames only, so it says nothing about keyframes that were never returned.",
                           "N videos have variable frame rate: their seconds are unreliable, frame distances are exact. The 'without flagged' rows drop vfr_times and whole_video_interval queries."])]


# ─── T10 error taxonomy ────────────────────────────────────────────────────

def t10_errors(ctx : Ctx) -> list[Table] :
    tables = []
    rows, records = [], []
    for b in ("A", "B") :
        for code in ctx.retrieval_codes() :
            results = ctx.data.results_of(code, b)
            counts = {k : sum(1 for r in results if E.rank_bucket(r.rank) == k) for k in E.RANK_BUCKETS}
            rows.append([b, ctx.name(code), str(len(results)), *[str(counts[k]) for k in E.RANK_BUCKETS]])
            records.append({"bench" : b, "configuration" : ctx.name(code), "n" : len(results), **{k.replace(" ", "_") : counts[k] for k in E.RANK_BUCKETS}})
    tables.append(Table("T10a", "T10a_rank_buckets", "Where the reference video ends up, per configuration (queries per rank bucket).", ["Bench", "Configuration", "n", *E.RANK_BUCKETS], rows, small = True, records = records, align = "llrrrrrr"))

    rows, records = [], []
    for b in ("A", "B") :
        labels = E.cross_labels(ctx.data, b)
        names = [k for k in next(iter(labels.values()), {}) if k not in ("dataset", "query_key", "task", "ref_video", "prefix", "flags", "baseline_rank")]
        for name in names :
            queries = [uid for uid, row in labels.items() if row[name] is True]
            rows.append([b, name, str(len(queries)), str(len(labels)), ", ".join(k for _d, k in queries[ : 6]) + (" ..." if len(queries) > 6 else "")])
            records.append({"bench" : b, "label" : name, "queries" : len(queries), "of" : len(labels), "query_keys" : ";".join(k for _d, k in queries)})
    tables.append(Table("T10b", "T10b_cross_labels", "Automatic labels that compare configurations, per query (counts of queries).", ["Bench", "Label", "Queries", "of", "Examples"], rows, records = records, align = "llrrl",
                        notes = ["hard: no configuration of the grid has the reference video in its first 10. rescued_by_fusion@k: the baseline hits at k and no single encoder does; hurt_by_fusion@k: some single encoder hits and the baseline does not. only_one_encoder: exactly one single encoder hits. rerank_gained / rerank_lost: baseline against all-three rerank off. gtx_beats_raw / raw_beats_gtx: baseline against raw Vietnamese. @k is Hit at k."]))

    rows, records = [], []
    for b in ("A", "B") :
        misses = [r for r in ctx.data.results_of(ctx.base, b) if not r.hit(1)]
        if (not misses) :
            continue
        profiles = [E.distractor_profile(r) for r in misses]
        top_prefix = {p : sum(1 for x in profiles if x["top1_prefix"] == p) for p in ("L", "M", "N", "S")}
        rows.append([b, str(len(misses)), ", ".join(f"{p} {c}" for p, c in top_prefix.items() if c), f"{sum(1 for x in profiles if x['top1_same_series'])}/{len(misses)}",
                     f"{statistics.mean(x['ref_frames_in_top100'] for x in profiles):.1f}", f"{statistics.mean(x['distinct_videos_in_top100'] for x in profiles):.1f}"])
        records.append({"bench" : b, "baseline_misses_at_1" : len(misses), **{f"top1_prefix_{p}" : c for p, c in top_prefix.items()}, "top1_same_series" : sum(1 for x in profiles if x["top1_same_series"]),
                        "mean_reference_frames_in_top100" : statistics.mean(x["ref_frames_in_top100"] for x in profiles), "mean_distinct_videos_in_top100" : statistics.mean(x["distinct_videos_in_top100"] for x in profiles)})
    tables.append(Table("T10c", "T10c_distractors", "What the baseline returned instead, for the queries where it missed at rank 1.", ["Bench", "Misses at 1", "Prefix of the top video", "Top video from the same series", "Reference frames in the 100 (mean)", "Distinct videos in the 100 (mean)"],
                        rows, records = records, align = "lrlrrr", small = True))

    if (ctx.labels) :
        codes : dict[str, int] = {}
        labelled = [r for r in ctx.labels if (r.get("error_codes") or "").strip()]
        for row in labelled :
            for code in [c.strip() for c in row["error_codes"].replace(",", ";").split(";") if c.strip()] :
                codes[code] = codes.get(code, 0) + 1
        rows = [[code, dict(E.TAXONOMY).get(code, ""), str(count)] for code, count in sorted(codes.items())]
        tables.append(Table("T10d", "T10d_manual_error_codes", f"Manual error codes from the labelling sheet ({len(labelled)} of {len(ctx.labels)} rows labelled).", ["Code", "Meaning", "Queries"], rows, align = "llr",
                            notes = ["A query can carry several codes, so counts add up to more than the number of queries."]))
    return tables


# ─── T11 text-signal annotation measures ───────────────────────────────────

def _text_metrics(blocks : list[dict | None]) -> dict[str, Any] :
    n = len(blocks)
    flagged = [b for b in blocks if b and b["ref_flagged"]]
    with_flags = [b for b in blocks if b and b["n_flagged"] > 0]
    interval_scored = [b for b in flagged if b["ref_in_interval"] is not None]
    seen = [b for b in blocks if b and b["n_videos"] > 0]
    return {
        "n" : n, "n_flagged_ref" : len(flagged), "flag_rate_ref" : len(flagged) / n if n else None,
        "here_rate" : sum(1 for b in flagged if b["ref_location"] == "here") / len(flagged) if flagged else None,
        "in_interval" : sum(1 for b in interval_scored if b["ref_in_interval"]) / len(interval_scored) if interval_scored else None,
        "precision" : len(flagged) / sum(b["n_flagged"] for b in with_flags) if with_flags else None,
        "base_rate" : sum(b["n_flagged"] / b["n_videos"] for b in seen) / len(seen) if seen else None,
        "rescue_potential" : sum(1 for b in flagged if b["ref_rank"] is None or b["ref_rank"] > 1) / n if n else None,
    }


def t11_text_signal(ctx : Ctx) -> list[Table] :
    code = next((c for c in ctx.retrieval_codes() if any(r.extra.get("text_signal") for r in ctx.data.results_of(c))), None)
    if (code is None) :
        ctx.skip("T11 text signal", "no run carries OCR/ASR annotation blocks (cues missing)")
        return []
    rows, records = [], []
    for b in ("A", "B") :
        scoped = [r for r in ctx.data.results_of(code, b) if r.extra.get("text_signal") is not None]
        for kind in ("confirmed", "legacy_leaky") :
            for variant in ("ocr", "asr", "both") :
                if (not any(((r.extra["text_signal"].get(kind) or {}).get(variant)) for r in scoped)) :
                    continue
                for slice_name in ("all", "cue", "cue+coverage") :
                    picked = []
                    for r in scoped :
                        block = (r.extra["text_signal"].get(kind) or {}).get(variant)
                        cov = r.extra.get("text_coverage") or {}
                        has_cov = any((cov.get(s) or 0) > 0 for s in (("ocr", "asr") if variant == "both" else (variant,)))
                        if (slice_name == "all" or (block is not None and (slice_name == "cue" or has_cov))) :
                            picked.append(block)
                    if (not picked or (slice_name != "all" and not any(picked))) :
                        continue
                    m = _text_metrics(picked)
                    label = "legacy_leaky (upper bound)" if kind == "legacy_leaky" else kind
                    rows.append([b, label, variant, slice_name, str(m["n"]), str(m["n_flagged_ref"]), pct(m["flag_rate_ref"]), pct(m["here_rate"]), pct(m["in_interval"]), pct(m["precision"]), pct(m["base_rate"]), pct(m["rescue_potential"])])
                    records.append({"bench" : b, "kind" : kind, "variant" : variant, "slice" : slice_name, **m})
    tables = [Table("T11a", "T11a_text_signal", f"OCR and ASR annotation measures on the baseline run ({ctx.name(code)}). Annotation only: neither filter changes a ranking.",
                    ["Bench", "Cue kind", "Variant", "Slice", "n", "Ref flagged", "Flag rate", "Here", "In interval", "Precision", "Base rate", "Rescue potential"], rows, small = True, records = records, align = "lllllrrrrrrr",
                    notes = ["legacy_leaky cues are the seed's old filter terms, audited against the real OCR and ASR engines, so every number built on them is an upper bound. confirmed cues appear only once a reviewer has confirmed them in the cue sidecar.",
                             "Flag rate: the reference video is annotated as matched. Here: of those, the matched frame is among the returned frames. Rescue potential: the reference is flagged but not ranked first, an upper bound on what an injection stage could fix; no such stage ships."])]
    rows, records = [], []
    for b in ("A", "B") :
        for prefix in ("L", "M", "N", "S") :
            results = [r for r in ctx.data.results_of(code, b, prefix = prefix) if r.extra.get("text_coverage")]
            if (not results) :
                continue
            def share(source : str) -> float | None :
                values = [(r.extra["text_coverage"].get(source) or 0) / r.extra["text_coverage"]["keyframes"] for r in results if r.extra["text_coverage"].get("keyframes") and r.extra["text_coverage"].get(source) is not None]
                return statistics.mean(values) if values else None
            rows.append([b, prefix, str(len(results)), pct(share("ocr")), pct(share("asr"))])
            records.append({"bench" : b, "prefix" : prefix, "n" : len(results), "ocr_keyframe_share" : share("ocr"), "asr_keyframe_share" : share("asr")})
    tables.append(Table("T11b", "T11b_text_coverage", "OCR and ASR coverage of the reference videos: mean share of a reference video's keyframes with text, by prefix.", ["Bench", "Prefix", "Queries", "OCR text share", "ASR text share"], rows, records = records, align = "llrrr",
                        notes = ["Read at run time from the loaded artifacts. OCR and ASR do not exist for N and S videos and are partial for M; a missing source shows as blank."]))
    return tables


# ─── T12 efficiency ────────────────────────────────────────────────────────

def reconstructed_ms(r : Result) -> float | None :
    """Latency of one query rebuilt from the first-computation times of its models plus fusion."""
    timing = r.extra.get("model_timings")
    if (not timing or "models" not in timing) :
        return None
    models = timing["models"].values()
    total = sum(m["search_ms"] for m in models) + timing.get("fuse_ms", 0.0)
    if (timing.get("rerank_mode") == "per_model") :
        total += sum(m["rerank_ms"] for m in models)
    elif (timing.get("rerank_mode") == "after_fusion") :
        total += sum((timing.get("pool_rerank_ms") or {}).values())
    return total


def t12_efficiency(ctx : Ctx) -> list[Table] :
    rows, records = [], []
    for code in ctx.retrieval_codes() :
        values = [v for v in (reconstructed_ms(r) for r in ctx.data.results_of(code)) if v is not None]
        if (not values) :
            continue
        rows.append([ctx.name(code), str(len(values)), f"{statistics.mean(values):.0f}", f"{np.percentile(values, 95):.0f}"])
        records.append({"configuration" : ctx.name(code), "n" : len(values), "mean_ms" : statistics.mean(values), "p95_ms" : float(np.percentile(values, 95))})
    tables = []
    if (rows) :
        tables.append(Table("T12a", "T12a_latency_reconstructed", "Query latency per configuration, RECONSTRUCTED: the sum of the included encoders' stored search and rerank times plus fusion.",
                            ["Configuration", "Queries", "Mean (ms)", "p95 (ms)"], rows, records = records, align = "lrrr", small = True,
                            notes = ["Each encoder's time is the one measured when it was first computed for that text on the suite host, with the thread limit the suite was started with and whatever load the host had. The wall-clock time of an arm in the database is not its cost, because later arms reuse earlier searches. Compare ratios between rows, not absolute values with the live container.",
                                     "Encoder time is text encoding plus the FAISS scan (search) and the neighbour scoring (rerank); the two cannot be split further from the stored data."]))
    live = ctx.facts["live_latency_s"]
    tables.append(Table("T12b", "T12b_latency_live", "Query latency in the live container (one query, through the live endpoint). Supplied by the team, not measured by this analysis.", ["Setting", "Seconds"],
                        [[k, f"{v:.2f}"] for k, v in live.items()], align = "lr", records = [{"setting" : k, "seconds" : v} for k, v in live.items()],
                        notes = [ctx.facts["hardware"]]))
    if (ctx.features is not None) :
        rows = [[f["name"], f"{f['bytes'] / 1e9:.2f}"] for f in ctx.features.index_files if f["name"].endswith((".index", ".json", ".gz"))]
        keyframes = sampling.total_keyframes(ctx.features)
        tables.append(Table("T12c", "T12c_index_size", "Index files and keyframe budget.", ["Item", "Size (GB) or count"],
                            [*rows, ["Keyframes as sampled (duration-adaptive)", f"{keyframes['adaptive']:,}"], [f"Keyframes if every shot were capped at {sampling.CAP}", f"{keyframes['capped']:,}"]],
                            align = "lr", notes = ["The capped count is a size comparison from the shot table, not a measurement of an index built that way."]))
    return tables


# ─── T14, T15 keyframe sampling ────────────────────────────────────────────

def t14_sampling(ctx : Ctx) -> list[Table] :
    if (ctx.features is None) :
        ctx.skip("T14/T15 keyframe sampling", "no --features folder")
        return []
    check = sampling.budget_check(ctx.features)
    if (not check) :
        ctx.skip("T14 keyframe sampling", "shots.csv is empty")
        return []
    rows, records = [], []
    for key, label in (("all", "all shots"), ("excluding_last_shot_of_each_video", "without each video's last shot"), ("L", "L"), ("M", "M"), ("N", "N"), ("S", "S")) :
        b = check.get(key)
        if (not b or not b.get("shots")) :
            continue
        rows.append([label, f"{b['shots']:,}", f"{b['mean']:.2f}", f"{b['median']:.0f}", f"{b['p5']:.0f} / {b['p95']:.0f}", f"{b['max']:.0f}", pct(b["capped_share"]), pct(b["match_share"]), pct(b["within_one_share"]), f"{b['mean_signed_deviation']:+.2f}"])
        records.append({"slice" : label, **b})
    tables = [Table("T14a", "T14a_keyframe_budget", "Keyframes per shot against the duration rule n(T) = min(40, 2 + ceil(max(0, T - 1.67) / 2)).",
                    ["Slice", "Shots", "Mean", "Median", "p5 / p95", "Max", "At the cap of 40", "Equals n(T)", "Within 1 of n(T)", "Mean (observed - n(T))"], rows, small = True, records = records, align = "lrrrrrrrrr",
                    notes = [f"T is estimated: the first keyframe of the next shot minus this shot's first keyframe, over the frame rate; the true shot boundaries are not stored. Spearman correlation between estimated duration and keyframe count: {check['spearman_duration_keyframes']:.2f}."])]
    rows = [[f"{b['from_s']:g} to {'inf' if b['to_s'] == float('inf') else format(b['to_s'], 'g')}", f"{b['shots']:,}", f"{b['observed_mean']:.2f}", f"{b['eq1_mean']:.2f}"] for b in check["duration_bins"]]
    tables.append(Table("T14b", "T14b_keyframes_by_duration", "Mean keyframes per shot by estimated shot duration (seconds), observed against the rule.", ["Duration (s)", "Shots", "Observed mean", "n(T) mean"], rows, align = "lrrr",
                        records = [{**b} for b in check["duration_bins"]]))

    base = ctx.data.results_of(ctx.base)
    coverage = sampling.interval_coverage(base, ctx.features)
    rows, records = [], []
    for b in ("A", "B") :
        for prefix in ("all", "L", "M", "N", "S") :
            picked = [c for c in coverage if c["bench"] == b and (prefix == "all" or c["prefix"] == prefix)]
            if (not picked) :
                continue
            adaptive, capped = sum(c["adaptive_has_keyframe"] for c in picked), sum(c["capped_has_keyframe"] for c in picked)
            rows.append([b, prefix, str(len(picked)), f"{adaptive} ({pct(adaptive / len(picked))})", f"{capped} ({pct(capped / len(picked))})", str(adaptive - capped)])
            records.append({"bench" : b, "prefix" : prefix, "n" : len(picked), "adaptive" : adaptive, "capped" : capped, "lost" : adaptive - capped})
    retrieval = sampling.capped_retrieval(base, ctx.features)
    tables.append(Table("T15a", "T15a_capped_interval_coverage", "Capped-at-four simulation: KIS and QA queries whose valid interval still contains a keyframe.", ["Bench", "Prefix", "Queries", "Adaptive sampling", f"Capped at {sampling.CAP}", "Lost"], rows, records = records, align = "llrrrr",
                        notes = ["Exact for the reference videos (their keyframes are in frames_ref.csv). It counts keyframes, not retrieval."]))
    cap, adp = retrieval["capped"], retrieval["adaptive"]
    tables.append(Table("T15b", "T15b_capped_retrieval", "APPROXIMATION by post-filtering the stored baseline top-100: frames a capped index would not contain are dropped and the video ranks recomputed.",
                        ["Sampling", "Hit@1", "R@5", "R@10", "MRR"], [["adaptive (stored)", pct(adp["hit_at_1"]), pct(adp["r_at_5"]), pct(adp["r_at_10"]), num(adp["mrr"])], [f"capped at {sampling.CAP} (approximation)", pct(cap["hit_at_1"]), pct(cap["r_at_5"]), pct(cap["r_at_10"]), num(cap["mrr"])]],
                        align = "lrrrr", records = [{"sampling" : "adaptive", **adp}, {"sampling" : "capped_approximation", **cap}],
                        notes = ["Approximation by post-filtering the stored top-100: it cannot add frames that would enter the list and ignores changed neighbour scores, so it is a rough indication and not an ablation.",
                                 f"{pct(retrieval['frames_dropped_share'])}% of the stored frames would be dropped. The in-shot position of frames outside the reference videos is estimated from the shot table; on the reference videos, where it is known exactly, the estimate equals the true position for {pct(retrieval['position_estimate_agreement'])}% of frames."]))
    return tables
