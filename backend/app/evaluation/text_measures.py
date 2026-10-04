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
  strict           {ref_flagged, n_flagged} under the strict rule described below

Each block also carries a `strict` sub-block: the same three counts, but a video counts as flagged only when
EVERY term of a source's cue is found in it (AND over the terms of one source, OR over the sources). The plain
measure is an OR over terms, so a cue with a common short term ("13", "2022") flags most of the result list;
the strict one shows how much of that is the OR rule. Single-term cues give identical numbers by construction.

Coverage is recorded separately, per video, from the artifacts loaded at that moment, so a later run on
refreshed OCR/ASR data needs no code change.

Loading. ocr_search.get_text() loads its files on first use, but asr_text.get_text() deliberately does NOT
(it is a pure dict lookup that must never raise inside the request path; only asr_text.preload() reads the
file, and main.py calls it at warm-up). A process that is not the API, such as the suite script, must call
load_text_artifacts() itself, otherwise every ASR lookup silently returns "" and every ASR measure reads
as "nothing matched". That is exactly what the first real run recorded.
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


def _error(part : str, exc : Exception, **where : Any) -> dict[str, Any] :
    return {"part" : part, **where, "error_type" : type(exc).__name__, "message" : str(exc)[ : 300]}


def load_text_artifacts() -> dict[str, Any] :
    """Read the OCR and ASR text files into THIS process (idempotent) and report what is loaded.

    Returns {"ocr" : {...}, "asr" : {...}} with ready, entries (frames that carry text), path and error.
    A source that cannot be read is reported with its error instead of raising: the caller decides whether
    that stops it (scripts/run_ablation_suite.py refuses to start) or only degrades the side measures (a
    run through the API). The broad except is deliberate for that reason and the message is never dropped."""
    from app import asr_text, ocr_search

    report : dict[str, Any] = {}
    for source, module, loader in (("ocr", ocr_search, ocr_search._load), ("asr", asr_text, asr_text._load)) :
        error = None
        try :
            loader()
        except Exception as exc :
            error = f"{type(exc).__name__}: {str(exc)[ : 300]}"
        status = module.status()
        report[source] = {
            "ready"   : bool(status.get("ready")),
            "entries" : int(status.get("frames_with_text", status.get("entries_loaded", 0)) or 0),
            "path"    : status.get("with_marks_path") or status.get("file_path"),
            "error"   : error,
        }
    return report


def coverage_for_video(video_id : str, errors : list[dict[str, Any]] | None = None) -> dict[str, Any] :
    """Keyframes of one video that have OCR text and ASR text in the loaded artifacts.

    Each source is counted on its own. A source whose artifact is missing or unreadable (the N and S
    videos have no OCR or ASR at all) gives None for that source and, when `errors` is passed, an entry
    there, instead of raising: coverage is a side measure and must not cost a query its result."""
    from app import asr_text, ocr_search, preprocess

    names = preprocess.frames_for_video(video_id)
    coverage : dict[str, Any] = {"keyframes" : len(names)}
    for source, module in (("ocr", ocr_search), ("asr", asr_text)) :
        try :
            if (source == "asr" and names and not asr_text.status().get("ready")) :
                # get_text() would answer "" for every frame and read as "no ASR text": say so instead.
                # (A video with no keyframes has nothing to mislabel, so it counts 0 of 0 as before.)
                raise RuntimeError("ASR text index is not loaded in this process (call text_measures.load_text_artifacts())")
            coverage[source] = sum(1 for n in names if module.get_text(n))
        except Exception as exc :
            if (errors is None) :
                raise
            coverage[source] = None
            errors.append(_error("coverage", exc, source = source))
    return coverage


def _videos_with_term(frame_results : list[dict[str, Any]], source : str, term : str, asr_mode : str) -> set[str] :
    """Videos of the result list in which ONE term is found by one source (the single-term path of annotate_request)."""
    from app.text_signal import OcrFilterMode, TextMatchMode, annotate_request

    outcome = annotate_request(
        asr_filter = term if source == "asr" else "", asr_filter_mode = TextMatchMode(asr_mode),
        ocr_filter = term if source == "ocr" else "", ocr_filter_mode = OcrFilterMode.substring,
        legacy_filter = "", legacy_mode = TextMatchMode.substring, results = frame_results,
    )
    return {video for video, a in (outcome.video_annotations or {}).items() if a["matched"]}


