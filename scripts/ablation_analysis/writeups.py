# scripts/ablation_analysis/writeups.py
"""The written aids: protocol.md, claims_check.md, limitations_candidates.md, numbers_to_fix_in_paper.md,
README.md. Plain prose, every number computed from the run folder, no causal wording, and the word
"significant" never appears without an adjusted p next to it. A SYNTHETIC or SMOKE run says so at the top
of every file."""
from __future__ import annotations

import statistics
from typing import Any

import numpy as np

from ablation_analysis import metrics as M
from ablation_analysis import sampling, stats
from ablation_analysis.context import Ctx

VERDICTS = ("supported", "not supported", "inconclusive because n is small", "not testable with this data")


def _banner(ctx : Ctx) -> str :
    return f"> **{ctx.stamp}: the numbers below are not results.** Reasons: {'; '.join(ctx.data.mode_reasons)}.\n\n" if ctx.stamp else ""


def _p(p : float) -> str :
    """'< 0.001' or '= 0.017', to follow the letter p."""
    return "< 0.001" if p < 0.001 else f"= {p:.3f}"


def _decide(rows : list[dict[str, Any]], better_when_delta_negative : bool) -> str :
    """supported when the first configuration is better on some metric with Holm p < 0.05 in some benchmark and
    worse on none; not supported when the other one is better with Holm p < 0.05; else inconclusive.
    rows are compare(base = first configuration, other = second configuration) outputs, so delta is second minus first."""
    first_better = second_better = False
    for c in rows :
        for metric in ("hit_at_1", "r_at_5", "r_at_10") :
            if (c[metric]["p_holm"] < 0.05) :
                if ((c[metric]["delta"] < 0) == better_when_delta_negative) :
                    first_better = True
                else :
                    second_better = True
    if (second_better) :
        return "not supported"
    return "supported" if first_better else "inconclusive"


def _comparison_lines(ctx : Ctx, other : str, label : str) -> tuple[list[dict[str, Any]], list[str]] :
    rows, lines = [], []
    for b in ("A", "B") :
        fam = M.family(ctx.data, b, ctx.base, ctx.retrieval_codes()).get(other)
        if (not fam) :
            continue
        rows.append(fam)
        base, oth = M.summary(ctx.data.results_of(ctx.base, b), with_ci = False), M.summary(ctx.data.results_of(other, b), with_ci = False)
        parts = []
        for metric, name in (("hit_at_1", "Hit@1"), ("r_at_5", "R@5"), ("r_at_10", "R@10")) :
            c = fam[metric]
            parts.append(f"{name} {100 * base[metric]:.1f} vs {100 * oth[metric]:.1f} (gained {c['gained']}, lost {c['lost']}, Holm-adjusted p {_p(c['p_holm'])})")
        m = fam["mrr"]
        lines.append(f"- Benchmark {b} (n = {base['n']}), {ctx.name(ctx.base)} vs {label}: " + "; ".join(parts) + f"; MRR {base['mrr']:.3f} vs {oth['mrr']:.3f}, difference {m['delta']:+.3f} (95% bootstrap interval {m['ci'][0]:+.3f} to {m['ci'][1]:+.3f}) for {label} minus baseline.")
    return rows, lines


