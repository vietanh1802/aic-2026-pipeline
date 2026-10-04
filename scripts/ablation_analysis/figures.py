# scripts/ablation_analysis/figures.py
"""Figures F1 to F8 for the paper: vector PDF plus 300 dpi PNG, 11.7 cm wide (LNCS text width), text at
least 8 pt at final size, colour-blind safe palette (Okabe and Ito) and distinguishable in greyscale
through markers and hatches. A SYNTHETIC or SMOKE run gets a red title and a diagonal watermark."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LogNorm  # noqa: E402

from ablation_analysis import errors as E  # noqa: E402
from ablation_analysis import metrics as M  # noqa: E402
from ablation_analysis.context import Ctx  # noqa: E402
from ablation_analysis.tables_more import MODEL_LABEL, reconstructed_ms  # noqa: E402

WIDTH_IN = 11.7 / 2.54
PALETTE = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#000000", "#999999"]
MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*"]
HATCHES = ["", "//", "..", "xx", "\\\\", "++", "oo", "--"]
plt.rcParams.update({"font.size" : 8, "axes.titlesize" : 8, "axes.labelsize" : 8, "legend.fontsize" : 8, "xtick.labelsize" : 8, "ytick.labelsize" : 8,
                     "pdf.fonttype" : 42, "axes.spines.top" : False, "axes.spines.right" : False, "figure.constrained_layout.use" : True})


def _finish(fig, ctx : Ctx, name : str, folder : Path, title : str = "") -> list[str] :
    folder.mkdir(parents = True, exist_ok = True)
    if (ctx.stamp) :
        fig.suptitle(f"{ctx.stamp}: not results", color = "#cc0000", fontsize = 9, fontweight = "bold")
        fig.text(0.5, 0.5, ctx.stamp, color = "#cc0000", alpha = 0.18, fontsize = 28, rotation = 30, ha = "center", va = "center", fontweight = "bold")
    fig.savefig(folder / f"{name}.pdf", bbox_inches = "tight")
    fig.savefig(folder / f"{name}.png", dpi = 300, bbox_inches = "tight")
    plt.close(fig)
    return [f"{name}.pdf", f"{name}.png"]


def _style(i : int) -> dict[str, Any] :
    return {"color" : PALETTE[i % len(PALETTE)], "marker" : MARKERS[i % len(MARKERS)]}


def f1_recall_curves(ctx : Ctx, folder : Path) -> list[str] :
    groups = {
        "Encoders" : [c for c in [ctx.base, *[ctx.data.code_for(f"single:{m}") for m in ("beit3", "clip", "siglip2")]] if c],
        "Rerank" : [c for c in [ctx.base, ctx.data.code_for("all:off"), ctx.data.code_for("all:after_fusion")] if c],
    }
    fig, axes = plt.subplots(2, 2, figsize = (WIDTH_IN, 4.6), sharey = True)
    ks = np.arange(1, 101)
    for col, (group, codes) in enumerate(groups.items()) :
        for row, b in enumerate(("A", "B")) :
            ax = axes[row][col]
            for i, code in enumerate(codes) :
                results = ctx.data.results_of(code, b)
                if (not results) :
                    continue
                ranks = np.array([r.rank if r.rank is not None else 10 ** 6 for r in results])
                ax.plot(ks, [(ranks <= k).mean() for k in ks], label = ctx.name(code).split(" ", 1)[0] + " " + ctx.name(code).split(" ", 1)[1][ : 22], linewidth = 1.2, **_style(i), markevery = 12, markersize = 3)
            ax.set_xscale("log")
            ax.set_xlabel("k (videos)")
            ax.set_title(f"{group}, benchmark {b}")
            if (col == 0) :
                ax.set_ylabel("R@k")
            ax.legend(fontsize = 6.5, loc = "lower right", frameon = False)
    return _finish(fig, ctx, "F1_recall_curves", folder)


def f2_main_metrics(ctx : Ctx, folder : Path) -> list[str] :
    codes = ctx.retrieval_codes()
    fig, axes = plt.subplots(1, 2, figsize = (WIDTH_IN, 0.28 * len(codes) + 1.2), sharey = True)
    for ax, b in zip(axes, ("A", "B")) :
        for j, (metric, label) in enumerate((("hit_at_1", "Hit@1"), ("r_at_10", "R@10"))) :
            ys = np.arange(len(codes)) + (j - 0.5) * 0.3
            vals, lows, highs = [], [], []
            for code in codes :
                s = M.summary(ctx.data.results_of(code, b))
                vals.append(s[metric])
                lows.append(s[metric] - s[f"{metric}_ci"][0])
                highs.append(s[f"{metric}_ci"][1] - s[metric])
            ax.errorbar(vals, ys, xerr = [lows, highs], fmt = MARKERS[j], color = PALETTE[j], label = label, capsize = 1.5, markersize = 3.5, linewidth = 0.8)
        ax.set_title(f"Benchmark {b}")
        ax.set_xlim(0, 1)
        ax.set_xlabel("proportion (95% Wilson)")
        ax.set_yticks(range(len(codes)))
        ax.set_yticklabels([c for c in codes])
        ax.invert_yaxis()
        ax.grid(axis = "x", linewidth = 0.3)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc = "outside lower center", ncol = 2, frameon = False)
    return _finish(fig, ctx, "F2_main_metrics", folder)


def f3_rerank_shift(ctx : Ctx, folder : Path) -> list[str] | None :
    off = ctx.data.code_for("all:off")
    if (not off) :
        ctx.skip("F3 rerank shift", "no rerank-off run")
        return None
    fig, ax = plt.subplots(figsize = (WIDTH_IN * 0.8, WIDTH_IN * 0.8))
    cap = 130
    for i, prefix in enumerate(("L", "M", "N", "S")) :
        pairs = [(a, b) for a, b in M.aligned(ctx.data.results_of(off), ctx.data.results_of(ctx.base)) if a.prefix == prefix]
        if (not pairs) :
            continue
        rng = np.random.default_rng(i)
        x = np.array([a.rank if a.rank is not None else cap for a, _b in pairs]) * np.exp(rng.normal(0, 0.03, len(pairs)))
        y = np.array([b.rank if b.rank is not None else cap for _a, b in pairs]) * np.exp(rng.normal(0, 0.03, len(pairs)))
        ax.scatter(x, y, s = 14, label = f"{prefix} (n = {len(pairs)})", alpha = 0.8, **{"color" : PALETTE[i], "marker" : MARKERS[i]})
    ax.plot([1, cap], [1, cap], color = "#666666", linewidth = 0.8)
    ax.axvline(110, color = "#aaaaaa", linewidth = 0.5)
    ax.axhline(110, color = "#aaaaaa", linewidth = 0.5)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("reference rank, rerank off (right of the line: not returned)")
    ax.set_ylabel("reference rank, rerank on")
    ax.set_title("Below the diagonal: rerank moves the video up")
    ax.legend(frameon = False)
    return _finish(fig, ctx, "F3_rerank_shift", folder)


def f4_overlap(ctx : Ctx, folder : Path) -> list[str] | None :
    models = ("beit3", "clip", "siglip2")
    codes = {m : ctx.data.code_for(f"single:{m}") for m in models}
    if (not all(codes.values())) :
        ctx.skip("F4 overlap", "single-encoder runs missing")
        return None
    uids = [r.uid for b in ("A", "B") for r in ctx.data.results_of(ctx.base, b)]
    fig, axes = plt.subplots(2, 1, figsize = (WIDTH_IN, 5.0))
    for ax, k in zip(axes, (1, 10)) :
        counts : dict[tuple[bool, bool, bool], int] = {}
        gain = loss = 0
        for u in uids :
            state = tuple(bool(ctx.data.by_code[codes[m]].get(u) and ctx.data.by_code[codes[m]][u].hit(k)) for m in models)
            counts[state] = counts.get(state, 0) + 1
            fusion = ctx.data.by_code[ctx.base][u].hit(k)
            gain += fusion and not any(state)
            loss += (not fusion) and any(state)
        combos = sorted((c for c in counts if any(c)), key = lambda c : -counts[c])
        ax.bar(range(len(combos)), [counts[c] for c in combos], color = PALETTE[0], hatch = "//", edgecolor = "white")
        for x, c in enumerate(combos) :
            ax.text(x, counts[c], str(counts[c]), ha = "center", va = "bottom", fontsize = 7)
        ax.set_xticks([])
        ax.set_ylabel(f"queries hit at k = {k}")
        ax.set_title(f"Hits at k = {k}: fusion gains {gain}, loses {loss} (of {len(uids)})")
        top = max(counts[c] for c in combos) if combos else 1
        ax.set_ylim(-0.38 * top, top * 1.15)
        ax.set_yticks([t for t in ax.get_yticks() if t >= 0])
        for x, c in enumerate(combos) :
            for row, (hit, model) in enumerate(zip(c, models)) :
                ax.scatter(x, -0.08 * top - row * 0.1 * top, s = 14, color = "#000000" if hit else "#dddddd")
        for row, model in enumerate(models) :
            ax.text(-0.6, -0.08 * top - row * 0.1 * top, MODEL_LABEL[model], ha = "right", va = "center", fontsize = 7)
        ax.spines["bottom"].set_visible(False)
    return _finish(fig, ctx, "F4_encoder_overlap", folder)


def f5_by_prefix(ctx : Ctx, folder : Path) -> list[str] :
    codes = [c for c in [ctx.base, *[ctx.data.code_for(f"single:{m}") for m in ("beit3", "clip", "siglip2")]] if c]
    fig, axes = plt.subplots(1, 2, figsize = (WIDTH_IN, 2.6), sharey = True)
    for ax, (b, metric, label) in zip(axes, (("B", "hit_at_1", "Hit@1"), ("B", "r_at_10", "R@10"))) :
        prefixes = [p for p in ("L", "M", "N", "S") if ctx.data.results_of(ctx.base, b, prefix = p)]
        width = 0.8 / max(1, len(codes))
        for i, code in enumerate(codes) :
            vals = [M.summary(ctx.data.results_of(code, b, prefix = p), with_ci = False)[metric] for p in prefixes]
            ax.bar(np.arange(len(prefixes)) + i * width, vals, width, label = ctx.name(code).split(" ", 1)[1][ : 18], color = PALETTE[i], hatch = HATCHES[i], edgecolor = "white")
        ax.set_xticks(np.arange(len(prefixes)) + 0.4 - width / 2)
        ax.set_xticklabels([f"{p}\nn = {len(ctx.data.results_of(ctx.base, b, prefix = p))}" for p in prefixes])
        ax.set_title(f"{label}, benchmark {b} (A is all L)")
        ax.set_ylim(0, 1)
    axes[0].set_ylabel("proportion")
    axes[0].legend(fontsize = 6.5, frameon = False, loc = "upper right")
    return _finish(fig, ctx, "F5_by_prefix", folder)


def f6_rank_heatmap(ctx : Ctx, folder : Path) -> list[str] :
    codes = ctx.retrieval_codes()
    uids = [r.uid for b in ("A", "B") for r in ctx.data.results_of(ctx.base, b)]
    uids.sort(key = lambda u : ctx.data.by_code[ctx.base][u].rank_or_miss)
    grid = np.array([[ (ctx.data.by_code[c].get(u).rank_or_miss if ctx.data.by_code[c].get(u) else np.nan) for c in codes] for u in uids], dtype = float)
    fig, ax = plt.subplots(figsize = (WIDTH_IN, 0.06 * len(uids) + 1.0))
    cmap = plt.get_cmap("viridis_r").copy()
    cmap.set_bad("#bbbbbb")
    shown = np.ma.masked_invalid(np.where(grid >= 101, np.nan, grid))
    image = ax.imshow(shown, aspect = "auto", cmap = cmap, norm = LogNorm(vmin = 1, vmax = 100), interpolation = "nearest")
    ax.set_xticks(range(len(codes)))
    ax.set_xticklabels(codes, rotation = 90)
    ax.set_yticks([])
    ax.set_ylabel(f"{len(uids)} queries, sorted by baseline rank")
    fig.colorbar(image, ax = ax, label = "reference rank (grey: not returned)", fraction = 0.04, pad = 0.02)
    return _finish(fig, ctx, "F6_rank_heatmap", folder)


def f7_errors(ctx : Ctx, folder : Path) -> list[str] :
    codes = [c for c in [ctx.base, *[ctx.data.code_for(f"single:{m}") for m in ("beit3", "clip", "siglip2")], ctx.data.code_for("all:off"), ctx.data.code_for("plain_text"), ctx.data.code_for("all:after_fusion")] if c]
    t01 = ctx.data.code_for("trake_n")
    fig, axes = plt.subplots(1 if not t01 else 2, 2, figsize = (WIDTH_IN, 2.8 if not t01 else 5.2), squeeze = False)
    for ax, b in zip(axes[0], ("A", "B")) :
        bottoms = np.zeros(len(codes))
        for i, bucket in enumerate(E.RANK_BUCKETS) :
            vals = np.array([sum(1 for r in ctx.data.results_of(c, b) if E.rank_bucket(r.rank) == bucket) / max(1, len(ctx.data.results_of(c, b))) for c in codes])
            ax.bar(range(len(codes)), vals, bottom = bottoms, color = PALETTE[i], hatch = HATCHES[i], edgecolor = "white", label = bucket)
            bottoms += vals
        ax.set_xticks(range(len(codes)))
        ax.set_xticklabels(codes, rotation = 90)
        ax.set_title(f"Reference rank, benchmark {b}")
        ax.set_ylim(0, 1)
    axes[0][0].set_ylabel("share of queries")
    axes[0][1].legend(fontsize = 6.5, frameon = False, bbox_to_anchor = (1.0, 1.0), loc = "upper left")
    if (t01) :
        results = ctx.data.results_of(t01)
        ax = axes[1][0]
        event_rows = [((r.extra.get("trake") or {}).get("events") or {}).get("rows") or [] for r in results]
        width = max([len(rows) for rows in event_rows] + [1])
        grid = np.full((len(results), width), np.nan)
        for i, r in enumerate(results) :
            for j, e in enumerate(event_rows[i]) :
                grid[i, j] = 1.0 if e["correct"] else 0.0
        ax.imshow(np.ma.masked_invalid(grid), cmap = plt.get_cmap("RdYlGn"), vmin = 0, vmax = 1, aspect = "auto")
        ax.set_yticks(range(len(results)))
        ax.set_yticklabels([r.key for r in results], fontsize = 6.5)
        ax.set_xticks(range(width))
        ax.set_xticklabels([f"E{j + 1}" for j in range(width)])
        ax.set_title("TRAKE-N events within 5 s (green: yes)")
        stages = {}
        for r in results :
            stages[E.trake_stage(r)] = stages.get(E.trake_stage(r), 0) + 1
        ax2 = axes[1][1]
        ax2.barh(range(len(stages)), list(stages.values()), color = PALETTE[0])
        ax2.set_yticks(range(len(stages)))
        ax2.set_yticklabels([s[ : 32] for s in stages], fontsize = 6.5)
        ax2.set_title("TRAKE-N stage reached")
        ax2.set_xlabel("queries")
    return _finish(fig, ctx, "F7_error_taxonomy", folder)


def f8_efficiency(ctx : Ctx, folder : Path) -> list[str] | None :
    points = []
    for code in ctx.retrieval_codes() :
        values = [v for v in (reconstructed_ms(r) for r in ctx.data.results_of(code)) if v is not None]
        if (values) :
            points.append((code, float(np.mean(values))))
    if (not points) :
        ctx.skip("F8 efficiency", "no model_timings stored")
        return None
    fig, ax = plt.subplots(figsize = (WIDTH_IN, 3.0))
    for b, marker, color in (("A", "o", PALETTE[0]), ("B", "s", PALETTE[1])) :
        xs = [ms for _c, ms in points]
        ys = [M.summary(ctx.data.results_of(c, b), with_ci = False)["mrr"] for c, _ms in points]
        ax.scatter(xs, ys, marker = marker, color = color, s = 18, label = f"benchmark {b}")
        if (b == "A") :
            for (code, _ms), x, y in zip(points, xs, ys) :
                ax.annotate(code, (x, y), fontsize = 6.5, xytext = (3, 2), textcoords = "offset points")
    ax.set_xlabel("reconstructed mean latency per query (ms, suite host)")
    ax.set_ylabel("MRR")
    ax.legend(frameon = False)
    return _finish(fig, ctx, "F8_efficiency", folder)


BUILDERS = (f1_recall_curves, f2_main_metrics, f3_rerank_shift, f4_overlap, f5_by_prefix, f6_rank_heatmap, f7_errors, f8_efficiency)


def build_all(ctx : Ctx, folder : Path) -> list[str] :
    written : list[str] = []
    for builder in BUILDERS :
        result = builder(ctx, folder)
        if (result) :
            written += result
    return written