def _strict_counts(
    frame_results : list[dict[str, Any]],
    used : dict[str, list[str]],
    reference_video : str,
    asr_mode : str,
    memo : dict[tuple[str, str], set[str]],
    or_matched : set[str],
) -> dict[str, Any] | None :
    """The strict variant: a video is flagged for a source when it holds EVERY term of that source's cue, and for
    a variant when any of its sources is flagged. None in bm25 mode (a BM25 query is one bag of tokens, there is no
    per-term match to intersect). With at most one term per source the OR rule already is the strict rule, so the
    scan is not repeated. `memo` shares per-term scans between the ocr, asr and both variants of one query."""
    if (asr_mode != "substring") :
        return None
    if (all(len(terms) <= 1 for terms in used.values())) :
        matched = or_matched
    else :
        matched = set()
        for source, terms in used.items() :
            if (not terms) :
                continue
            per_term = []
            for term in terms :
                if ((source, term) not in memo) :
                    memo[(source, term)] = _videos_with_term(frame_results, source, term, asr_mode)
                per_term.append(memo[(source, term)])
            matched |= set.intersection(*per_term)
    return {"ref_flagged" : reference_video in matched, "n_flagged" : len(matched)}


def annotate_block(
    frame_results : list[dict[str, Any]],
    terms : dict[str, list[str]],
    variant : str,
    reference_video : str,
    valid_intervals : list[dict[str, int]] | None,
    reference_rank : int | None,
    asr_mode : str = "substring",
    memo : dict[tuple[str, str], set[str]] | None = None,
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
        "strict"          : _strict_counts(frame_results, used, reference_video, asr_mode, {} if memo is None else memo, matched),
    }


def annotate_query(
    frame_results : list[dict[str, Any]],
    cues : dict[str, dict[str, list[str]]],
    reference_video : str,
    valid_intervals : list[dict[str, int]] | None,
    reference_rank : int | None,
    asr_mode : str = "substring",
    errors : list[dict[str, Any]] | None = None,
) -> dict[str, Any] :
    """{kind: {variant: block}} for every cue kind the query has (confirmed, legacy_leaky).

    Each variant (ocr, asr, both) is annotated on its own. One that raises, for example because the
    OCR or ASR files are missing for an N or S video, becomes None and an entry in `errors`; the
    others still run. Without an `errors` list the exception propagates (for direct callers)."""
    blocks : dict[str, dict[str, dict[str, Any] | None]] = {}
    for kind, terms in cues.items() :
        blocks[kind] = {}
        memo : dict[tuple[str, str], set[str]] = {}     # per-term scans, shared by the three variants of this cue kind
        for variant in VARIANTS :
            try :
                blocks[kind][variant] = annotate_block(
                    frame_results, terms, variant, reference_video, valid_intervals, reference_rank, asr_mode, memo)
            except Exception as exc :
                if (errors is None) :
                    raise
                blocks[kind][variant] = None
                errors.append(_error("annotation", exc, kind = kind, variant = variant))
    return blocks


def measure_query(
    frame_results : list[dict[str, Any]],
    reference_video : str,
    valid_intervals : list[dict[str, int]] | None,
    reference_rank : int | None,
    cues : dict[str, dict[str, list[str]]],
    annotate : bool,
    asr_mode : str = "substring",
) -> tuple[dict[str, Any], list[dict[str, Any]]] :
    """The side measures of one query: OCR/ASR coverage of the reference video and, when `annotate`,
    the annotation blocks. Returns (what to merge into extra_json, errors).

    This never raises. Annotation is a side feature on top of a ranking that is already scored, so a
    failure per source is recorded under text_signal_errors and the query keeps its retrieval metrics."""
    errors : list[dict[str, Any]] = []
    extra : dict[str, Any] = {}
    try :
        extra["text_coverage"] = coverage_for_video(reference_video, errors)
    except Exception as exc :
        errors.append(_error("coverage", exc))
    if (annotate) :
        try :
            extra["text_signal"] = annotate_query(
                frame_results, cues, reference_video, valid_intervals, reference_rank, asr_mode, errors)
        except Exception as exc :
            errors.append(_error("annotation", exc))
    return extra, errors
