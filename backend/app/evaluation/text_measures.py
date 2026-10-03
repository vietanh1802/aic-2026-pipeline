# backend/app/evaluation/text_measures.py
"""Annotation-level measures of the OCR and ASR filters. They never touch a ranking.

In the shipped system OCR and ASR only ANNOTATE results: text_signal.annotate_request marks videos of the
returned frames and changes no rank (Stage D, injection, is not implemented). So the question a run can
answer is not "did the filter move the answer up" but "would the filter have pointed at the answer".
For one query, with the cue terms labelled for it, this module calls annotate_request on the query's own
frames (exactly what /ensemble-search does after retrieval) for ocr, asr and both, and keeps per variant:

  ref_flagged      the reference video is annotated as matched (here or elsewhere)
  ref_location     here (the matched frame is one of the returned frames) | elsewhere | none | absent
                   (the reference video is not in the returned frames, so nothing was annotated for it)
  ref_in_interval  a matched frame of the reference video lies inside a valid interval (KIS and QA)
  n_flagged        videos of the result list that are annotated as matched
  n_videos         videos in the result list
  ref_rank         the reference video's rank, for rescue potential (flagged but not first)

Coverage is recorded separately, per video, from the artifacts loaded at that moment, so a later run on
refreshed OCR/ASR data needs no code change.
"""
from __future__ import annotations

from typing import Any

SOURCES = ("ocr", "asr")
VARIANTS = ("ocr", "asr", "both")


def _frame_idx(name : str | None) -> int | None :
    try :
        return int(str(name).rsplit("-", 1)[1].split(".")[0])
    except (IndexError, ValueError) :
        return None


def coverage_for_video(video_id : str) -> dict[str, Any] :
    """Keyframes of one video that have OCR text and ASR text in the loaded artifacts."""
    from app import asr_text, ocr_search, preprocess

    names = preprocess.frames_for_video(video_id)
    return {
        "keyframes" : len(names),
        "ocr"       : sum(1 for n in names if ocr_search.get_text(n)),
        "asr"       : sum(1 for n in names if asr_text.get_text(n)),
    }


def annotate_block(
    frame_results : list[dict[str, Any]],
    terms : dict[str, list[str]],
    variant : str,
    reference_video : str,
    valid_intervals : list[dict[str, int]] | None,
    reference_rank : int | None,
    asr_mode : str = "substring",
) -> dict[str, Any] | None :
    """One variant of one query, or None when the labelled terms have nothing for its sources."""
    from app.text_signal import MAX_FILTER_TERMS, OcrFilterMode, TextMatchMode, annotate_request

    sources = SOURCES if variant == "both" else (variant,)
    used = {s : terms.get(s, [])[ : MAX_FILTER_TERMS] for s in sources}
    if (not any(used.values())) :
        return None

    outcome = annotate_request(
        asr_filter = ", ".join(used.get("asr", [])), asr_filter_mode = TextMatchMode(asr_mode),
        ocr_filter = ", ".join(used.get("ocr", [])), ocr_filter_mode = OcrFilterMode.substring,
        legacy_filter = "", legacy_mode = TextMatchMode.substring, results = frame_results,
    )
    annotations = outcome.video_annotations or {}
    reference = annotations.get(reference_video)
    matched = {video for video, a in annotations.items() if a["matched"]}

    location = "absent"
    in_interval = None
    if (reference is not None) :
        locations = [reference[s]["location"] for s in sources]
        location = "here" if "here" in locations else "elsewhere" if "elsewhere" in locations else "none"
        if (valid_intervals is not None) :
            frames = [_frame_idx(reference[s]["match_frame"]) for s in sources if reference[s]["match_frame"]]
            in_interval = any(
                f is not None and iv["start"] <= f <= iv["end"] for f in frames for iv in valid_intervals
            )
    return {
        "terms"           : used,
        "ref_flagged"     : reference_video in matched,
        "ref_location"    : location,
        "ref_in_interval" : in_interval if reference_video in matched else None,
        "n_flagged"       : len(matched),
        "n_videos"        : len(annotations),
        "ref_rank"        : reference_rank,
    }


def annotate_query(
    frame_results : list[dict[str, Any]],
    cues : dict[str, dict[str, list[str]]],
    reference_video : str,
    valid_intervals : list[dict[str, int]] | None,
    reference_rank : int | None,
    asr_mode : str = "substring",
) -> dict[str, Any] :
    """{kind: {variant: block}} for every cue kind the query has (confirmed, legacy_leaky)."""
    return {
        kind : {
            variant : annotate_block(frame_results, terms, variant, reference_video, valid_intervals, reference_rank, asr_mode)
            for variant in VARIANTS
        }
        for kind, terms in cues.items()
    }