def claims_check(ctx : Ctx) -> str :
    out = ["# Claims check", "", _banner(ctx), "Verdicts use only the run folder. A comparison counts as supported only when a Holm-adjusted p is below 0.05 in the stated direction; with 86 and 28 queries most differences will not reach that, and the text says so. No claim is tested for a cause, only for a difference in these queries.", ""]
    adjust_note = "Holm adjustment is over every configuration and every metric (Hit@1, R@5, R@10) compared with the baseline in that benchmark."

    # C1
    out += ["## C1 Duration-adaptive keyframe sampling", "", "Paper: n(T) = min(40, 2 + ceil(max(0, T - 1.67) / 2)) gives longer shots more coverage without unbounded growth.", ""]
    if (ctx.features is None) :
        out += ["**Verdict: not testable with this data** (no corpus features folder; run scripts/dump_corpus_features.py).", ""]
    else :
        check = sampling.budget_check(ctx.features)
        a = check["all"]
        rho = check["spearman_duration_keyframes"]
        verdict = "supported" if (rho == rho and rho > 0.5 and a["max"] <= 40) else "inconclusive because n is small" if a["shots"] < 100 else "not supported"
        out += [f"**Verdict: {verdict}**, for the statistics only. There is no ablation arm, so the effect of the rule on retrieval is not tested.", "",
                f"- {a['shots']:,} shots: mean {a['mean']:.2f} keyframes per shot, median {a['median']:.0f}, p5 {a['p5']:.0f}, p95 {a['p95']:.0f}, maximum {a['max']:.0f}; {100 * a['capped_share']:.1f}% of shots are at the cap of 40.",
                f"- Spearman correlation between estimated shot duration and keyframe count: {rho:.2f}. Keyframes equal n(T) for {100 * a['match_share']:.1f}% of shots and are within 1 of it for {100 * a['within_one_share']:.1f}%, with T estimated (the true shot boundaries are not stored).", ""]

    # C2
    c13 = ctx.data.code_for("all:after_fusion")
    out += ["## C2 Separate search and neighbour rerank per encoder, combined at the final ranking", "", "Paper: each encoder is searched and reranked separately and scores are combined only at the end (Eq. 2); agreement across encoders raises a frame's score. Test: baseline against post-fusion rerank, our implementation.", ""]
    if (not c13) :
        out += ["**Verdict: not testable with this data** (no post-fusion run).", ""]
    else :
        rows, lines = _comparison_lines(ctx, c13, "post-fusion rerank")
        out += [f"**Verdict: {_decide(rows, better_when_delta_negative = True)}**", "", *lines, "", adjust_note,
                "The post-fusion variant is our re-created implementation (candidate pool from the fused raw lists, neighbour score under every encoder, fused again), not the earlier code, so this compares the shipped order with one plausible alternative order.", ""]

    # C3
    off = ctx.data.code_for("all:off")
    out += ["## C3 Neighbouring-frame reranking helps", "", "Test: baseline against rerank off (all three encoders), and each single encoder with rerank on against off.", ""]
    if (not off) :
        out += ["**Verdict: not testable with this data** (no rerank-off run).", ""]
    else :
        rows, lines = _comparison_lines(ctx, off, "rerank off")
        out += [f"**Verdict: {_decide(rows, better_when_delta_negative = True)}**", "", *lines, "", adjust_note, ""]
        for m in ("beit3", "clip", "siglip2") :
            on, of = ctx.data.code_for(f"single:{m}"), ctx.data.code_for(f"single:{m}:off")
            if (on and of) :
                for b in ("A", "B") :
                    c = M.compare(ctx.data.results_of(of, b), ctx.data.results_of(on, b))
                    out.append(f"- {m} alone, benchmark {b}: rerank on minus off, Hit@1 {100 * c['hit_at_1']['delta']:+.1f} points (gained {c['hit_at_1']['gained']}, lost {c['hit_at_1']['lost']}, raw p {_p(c['hit_at_1']['p'])}), R@10 {100 * c['r_at_10']['delta']:+.1f} points (raw p {_p(c['r_at_10']['p'])}); raw p values, not adjusted.")
        out += ["", "Neighbour definition: for L videos (all of benchmark A) neighbors_clip is empty for 263,895 of 360,531 frames and rerank uses the fallback of 2 keyframes either side including the frame itself; M, N and S use stored links. The L versus M, N, S rows of table T4 therefore mix the data with this difference.", ""]

    # C4
    singles = {m : ctx.data.code_for(f"single:{m}") for m in ("beit3", "clip", "siglip2")}
    out += ["## C4 The three encoders are complementary; SigLIP2 helps queries that hinge on a small attribute", "", ""]
    if (not all(singles.values())) :
        out += ["**Verdict: not testable with this data** (single-encoder runs missing).", ""]
    else :
        uids = [r.uid for b in ("A", "B") for r in ctx.data.results_of(ctx.base, b)]
        n = len(uids)
        hit = {m : np.array([bool(ctx.data.by_code[c].get(u) and ctx.data.by_code[c][u].hit(10)) for u in uids]) for m, c in singles.items()}
        union = np.any(list(hit.values()), axis = 0)
        best = max(int(h.sum()) for h in hit.values())
        excl = {m : int((hit[m] & ~np.any([hit[o] for o in hit if o != m], axis = 0)).sum()) for m in hit}
        fusion = np.array([ctx.data.by_code[ctx.base][u].hit(10) for u in uids])
        gain, loss = int((fusion & ~union).sum()), int((~fusion & union).sum())
        complementary = (int(union.sum()) - best) >= max(3, round(0.05 * n)) and all(v >= 1 for v in excl.values())
        out += [f"Complementarity (R@10 over {n} queries of A and B): **{'supported' if complementary else 'inconclusive because n is small'}**. Union of the three single encoders {int(union.sum())} hits against {best} for the best single encoder; exclusive hits BEiT-3 {excl['beit3']}, OpenCLIP {excl['clip']}, SigLIP2 {excl['siglip2']}; fusion gains {gain} queries no single encoder hits and loses {loss} that some single encoder hits. Rule used: supported when the union exceeds the best single encoder by at least 5% of the queries (and at least 3) and every encoder has an exclusive hit.", ""]
        labelled = [r for r in (ctx.labels or []) if (r.get("small_detail_query") or "").strip().lower() in ("yes", "no")]
        if (not labelled) :
            out += ["SigLIP2 and small details: **not testable with this data** until the labelling sheet has small_detail_query filled (scripts/aggregate_error_labels.py then reports Hit@1 and R@10 of each single encoder on yes against no).", ""]
        else :
            yes = {(r["dataset"], r["query_key"]) for r in labelled if r["small_detail_query"].strip().lower() == "yes"}
            no = {(r["dataset"], r["query_key"]) for r in labelled if r["small_detail_query"].strip().lower() == "no"}
            out += [f"SigLIP2 and small details (descriptive; labelled rows are only queries the baseline missed at rank 1, {len(yes)} yes and {len(no)} no): "]
            for m, c in singles.items() :
                for name, group in (("yes", yes), ("no", no)) :
                    results = [ctx.data.by_code[c][u] for u in group if u in ctx.data.by_code[c]]
                    if (results) :
                        out.append(f"- {m}, small detail {name}: n = {len(results)}, R@10 {100 * sum(1 for r in results if r.hit(10)) / len(results):.1f}%.")
            out += ["", "**Verdict for the SigLIP2 part: inconclusive because n is small.** The labelled set is the baseline's misses only, so it cannot compare queries that were easy for every encoder.", ""]

    # C5
    t01, t02 = ctx.data.code_for("trake_n"), ctx.data.code_for("trake_plain")
    out += ["## C5 TRAKE-N beats scoring the whole description once", "", ""]
    if (not t01 or not t02) :
        out += ["**Verdict: not testable with this data** (run --preset trake).", ""]
    else :
        a, b = ctx.data.results_of(t02), ctx.data.results_of(t01)
        c = M.compare(a, b)
        sa, sb = M.summary(a, with_ci = False), M.summary(b, with_ci = False)
        events = [r.extra["trake"]["events"] for r in b if (r.extra.get("trake") or {}).get("events")]
        ev = f"{sum(e['correct'] for e in events)} of {sum(e['total'] for e in events)} events within 5 s" if events else "events not scored"
        out += [f"**Verdict: inconclusive because n is small.** {sa['n']} queries. Hit@1 plain {100 * sa['hit_at_1']:.1f} vs TRAKE-N {100 * sb['hit_at_1']:.1f}; R@10 {100 * sa['r_at_10']:.1f} vs {100 * sb['r_at_10']:.1f}; MRR {sa['mrr']:.3f} vs {sb['mrr']:.3f}. Paired Hit@1: TRAKE-N gained {c['hit_at_1']['gained']}, lost {c['hit_at_1']['lost']}, exact McNemar p {_p(c['hit_at_1']['p'])} (not adjusted, a single descriptive comparison). TRAKE-N chose frames for {ev}. With eight queries only descriptive statements are supported.", ""]

    # C6
    out += ["## C6 OCR and ASR provide evidence that visual ranking misses", "", ""]
    code = next((c for c in ctx.retrieval_codes() if any(r.extra.get("text_signal") for r in ctx.data.results_of(c))), None)
    if (code is None) :
        out += ["**Verdict: inconclusive because n is small**: no run carries annotation blocks (no cues labelled).", ""]
    else :
        from ablation_analysis.tables_more import _text_metrics
        lines = []
        for b in ("A", "B") :
            for kind in ("confirmed", "legacy_leaky") :
                blocks = [(r.extra["text_signal"].get(kind) or {}).get("both") for r in ctx.data.results_of(code, b) if r.extra.get("text_signal")]
                blocks = [x for x in blocks if x]
                if (blocks) :
                    m = _text_metrics(blocks)
                    lines.append(f"- Benchmark {b}, cues {kind}{' (upper bound)' if kind == 'legacy_leaky' else ''}, OCR and ASR together, queries with a cue (n = {m['n']}): the reference video is annotated in {100 * m['flag_rate_ref']:.1f}% of them; rescue potential (annotated but not ranked first) {100 * m['rescue_potential']:.1f}% of them; precision of the annotation {pct_or_na(m['precision'])}.")
        out += ["**Verdict: not testable with this data as a ranking effect.** OCR and ASR only annotate results and never change a ranking, so Hit@k, R@k and MRR cannot move. At annotation level:", "", *(lines or ["- no query has a cue in this run."]), "",
                "Cues for rounds 1 to 3 are the seeds' old filter terms, audited against the real engines (an upper bound). Cues for final-v1 exist only if the reviewer confirmed them. OCR and ASR do not exist for N and S videos and are partial for M.", ""]

    # C7
    live = ctx.facts["live_latency_s"]
    warm, cold = live.get("all three encoders, rerank on (warm)"), live.get("first call after a restart (cold)")
    values = {m : [v for v in (r.extra.get("model_timings", {}).get("models", {}).get(m, {}).get("search_ms") for r in ctx.data.results_of(ctx.base)) if v is not None] for m in ("beit3", "clip", "siglip2")}
    out += ["## C7 A backend that reuses loaded models avoids repeated preparation", "", f"**Verdict: supported for the numbers the team measured, which are inputs here and not measured by this analysis:** first call after a restart {cold:.1f} s against {warm:.2f} s warm for all three encoders ({cold / warm:.1f} times). Per encoder, warm: BEiT-3 {live['BEiT-3 alone (warm)']:.2f} s, OpenCLIP {live['OpenCLIP alone (warm)']:.2f} s, SigLIP2 {live['SigLIP2 alone (warm)']:.2f} s. One query each, so no spread is available.", ""]
    if (any(values.values())) :
        out += ["Stored per-encoder search times on the suite host (mean, first computation, ms): " + ", ".join(f"{m} {statistics.mean(v):.0f}" for m, v in values.items() if v) + ". These come from a run with its own thread limit and are not comparable with the live container's.", ""]

    # C8
    paper = ctx.facts["paper_draft"]
    loaded = ctx.facts["loaded_index"]
    out += ["## C8 Collection size of 1,480 videos and 323.8 hours", "", f"**Verdict: not supported as written.** The loaded index has {loaded['videos']:,} videos and {loaded['keyframes']:,} keyframes (L {loaded['frames_per_prefix']['L']:,}, M {loaded['frames_per_prefix']['M']:,}, N {loaded['frames_per_prefix']['N']:,}, S {loaded['frames_per_prefix']['S']:,}), measured on the deployment; the draft says {paper['videos']:,} videos.", ""]
    if (ctx.features is not None) :
        hours = sum(v["duration_s"] for v in ctx.features.videos.values()) / 3600
        out += [f"From the features folder: {len(ctx.features.videos):,} videos and {hours:,.1f} hours (last keyframe divided by frame rate, a LOWER bound of the true duration). The draft says {paper['hours']} hours; the lower bound {'is above' if hours > paper['hours'] else 'does not exceed'} it, so the data {'contradict' if hours > paper['hours'] else 'cannot confirm or contradict'} that figure." + (" These are synthetic features." if ctx.features.synthetic else ""), ""]
    else :
        out += [f"Hours: not testable with this data (no features folder); the draft says {paper['hours']}.", ""]

    # C10: the text claim, baseline (Expand) against plain translation
    plain = ctx.data.code_for("plain_text")
    out += ["## C10 (claim number; the arms are C01 and C14) LLM-prepared English search text beats plain translation", "", "Paper Section 3.3: the query is prepared by an LLM (Expand: a cleaned, enriched English search sentence plus a checklist) before it reaches the encoders. Test: baseline (Expand) against plain translation, the same queries searched with the same encoders.", ""]
    if (not plain or ctx.info(ctx.base).config.get("text_policy") != "expand_gemini") :
        out += ["**Verdict: not testable with this data** (the baseline is not Expand, or there is no plain-translation arm; run preset core2).", ""]
    else :
        rows, lines = _comparison_lines(ctx, plain, "plain translation")
        out += [f"**Verdict: {_decide(rows, better_when_delta_negative = True)}**", "", f"Arms compared: {ctx.base} ({ctx.name(ctx.base)}) against {plain} ({ctx.name(plain)}).", "", *lines, "", adjust_note,
                "Plain translations longer than an encoder's context are truncated, which is part of what this arm measures; table T5b splits the queries by whether the text was truncated.", ""]

    # C9
    out += ["## C9 Candidate-region blocks in the player", "", "**Verdict: not testable with this data.** A user-interface feature; none of Hit@k, R@k, MRR or latency measures it.", ""]
    return "\n".join(out) + "\n"


