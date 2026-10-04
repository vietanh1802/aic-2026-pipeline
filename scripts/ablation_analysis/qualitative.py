# scripts/ablation_analysis/qualitative.py
"""About 20 qualitative cases chosen by rule, written as cases.csv, index.md and, when the keyframe images
are available, a self-contained HTML page with relative image paths.

Rules (3 each, 2 for clean hits), a query is used once; ties broken by dataset and query key so the choice
is reproducible: fusion rescues, fusion hurts, rerank gains, rerank loses, hardest, TRAKE failures, clean hits.
"""
from __future__ import annotations

import csv
import html
import os
import shutil
from pathlib import Path
from typing import Any

from ablation_analysis import errors as E
from ablation_analysis.context import Ctx
from ablation_analysis.data import Result

PER_RULE = {"fusion rescues" : 3, "fusion hurts" : 3, "rerank gains" : 3, "rerank loses" : 3, "hardest" : 3, "TRAKE failure" : 3, "clean hit" : 2}


def select_cases(ctx : Ctx) -> list[tuple[str, Result]] :
    data, base = ctx.data, ctx.base
    singles = [c for c in (data.code_for(f"single:{m}") for m in ("beit3", "clip", "siglip2")) if c]
    off = data.code_for("all:off")
    grid = [c for c in ctx.retrieval_codes()]
    queries = sorted(data.results_of(base), key = lambda r : (r.bench, r.dataset, r.key))
    miss = 10 ** 6

    def get(code : str, r : Result) -> Result | None :
        return data.by_code.get(code, {}).get(r.uid)

    def rank(r : Result | None) -> int :
        return r.rank if r is not None and r.rank is not None else miss

    chosen : list[tuple[str, Result]] = []
    used : set[tuple[str, str]] = set()

    def take(rule : str, candidates : list[Result]) -> None :
        for r in candidates :
            if (sum(1 for rl, _x in chosen if rl == rule) >= PER_RULE[rule]) :
                break
            if (r.uid not in used) :
                chosen.append((rule, r))
                used.add(r.uid)

    if (len(singles) == 3) :
        take("fusion rescues", sorted([r for r in queries if r.hit(10) and not any(get(c, r) and get(c, r).hit(10) for c in singles)], key = lambda r : (rank(r), r.uid)))
        hurt = [r for r in queries if any(get(c, r) and get(c, r).hit(10) for c in singles) and not r.hit(10)]
        take("fusion hurts", sorted(hurt, key = lambda r : (-(rank(r) - min(rank(get(c, r)) for c in singles)), r.uid)))
    if (off) :
        take("rerank gains", sorted([r for r in queries if rank(r) < rank(get(off, r))], key = lambda r : (-(rank(get(off, r)) - rank(r)), r.uid)))
        take("rerank loses", sorted([r for r in queries if rank(r) > rank(get(off, r))], key = lambda r : (-(rank(r) - rank(get(off, r))), r.uid)))
    take("hardest", [r for r in queries if all(rank(get(c, r)) > 10 for c in grid)])
    t01 = data.code_for("trake_n")
    if (t01) :
        take("TRAKE failure", [r for r in sorted(data.results_of(t01), key = lambda r : (r.dataset, r.key)) if E.trake_stage(r) != "success"])
    take("clean hit", [r for r in queries if all(rank(get(c, r)) == 1 for c in grid)])
    return chosen


