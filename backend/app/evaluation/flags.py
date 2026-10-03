# backend/app/evaluation/flags.py
"""Per-query label flags, kept in sidecar files so a shipped seed is never edited.

seeds/flags/*.json, one file per flag, each {"flag": name, ...} plus either
  "videos":  reference video ids that carry the flag (vfr_times: keyframe timestamps drift from the
             container clock, so interval-level results on them are unreliable), or
  "queries": [{"dataset": version, "query_key": key}] for single queries (whole_video_interval: the
             valid interval covers the whole video, so the interval metric is trivially a hit).
Video-level metrics are unaffected by either flag; the flags exist so reports can be computed with
and without the affected queries. There is no remark_requested flag.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

FLAGS_DIR = Path(__file__).resolve().parent / "seeds" / "flags"


@lru_cache(maxsize = 1)
def _load() -> tuple[dict[str, frozenset[str]], dict[str, frozenset[tuple[str, str]]]] :
    by_video : dict[str, frozenset[str]] = {}
    by_query : dict[str, frozenset[tuple[str, str]]] = {}
    for path in sorted(FLAGS_DIR.glob("*.json")) :
        data = json.loads(path.read_text(encoding = "utf-8"))
        name = data["flag"]
        if ("videos" in data) :
            by_video[name] = frozenset(data["videos"])
        if ("queries" in data) :
            by_query[name] = frozenset((q["dataset"], q["query_key"]) for q in data["queries"])
    return by_video, by_query


def flags_for(dataset_version : str, query_key : str, video_id : str) -> list[str] :
    by_video, by_query = _load()
    found = {name for name, videos in by_video.items() if video_id in videos}
    found |= {name for name, queries in by_query.items() if (dataset_version, query_key) in queries}
    return sorted(found)


def select_rows(rows, config) -> list :
    """Apply a RunConfig's subset (task types, excluded flags) to query rows that carry
    dataset_version, query_key, task_type and video_id."""
    subset = config.subset
    chosen = []
    for row in rows :
        if (subset.task_types is not None and row["task_type"] not in subset.task_types) :
            continue
        if (subset.exclude_flags and set(subset.exclude_flags) & set(flags_for(row["dataset_version"], row["query_key"], row["video_id"]))) :
            continue
        chosen.append(row)
    return chosen[ : subset.limit_queries]