def _text_sentence(ctx : Ctx) -> str :
    """What text the arms searched, from the baseline's own configuration."""
    if (ctx.info(ctx.base).config.get("text_policy") == "expand_gemini") :
        return ("The text of every arm is the English search text prepared by the Expand step (one Gemini call that translates, cleans and enriches the Vietnamese query), "
                "recorded once and replayed, so every arm searches the same text; plain translation (Google Translate) is the text ablation and raw Vietnamese a sanity check.")
    return "The text policy of the baseline is server-side Google Translate to English (translate_gtx), recorded and replayed so every configuration searches the same text."


def pct_or_na(x : float | None) -> str :
    return "n/a" if x is None else f"{100 * x:.1f}%"


def protocol(ctx : Ctx) -> str :
    data = ctx.data
    prov = data.provenance
    ns = {b : len(data.results_of(ctx.base, b)) for b in ("A", "B")}
    prefixes = {b : {p : len(data.results_of(ctx.base, b, prefix = p)) for p in ("L", "M", "N", "S")} for b in ("A", "B")}
    tasks = {b : {t : len(data.results_of(ctx.base, b, task = t)) for t in ("KIS", "QA", "TRAKE")} for b in ("A", "B")}
    def fmt(d : dict[str, int]) -> str :
        return ", ".join(f"{v} {k}" for k, v in d.items() if v)

    commit = prov.get("commit_full") or "unknown"
    lines = ["# Draft of Section 4.1 (evaluation protocol)", "", _banner(ctx),
             "## Datasets and labels", "",
             f"Benchmark A is the three preliminary rounds pooled ({ns['A']} queries: {fmt(tasks['A'])}; reference videos {fmt(prefixes['A'])}). Its labels are the team's own, made by manual review of intervals. Benchmark B is the final round ({ns['B']} queries: {fmt(tasks['B'])}; reference videos {fmt(prefixes['B'])}). Its labels come from the organisers' appeal documents: one timestamp per query, used with a plus or minus 5 second interval. The team filed remark requests on 7 final queries; the repository does not record which, so no label flag exists for them. TRAKE queries have one reference frame per event and no interval.", "",
             "## Metrics", "",
             "All headline metrics are video level and follow backend/app/evaluation/scoring.py. The ranked video list orders videos by where each first appears in the 100 fused frames returned. Hit@1 is the share of queries whose reference video is first; R@k the share within the first k videos (k = 1, 3, 5, 10, 20, 50, 100); MRR the mean of 1 / rank of the reference video, 0 when it is absent from the list. A query that failed counts as a miss. The median rank is taken over the queries where the reference video is returned. Interval level (KIS and QA only) is the official R-Score: a returned frame counts when it is from the reference video and its frame index falls inside a valid interval; the query's score is the mean of R@k for k = 1, 5, 20, 50, 100. TRAKE-N is scored at video level by the combined-score rank of the reference video, and per event by whether the chosen frame is within 5 seconds of the team's reference frame.", "",
             "## Flags", "",
             "Two label flags are kept beside the seeds. vfr_times marks 49 N videos whose keyframe timestamps drift from the container clock, so interval results on them are unreliable. whole_video_interval marks the one query whose valid interval is the whole video. Video-level metrics do not depend on either; tables are also given without the flagged queries.", "",
             "## Configurations", "",
             "Each configuration varies one component of the shipped system and is run on all four datasets: " + "; ".join(ctx.name(c) for c in ctx.retrieval_codes()) + "." + (" TRAKE: " + "; ".join(ctx.name(c) for c in ctx.codes("trake")) + "." if ctx.codes("trake") else "") + " " + _text_sentence(ctx) + " Rerank after fusion is our re-created implementation, not the earlier code.", "",
             "## Statistical methods", "",
             f"Proportions carry Wilson 95% intervals. MRR and the median rank carry percentile bootstrap intervals over queries ({stats.N_BOOT} resamples, seed {stats.SEED}). Comparisons with the baseline are paired on queries: an exact two-sided McNemar test on the queries gained and lost for Hit@1, R@5 and R@10, Holm-adjusted over every configuration and metric compared with the baseline within a benchmark, and a paired bootstrap interval for the MRR difference. One run per configuration; there is no run-to-run variance estimate.", "",
             "## Hardware, software and provenance", "",
             f"Retrieval ran on {ctx.facts['hardware']}. Commit {commit}, version {prov.get('version', 'unknown')}. Run started {prov.get('started_at', 'unknown')}. Per-model search times are taken from the first computation of each encoder for a text and are used only to reconstruct latency; the wall-clock time of a configuration in the database is not its cost because configurations share searches.", ""]
    return "\n".join(lines) + "\n"


