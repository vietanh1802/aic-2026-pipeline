# backend/app/evaluation/diagnostics.py
"""Per-query diagnostics stored beside the scores, so the offline analysis needs no rerun.

interval_gap answers, for a KIS or QA query whose ranking found the right video but no frame inside the
valid interval (or found none at all), how far the closest returned frame of the reference video was
from the interval. It is computed from the stored top-100 frames: it says nothing about keyframes that
were never returned. The distance to the nearest keyframe of the whole video is rebuilt offline from
the corpus features (frames_ref.csv), not here.

scoring.py is not touched: these numbers sit in extra_json under interval_gap.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def _gap_to_intervals(frame_idx : int, intervals : Sequence[tuple[int, int]]) -> int :
    """0 inside any interval (both ends inclusive), else the distance in frames to the nearest edge."""
    return min(0 if start <= frame_idx <= end else min(abs(frame_idx - start), abs(frame_idx - end)) for start, end in intervals)


def interval_gap(
    frame_results : Sequence[dict[str, Any]],
    reference_video : str,
    valid_intervals : Sequence[dict[str, int]] | None,
    fps : float | None,
) -> dict[str, Any] | None :
    """Closest returned frame of the reference video to the valid interval, or None for a query with no
    interval (TRAKE). Ties go to the better-ranked frame. gap_s is gap_frames / fps; fps is the value
    the metadata gives for that video, recorded so the conversion can be audited (variable frame rate
    N videos make the seconds unreliable, the frame gap is exact)."""
    if (valid_intervals is None) :
        return None
    intervals = [(int(iv["start"]), int(iv["end"])) for iv in valid_intervals]
    reference = reference_video.strip()

    best : tuple[int, int, int] | None = None   # (gap, rank, frame_idx)
    first_rank : int | None = None
    count = 0
    for rank, frame in enumerate(frame_results, start = 1) :
        if (str(frame.get("video") or "").strip() != reference or frame.get("frame_idx") is None) :
            continue
        count += 1
        if (first_rank is None) :
            first_rank = rank
        gap = _gap_to_intervals(int(frame["frame_idx"]), intervals)
        if (best is None or gap < best[0]) :
            best = (gap, rank, int(frame["frame_idx"]))

    return {
        "fps"                  : fps,
        "n_ref_frames"         : count,
        "first_ref_frame_rank" : first_rank,
        "nearest_frame_rank"   : best[1] if best else None,
        "nearest_frame_idx"    : best[2] if best else None,
        "gap_frames"           : best[0] if best else None,
        "gap_s"                : round(best[0] / fps, 2) if (best and fps) else None,
        "inside"               : best[0] == 0 if best else False,
    }