def _reference_frame(ctx : Ctx, r : Result) -> str | None :
    if (ctx.features is None or not ctx.features.frames_ref.get(r.ref_video)) :
        return None
    frames = ctx.features.frames_ref[r.ref_video]
    if (r.intervals) :
        target = sum(s + e for s, e in r.intervals) / (2 * len(r.intervals))
    elif (r.ref_frame_idx is not None) :
        target = r.ref_frame_idx
    else :
        events = (ctx.data.refs.get(r.uid) or {}).get("trake_events") or []
        target = events[0].get("reference_frame_idx") if events and events[0].get("reference_frame_idx") is not None else frames[len(frames) // 2][2]
    return min(frames, key = lambda f : abs(f[2] - target))[0]


def _find_images(images_dir : Path, names : set[str]) -> dict[str, Path] :
    found : dict[str, Path] = {}
    for name in names :
        for candidate in (images_dir / name, images_dir / "images" / name) :
            if (candidate.exists()) :
                found[name] = candidate
                break
    missing = names - set(found)
    if (missing) :
        for root, _dirs, files in os.walk(images_dir) :
            for f in files :
                if (f in missing) :
                    found[f] = Path(root) / f
                    missing.discard(f)
            if (not missing) :
                break
    return found


def write_qualitative(ctx : Ctx, folder : Path) -> dict[str, Any] :
    folder.mkdir(parents = True, exist_ok = True)
    cases = select_cases(ctx)
    codes = ctx.retrieval_codes()
    rows = []
    for rule, r in cases :
        fps = (ctx.features.videos.get(r.ref_video) or {}).get("fps") if ctx.features else None
        interval = "; ".join(f"{s / fps:.1f}-{e / fps:.1f} s" if fps else f"frames {s}-{e}" for s, e in r.intervals)
        top = [(v["video_id"], v["frames"][0]["name"] if v.get("frames") else "") for v in r.ranked[ : 5]]
        row : dict[str, Any] = {
            "rule" : rule, "dataset" : r.dataset, "query_key" : r.key, "task" : r.task, "ref_video" : r.ref_video, "interval" : interval,
            "query_vi" : r.query_vi, "query_en" : r.query_en or "", "reference_frame" : _reference_frame(ctx, r) or "",
            "top5" : " | ".join(f"{v} ({n})" for v, n in top),
        }
        for code in codes :
            other = ctx.data.by_code[code].get(r.uid)
            row[f"rank {code}"] = (other.rank if other and other.rank is not None else "not retrieved") if other else ""
        row["_top"] = top
        rows.append(row)
    fields = [k for k in rows[0] if k != "_top"] if rows else []
    with open(folder / "cases.csv", "w", encoding = "utf-8-sig", newline = "") as handle :
        if (ctx.stamp) :
            handle.write(f"# {ctx.stamp}: these cases are not results\n")
        writer = csv.DictWriter(handle, fieldnames = fields, lineterminator = "\n", extrasaction = "ignore")
        writer.writeheader()
        writer.writerows(rows)

    wanted = {n for row in rows for _v, n in row["_top"] if n} | {row["reference_frame"] for row in rows if row["reference_frame"]}
    images = _find_images(ctx.images_dir, wanted) if (ctx.images_dir and ctx.images_dir.exists()) else {}
    if (images) :
        (folder / "images").mkdir(exist_ok = True)
        for name, source in images.items() :
            shutil.copyfile(source, folder / "images" / name)

    lines = [f"# Qualitative cases{f' ({ctx.stamp})' if ctx.stamp else ''}", ""]
    if (ctx.stamp) :
        lines += [f"**{ctx.stamp}: nothing here is a result.**", ""]
    lines += ["Selected by rule, 3 per rule (2 for clean hits), a query used once, ties broken by dataset and query key. Ranks are the reference video's rank per configuration.", ""]
    for rule, r in cases :
        row = next(x for x in rows if x["dataset"] == r.dataset and x["query_key"] == r.key)
        lines += [f"## {rule}: {r.dataset} {r.key} ({r.task}, reference {r.ref_video})", "", f"- Vietnamese: {r.query_vi}", f"- English searched: {r.query_en or ''}",
                  f"- Valid interval: {row['interval'] or 'none (TRAKE)'}", f"- Reference keyframe: {row['reference_frame'] or 'not available (no features folder)'}",
                  f"- Baseline top 5 videos (best frame): {row['top5']}", "- Rank per configuration: " + ", ".join(f"{c} {row[f'rank {c}']}" for c in codes), ""]
    if (not images) :
        lines += ["Frame images were not available (no --images-dir, or the names were not found). Frame names are listed above; the images come from the keyframe image folder of the deployment (the same names the app serves under /static/images/), which this analysis does not link to.", ""]
    (folder / "index.md").write_text("\n".join(lines) + "\n", encoding = "utf-8")

    if (images) :
        parts = ["<!doctype html><meta charset='utf-8'><title>Qualitative cases</title><style>body{font-family:sans-serif;max-width:1100px;margin:auto}img{height:110px;margin:2px;border:1px solid #888}.s{color:#c00;font-weight:bold}.c{border-top:1px solid #aaa;margin-top:14px}</style>"]
        if (ctx.stamp) :
            parts.append(f"<p class='s'>{html.escape(ctx.stamp)}: nothing here is a result</p>")
        for (rule, r), row in zip(cases, rows) :
            parts.append(f"<div class='c'><h3>{html.escape(rule)}: {html.escape(r.dataset)} {html.escape(r.key)} ({r.task}, reference {html.escape(r.ref_video)})</h3><p>{html.escape(r.query_vi)}<br><i>{html.escape(r.query_en or '')}</i></p>")
            if (row["reference_frame"] in images) :
                parts.append(f"<div>reference: <img src='images/{html.escape(row['reference_frame'])}' title='{html.escape(row['reference_frame'])}'></div>")
            parts.append("<div>top 5: " + "".join(f"<img src='images/{html.escape(n)}' title='{html.escape(v)} {html.escape(n)}'>" for v, n in row["_top"] if n in images) + "</div>")
            parts.append("<p>" + html.escape(", ".join(f"{c}: {row[f'rank {c}']}" for c in codes)) + "</p></div>")
        (folder / "index.html").write_text("\n".join(parts), encoding = "utf-8")
    return {"cases" : len(cases), "images" : len(images)}