def limitations(ctx : Ctx) -> str :
    items = [
        ("Labels for benchmark A are the team's own, made by manual review of intervals.", "reference confidence manual_review_interval in the seeds (T1b)"),
        ("Labels for benchmark B come from the appeal documents with a single timestamp and a plus or minus 5 second interval; remark requests on 7 queries are pending and not flagged.", "seeds/final-v1.json notes; the repository does not record which 7"),
        ("Benchmarks are small (86 and 28 queries): a 95% interval on a proportion is about 10 and 17 points wide on each side at p = 0.5, so most pairwise differences cannot be separated from noise.", "stats.half_width_at_half; every table note"),
        ("Each configuration was run once; there is no estimate of run-to-run variation (the search is deterministic, but the translated text and the label set are single draws).", "run folder: one run per configuration and dataset"),
        ("N videos have variable frame rate, so interval-level results on them (and their seconds) are unreliable; 49 videos are flagged vfr_times.", "seeds/flags/vfr_times.json"),
        ("Neighbour reranking uses different neighbour definitions: for L videos (all of benchmark A) the stored neighbour links are empty for 263,895 of 360,531 frames and the fallback of 2 keyframes either side including the frame itself is used; M, N and S use the stored links.", "preprocess._neighbor_faiss_ids; EC2 measurement 2026-10-04"),
        ("OCR and ASR only annotate results; they never change a ranking, so no ranking benefit is measured. They do not exist for N and S videos and are partial for M. Cues for rounds 1 to 3 are the seeds' old filter terms (audited against the real engines, an upper bound); final-v1 cues exist only once confirmed.", "backend/app/evaluation/cues.py; seeds/cues"),
        ("Post-fusion rerank is a re-created implementation; the earlier code is not in the history.", "backend/app/evaluation/shared_search.py docstring"),
        ("There is no keyframe-sampling arm: the sampling rule is described by corpus statistics only, and the capped-at-four retrieval figure is an approximation by post-filtering the stored top-100.", "T14, T15"),
        ("Latency was measured on CPU only (8 vCPU, no GPU), for single queries in the live container; per-configuration latency is reconstructed from stored first-computation times.", "T12"),
        ("Rankings are taken from the 100 fused frames returned per query, so a reference video outside them counts as not retrieved and the not-retrieved bucket cannot separate rank 101 from rank 1000.", "scoring.py, top_k = 100"),
        (("The Expand text is a single draw from one LLM (Gemini flash-lite, temperature 0) and the plain translation a single draw from a public service; neither was repeated." if ctx.info(ctx.base).config.get("text_policy") == "expand_gemini"
          else "The text translation is a fixed single draw from a public translation service; the Gemini-based expansion arm was not run."), "run folder text cache; preset core2 or core"),
        ("The 8 TRAKE queries and 31 events support only descriptive statements; the shortlist stage of TRAKE-N is rebuilt from the same rule as the production function, not logged by it.", "T7; backend/app/evaluation/trake.py"),
    ]
    lines = ["# Limitation candidates", "", _banner(ctx), "Each statement is supported by the source named after it. Pick those the paper needs.", ""]
    lines += [f"{i + 1}. {text} (Source: {source}.)" for i, (text, source) in enumerate(items)]
    return "\n".join(lines) + "\n"


