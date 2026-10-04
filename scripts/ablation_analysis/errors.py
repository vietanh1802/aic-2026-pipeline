# scripts/ablation_analysis/errors.py
"""Automatic error analysis: mechanical labels from stored ranks and frames, no guessing.

Rank buckets, interval buckets, cross-configuration labels (hard, rescued or hurt by fusion, only one
encoder hits, rerank gained or lost, gtx beats raw), the TRAKE failure stage, the distractor profile of
baseline failures, and query properties with their correlation to the baseline reference rank. The manual
labelling sheet is written here too. Nothing in this module judges why a query failed; the sheet exists
so a person can.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from ablation_analysis import stats
from ablation_analysis.data import Result, RunData
from ablation_analysis.features import Features

RANK_BUCKETS = ("top1", "2 to 5", "6 to 10", "11 to 100", "not retrieved")
GAP_BUCKETS = ("inside", "within 5 s", "5 to 30 s", "over 30 s", "no frame returned")
TAXONOMY = (
    ("D1", "many visually similar videos"),
    ("D2", "small or fine detail not captured"),
    ("D3", "depends on visible text"),
    ("D4", "depends on speech"),
    ("D5", "action or temporal order not visible in one frame"),
    ("D6", "query ambiguous or under-specified"),
    ("D7", "translation or text-encoder loss"),
    ("D8", "reference label doubtful"),
    ("D9", "other"),
)


def rank_bucket(rank : int | None) -> str :
    if (rank is None) :
        return "not retrieved"
    return "top1" if rank == 1 else "2 to 5" if rank <= 5 else "6 to 10" if rank <= 10 else "11 to 100"


def gap_bucket(result : Result) -> str | None :
    """Where the closest returned frame of the reference video lies relative to the valid interval, for
    KIS and QA. None for TRAKE (no interval). Uses the interval_gap stored by the runner; falls back to
    interval_hit when the run predates it."""
    if (result.task == "TRAKE" or not result.intervals) :
        return None
    if (result.interval_hit) :
        return "inside"
    gap = result.extra.get("interval_gap")
    if (not gap or gap.get("gap_s") is None) :
        return "no frame returned" if result.rank is None else None
    seconds = gap["gap_s"]
    return "within 5 s" if seconds <= 5 else "5 to 30 s" if seconds <= 30 else "over 30 s"


def series(video : str) -> str :
    """The number before the V suffix: L26 in L26_V104, N061 in N061-V002."""
    return re.split(r"[_-]V\d", video)[0]


def distractor_profile(result : Result) -> dict[str, Any] :
    """What the baseline returned instead, for one query."""
    top = result.ranked[0]["video_id"] if result.ranked else None
    return {
        "top1_video" : top,
        "top1_prefix" : top[ : 1] if top else None,
        "top1_same_series" : (series(top) == series(result.ref_video)) if top else None,
        "ref_frames_in_top100" : sum(1 for f in result.frames if f.get("video") == result.ref_video),
        "distinct_videos_in_top100" : len({f.get("video") for f in result.frames}),
    }


def trake_stage(result : Result) -> str :
    """Why a TRAKE-N query failed, from rank and the stored discovery block."""
    trake = result.extra.get("trake") or {}
    discovery = trake.get("discovery") or {}
    if (not discovery or "error" in discovery) :
        return "unknown (no discovery block)"
    if (not discovery.get("in_shortlist")) :
        return "not shortlisted"
    if (not discovery.get("feasible_chain")) :
        return "shortlisted, no feasible chain"
    if (result.rank != 1) :
        return "chain found, reference video not ranked first"
    events = trake.get("events")
    if (events and events["correct"] < events["total"]) :
        return "right video, wrong event frame"
    return "success" if events else "right video, events not scored"


def cross_labels(data : RunData, bench : str, ks : Sequence[int] = (1, 10)) -> dict[tuple[str, str], dict[str, Any]] :
    """Per query, labels that need more than one configuration. Missing configurations give no label."""
    base = data.code_for("base")
    singles = [c for c in (data.code_for(f"single:{m}") for m in ("beit3", "clip", "siglip2")) if c]
    off, raw = data.code_for("all:off"), data.code_for("raw_vi")
    grid = [c for c, info in data.configs.items() if not info.role.startswith(("trake", "other"))]
    labels : dict[tuple[str, str], dict[str, Any]] = {}
    for r in data.results_of(base, bench) :
        uid = r.uid
        def get(code : str | None) -> Result | None :
            return data.by_code.get(code, {}).get(uid) if code else None

        row : dict[str, Any] = {
            "dataset" : r.dataset, "query_key" : r.key, "task" : r.task, "ref_video" : r.ref_video, "prefix" : r.prefix, "flags" : ";".join(r.flags),
            "baseline_rank" : r.rank, "hard" : all(not (get(c) and get(c).hit(10)) for c in grid),
        }
        for k in ks :
            single_hits = [bool(get(c) and get(c).hit(k)) for c in singles]
            row[f"rescued_by_fusion@{k}"] = len(singles) == 3 and r.hit(k) and not any(single_hits)
            row[f"hurt_by_fusion@{k}"] = len(singles) == 3 and (not r.hit(k)) and any(single_hits)
            row[f"only_one_encoder@{k}"] = len(singles) == 3 and sum(single_hits) == 1
            if (off) :
                row[f"rerank_gained@{k}"] = r.hit(k) and not (get(off) and get(off).hit(k))
                row[f"rerank_lost@{k}"] = (not r.hit(k)) and bool(get(off) and get(off).hit(k))
            if (raw) :
                row[f"gtx_beats_raw@{k}"] = r.hit(k) and not (get(raw) and get(raw).hit(k))
                row[f"raw_beats_gtx@{k}"] = (not r.hit(k)) and bool(get(raw) and get(raw).hit(k))
        labels[uid] = row
    return labels


# ─── query properties and their correlation with the baseline rank ─────────

def words(text : str) -> int :
    return len(text.split())


def clauses(text : str) -> int :
    return len([part for part in re.split(r"[.,;:!?]+", text) if part.strip()])


def has_digits(text : str) -> bool :
    return bool(re.search(r"\d", text))


def has_quoted_or_capitalised(text : str) -> bool :
    """A quotation mark, or a capitalised word that is not the first word of a sentence (a name, a sign)."""
    if (re.search(r"[\"“”‘’']", text)) :
        return True
    tokens = text.split()
    for i, token in enumerate(tokens) :
        if (i > 0 and not re.search(r"[.!?:]$", tokens[i - 1]) and token[ : 1].isalpha() and token[ : 1].isupper()) :
            return True
    return False


def query_properties(result : Result, features : Features | None) -> dict[str, Any] :
    props : dict[str, Any] = {
        "words" : words(result.query_vi), "clauses" : clauses(result.query_vi), "has_digits" : int(has_digits(result.query_vi)),
        "has_quoted_or_capitalised" : int(has_quoted_or_capitalised(result.query_vi)),
        "task" : result.task, "prefix" : result.prefix,
        "ref_duration_s" : None, "ref_keyframes" : None, "interval_keyframes" : None, "interval_s" : None, "interval_share" : None,
    }
    if (features is None) :
        return props
    video = features.videos.get(result.ref_video)
    if (video) :
        props["ref_duration_s"], props["ref_keyframes"] = video["duration_s"], video["n_keyframes"]
        if (result.intervals) :
            fps = video["fps"] or 25.0
            seconds = sum((e - s) / fps for s, e in result.intervals)
            props["interval_s"] = round(seconds, 2)
            props["interval_share"] = round(seconds / video["duration_s"], 5) if video["duration_s"] else None
    frames = features.frames_ref.get(result.ref_video)
    if (frames and result.intervals) :
        props["interval_keyframes"] = sum(1 for _n, _s, f in frames if any(s <= f <= e for s, e in result.intervals))
    return props


NUMERIC_PROPERTIES = ("words", "clauses", "has_digits", "has_quoted_or_capitalised", "ref_duration_s", "ref_keyframes", "interval_keyframes", "interval_s", "interval_share")


def property_correlations(results : Sequence[Result], features : Features | None) -> list[dict[str, Any]] :
    """Spearman of each numeric property with the reference rank (a miss counts as rank 101), with a
    bootstrap interval, n and the tercile Hit@1 and R@10. Descriptive only."""
    rows = []
    props = [query_properties(r, features) for r in results]
    for name in NUMERIC_PROPERTIES :
        pairs = [(p[name], r) for p, r in zip(props, results) if p[name] is not None]
        if (len(pairs) < 5) :
            rows.append({"property" : name, "n" : len(pairs), "spearman" : None, "ci_low" : None, "ci_high" : None})
            continue
        x = [v for v, _r in pairs]
        y = [r.rank_or_miss for _v, r in pairs]
        rho, low, high = stats.correlation_ci(x, y)
        record = {"property" : name, "n" : len(pairs), "spearman" : rho, "ci_low" : low, "ci_high" : high}
        cuts = np.quantile(np.array(x, dtype = float), [1 / 3, 2 / 3])
        if (len(set(cuts)) == 2) :
            terciles = [[r for v, r in pairs if (v <= cuts[0] if t == 0 else cuts[0] < v <= cuts[1] if t == 1 else v > cuts[1])] for t in range(3)]
            for t, group in enumerate(terciles) :
                record[f"t{t + 1}_n"] = len(group)
                record[f"t{t + 1}_hit1"] = sum(1 for r in group if r.hit(1)) / len(group) if group else None
                record[f"t{t + 1}_r10"] = sum(1 for r in group if r.hit(10)) / len(group) if group else None
        rows.append(record)
    return rows


# ─── manual labelling sheet ────────────────────────────────────────────────

SHEET_FIELDS = (
    "dataset", "query_key", "task", "ref_video", "interval_s", "query_vi", "query_en", "baseline_rank", "top5_videos", "auto_labels",
    "error_codes", "small_detail_query", "text_cue_present", "label_doubt", "notes",
)


def labeling_sheet(data : RunData, features : Features | None) -> list[dict[str, Any]] :
    """One row per query where the baseline did not hit at 1, with empty columns for the person."""
    base = data.code_for("base")
    rows = []
    for bench in ("A", "B") :
        labels = cross_labels(data, bench)
        for r in data.results_of(base, bench) :
            if (r.hit(1)) :
                continue
            label = labels.get(r.uid, {})
            auto = [name for name, value in label.items() if value is True]
            video = (features.videos.get(r.ref_video) if features else None) or {}
            fps = video.get("fps") or 25.0
            interval_s = "; ".join(f"{s / fps:.1f}-{e / fps:.1f}" for s, e in r.intervals) if r.intervals else ""
            rows.append({
                "dataset" : r.dataset, "query_key" : r.key, "task" : r.task, "ref_video" : r.ref_video, "interval_s" : interval_s,
                "query_vi" : r.query_vi, "query_en" : r.query_en or "", "baseline_rank" : r.rank if r.rank is not None else "not retrieved",
                "top5_videos" : "; ".join(v["video_id"] for v in r.ranked[ : 5]), "auto_labels" : "; ".join(auto),
                "error_codes" : "", "small_detail_query" : "", "text_cue_present" : "", "label_doubt" : "", "notes" : "",
            })
    return rows


def write_sheet(folder : Path, rows : list[dict[str, Any]]) -> None :
    folder.mkdir(parents = True, exist_ok = True)
    with open(folder / "error_labeling_sheet.csv", "w", encoding = "utf-8-sig", newline = "") as handle :
        writer = csv.DictWriter(handle, fieldnames = list(SHEET_FIELDS), lineterminator = "\n")
        writer.writeheader()
        writer.writerows(rows)
    with open(folder / "taxonomy.csv", "w", encoding = "utf-8", newline = "") as handle :
        writer = csv.writer(handle, lineterminator = "\n")
        writer.writerow(["code", "description"])
        writer.writerows(TAXONOMY)
    try :
        from openpyxl import Workbook
        from openpyxl.worksheet.datavalidation import DataValidation
    except ImportError :
        return
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "labels"
    sheet.append(list(SHEET_FIELDS))
    for row in rows :
        sheet.append([row[f] for f in SHEET_FIELDS])
    last = max(2, len(rows) + 1)
    for column, options in (("small_detail_query", "yes,no"), ("text_cue_present", "ocr,asr,both,none"), ("label_doubt", "yes,no")) :
        letter = chr(ord("A") + SHEET_FIELDS.index(column))
        validation = DataValidation(type = "list", formula1 = f'"{options}"', allow_blank = True)
        sheet.add_data_validation(validation)
        validation.add(f"{letter}2:{letter}{last}")
    codes = workbook.create_sheet("taxonomy")
    codes.append(["code", "description"])
    for code, description in TAXONOMY :
        codes.append([code, description])
    workbook.save(folder / "error_labeling_sheet.xlsx")