def numbers_to_fix(ctx : Ctx) -> str :
    paper, loaded = ctx.facts["paper_draft"], ctx.facts["loaded_index"]
    lines = ["# Numbers in the paper draft that the data contradict or refine", "", _banner(ctx),
             "The draft text itself was not available to this analysis; only the figures stated in the task are checked. Add the others by comparing with tables T1a and T14a.", "",
             "| Item | Draft | Measured | Source |", "|---|---|---|---|",
             f"| Videos | {paper['videos']:,} | {loaded['videos']:,} | loaded index on EC2, 2026-10-04 |",
             f"| Keyframes | {paper['keyframes']:,} (also README.md line 18) | {loaded['keyframes']:,} (L {loaded['frames_per_prefix']['L']:,}, M {loaded['frames_per_prefix']['M']:,}, N {loaded['frames_per_prefix']['N']:,}, S {loaded['frames_per_prefix']['S']:,}) | loaded index on EC2, 2026-10-04 |"]
    if (ctx.features is not None) :
        hours = sum(v["duration_s"] for v in ctx.features.videos.values()) / 3600
        lines.append(f"| Hours | {paper['hours']} | at least {hours:,.1f} (lower bound: last keyframe / fps) | features folder{' (SYNTHETIC)' if ctx.features.synthetic else ''} |")
        shots = ctx.features.shots
        if (shots) :
            per = [s["n_keyframes"] for s in shots]
            lines.append(f"| Keyframes per shot | not given | mean {statistics.mean(per):.2f}, median {statistics.median(per):.0f} | shots.csv |")
    else :
        lines.append(f"| Hours | {paper['hours']} | not measured (no features folder) | |")
    lines += ["", "Also check wherever the draft says: ASR is NVIDIA Parakeet, not Whisper (README.md was corrected; docs/KIEN_TRUC_PIPELINE.md still says Whisper large-v3); latency numbers against T12b; the number of videos per prefix against T1a.", ""]
    return "\n".join(lines) + "\n"


def readme(ctx : Ctx, written : dict[str, list[str]]) -> str :
    lines = ["# Analysis of an ablation run", "", _banner(ctx),
             "## Rerun", "",
             "```", "pip install -r scripts/requirements-analysis.txt",
             "python scripts/analyze_ablation.py --run-dir <ablation_out/timestamp> --features <features dir> [--labels error_labeling_sheet_filled.csv] [--images-dir <keyframe images>]", "```", "",
             "The run folder must contain ablation.db (pull it back with tar WITHOUT --exclude=ablation.db, and keep ablation.db-wal and ablation.db-shm if they exist) and, ideally, provenance.json and suite.json. The features folder is written by scripts/dump_corpus_features.py on EC2. A folder with synthetic or smoke markers writes to analysis_SYNTHETIC or analysis_SMOKE and stamps every table, figure and file.", "",
             "## Which file feeds which paper section", "",
             "| Section | Files |", "|---|---|",
             "| 3.1 dataset | tables/T1a_corpus, T1b_benchmarks, T14a, T14b, numbers_to_fix_in_paper.md |",
             "| 4.1 protocol | protocol.md, tables/T1b_benchmarks, limitations_candidates.md |",
             "| 4.2 main results | tables/T2_main_ablation, T2x_extended_A/B, T3_encoder_grid_A/B, T6_task_and_prefix, figures F1, F2, F5, F6 |",
             "| 4.3 component analysis | tables/T4_rerank, T5_text_policy, T5b_text_length and T5c_truncated_vs_not (tokens against each encoder's limit), T5s_sanity (raw Vietnamese, shown once), T7a/T7b_trake, T8a/T8b, T9, T11a/T11b; figures F3, F4, F7 |",
             "| 4.4 efficiency and errors | tables/T10a to T10d, T12a to T12c, T13a to T13c, T15a/T15b; figures F7, F8; qualitative/; error_labeling_sheet.csv |",
             "| claims | claims_check.md |", "",
             "Every table is written as .csv (numbers), .tex (paper) and .md (reading). paper_tables.tex joins T1, T2, T3, T4, T7, T8, T10, T12. A CSV of a stamped run starts with a '#' comment line; read it with comment = '#'.", "",
             "## Written files", ""]
    for kind, files in written.items() :
        lines.append(f"- {kind}: {len(files)} files")
    if (ctx.skipped) :
        lines += ["", "## Skipped (and why)", "", *[f"- {s}" for s in ctx.skipped]]
    return "\n".join(lines) + "\n"
