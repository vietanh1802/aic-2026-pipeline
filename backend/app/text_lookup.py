# backend/app/text_lookup.py
"""
text_lookup.py — shared video/frame-scoped ASR+OCR term lookup
================================================================

lookup_text() is the one entry point Stage C's planned features (and anything
else that needs "which frames say this text") should call, instead of driving
ocr_search / text_signal themselves. It never changes ranking or removes a
result on its own -- same non-interference stance as text_signal.py's
annotate_videos() -- it only reports where a term is found.

Two sources, two different natural granularities:

  ocr   -- ocr_search.search() already scores per FRAME, so a TextHit's rank
           and total_matched are that frame's own rank among matching frames
           (ocr_search's own tie-break rules apply, unchanged).
  asr   -- BM25 (text_signal._annotate_bm25()) scores per VIDEO, from windows
           of transcript text, not per frame. One representative TextHit is
           produced per matching video: the nearest keyframe to the first
           eligible window that actually contains a query token. rank/
           total_matched are therefore per-VIDEO here, not per-frame.

match_type -- "exact" vs "normalized":

  OCR runs the query twice, once with diacritics kept (strip_diacritics=False,
  "exact") and once with them folded (strip_diacritics=True, "normalized") --
  ocr_search.py's own two-file design (ocr_clean.json / ocr_clean_nodau.json)
  exists precisely for this. A frame found only after folding is tagged
  "normalized"; found either way, "exact" wins.

  ASR/BM25 never folds diacritics -- confirmed in text_signal.py's own module
  docstring ("BM25 vocabulary keeps diacritics"). Every BM25 hit is therefore
  inherently an exact token match; match_type is always "exact" for source="asr".

scope -- "video" restricts to one video's own frames (via
preprocess.frames_for_video(), never by reaching into preprocess._video_frames
directly). "corpus" searches everything, then drops any hit whose video has no
entry in the visual corpus at all -- this is the confirmed 873-video exclusion
(K01-K20 have ASR/playback data but were never keyframe-extracted or indexed;
see docs from this session's corpus-size investigation) -- ranks are NOT
renumbered after that drop, they reflect the full, unfiltered search.
"""

import json
import os
from dataclasses import dataclass
from typing import Literal, Optional

from app import ocr_search
from app import preprocess
from app import text_signal

OCR_LIMIT = 5000  # generous cap on returned rows; all_word_matches/rank are unaffected by it


@dataclass
class TextHit :
    video_id      : str
    frame_name    : str
    match_type    : Literal["exact", "normalized"]
    rank          : int
    total_matched : int
    # Added at the END with defaults so every positional TextHit(video, frame,
    # type, rank, total) call (text_lookup, text_signal, tests) keeps working.
    # exact_phrase: OCR only, True when the frame holds the whole typed phrase
    # rather than its words scattered (ocr_search's own row["exact_phrase"], for
    # the pass this hit came from); None for ASR. doc_id: ASR only, the BM25
    # document (window) that decided the video's rank; None for OCR.
    exact_phrase  : Optional[bool] = None
    doc_id        : Optional[int] = None


def lookup_text(
        term : str,
        source : Literal["asr", "ocr"],
        scope : Literal["video", "corpus"],
        video_id : Optional[str] = None,
) -> list[TextHit] :
    """Never raises -- same philosophy as annotate_videos(): a lookup feature
    must not be able to take anything else down with it."""
    if scope == "video" and not video_id :
        raise ValueError("scope='video' requires video_id")
    try :
        if source == "ocr" :
            return _lookup_ocr(term, scope, video_id)
        return _lookup_asr(term, scope, video_id)
    except Exception :
        return []


def lookup_text_batch(
        term : str,
        source : Literal["asr", "ocr"],
        video_ids : list[str],
) -> dict[str, list[TextHit]] :
    """Many videos, one term, one scan -- for a caller (text_signal.py's
    annotate_videos()) that used to call lookup_text(scope="video") once per
    candidate video and, in doing so, re-paid a full OCR haystack scan or BM25
    postings walk once per video instead of once per query. Measured: 100
    candidates x lookup_text(scope="video") cost ~3.0-3.2s for OCR (ocr_search
    has no per-video index -- video= is just an early `continue` inside a full
    179,728-entry scan) and up to ~470ms for BM25 on a common term.

    Reuses scope="corpus" internally -- that path already does the scan/walk
    exactly once regardless of candidate count -- then partitions the single
    result set to the requested video_ids in memory, which is cheap. Never
    raises, same as lookup_text()."""
    try :
        # ASR ranks every scored video but only resolves a frame for the
        # videos asked for: annotate_videos() wants ~60 of ~800 matches, and
        # resolving the rest (a scan of every keyframe of every video) was most
        # of the cost. The hits it returns are identical, see _lookup_asr().
        hits = (_lookup_ocr(term, "corpus", None) if source == "ocr"
                else _lookup_asr(term, "corpus", None, only_videos=set(video_ids)))
    except Exception :
        hits = []
    out : dict[str, list[TextHit]] = {video_id : [] for video_id in video_ids}
    wanted = set(video_ids)
    for hit in hits :
        if hit.video_id in wanted :
            out[hit.video_id].append(hit)
    return out


# ── OCR ──────────────────────────────────────────────────────────────────

def _lookup_ocr(term : str, scope : str, video_id : Optional[str]) -> list[TextHit] :
    allowed = set(preprocess.frames_for_video(video_id)) if scope == "video" else None
    hits : list[TextHit] = []
    seen : set[str] = set()

    for strip, tag in ((False, "exact"), (True, "normalized")) :
        result = ocr_search.search(
            term, limit=OCR_LIMIT, strip_diacritics=strip,
            video=video_id if scope == "video" else None)
        total_matched = result["all_word_matches"]

        for row in result["results"] :
            name = row["name"]
            if name in seen :
                continue  # already reported as "exact" -- don't also report "normalized"

            hit_video = video_id if scope == "video" else name.split("-")[0]
            if scope == "video" :
                if name not in allowed :
                    continue  # ocr_search's own startswith(video) has no delimiter guard
            elif not preprocess.frames_for_video(hit_video) :
                continue  # outside the 873-video visual corpus

            hits.append(TextHit(hit_video, name, tag, row["rank"], total_matched,
                                exact_phrase=row.get("exact_phrase")))
            seen.add(name)

    return hits


# ── ASR ──────────────────────────────────────────────────────────────────

@dataclass
class _Window :
    start_s : float
    text    : str


_windows_cache : Optional[dict[str, list[_Window]]] = None


def _windows_by_video() -> dict[str, list[_Window]] :
    """video -> its eligible windows, sorted by start time. Independent, tiny
    cache local to this module -- text_signal.py's own BM25 loader keeps only
    video_id/retrieval_text per doc, never the time range a hit needs to be
    placed on the timeline, so it can't be reused for that part."""
    global _windows_cache
    if _windows_cache is not None :
        return _windows_cache

    _windows_cache = {}
    path = os.path.join(text_signal.ASR_RELEASE_DIR, "windows.jsonl")
    if not os.path.exists(path) :
        return _windows_cache

    by_video : dict[str, list[_Window]] = {}
    with open(path, encoding="utf-8") as f :
        for line in f :
            row = json.loads(line)
            text = row.get("retrieval_text")
            if (not row.get("eligible")) or (not text) :
                continue
            by_video.setdefault(row["video_id"], []).append(
                _Window(row["sample_start"] / row["sample_rate"], text))
    for windows in by_video.values() :
        windows.sort(key=lambda w : w.start_s)

    _windows_cache = by_video
    return _windows_cache


def preload() -> None :
    """Warm _windows_by_video()'s lazy cache at startup. Same reasoning as
    asr_text.preload()/ocr_search.preload()/text_signal.preload() (all called
    from main.py's warm-up): the ~490ms cost of parsing windows.jsonl
    (measured -- see the batch-fix report) should land during warm-up, not on
    whichever production request happens to make the first bm25/ASR lookup.

    Never raises -- _windows_by_video() already returns an empty cache for a
    missing windows.jsonl without raising, but a present-and-corrupt file
    could still throw on json.loads(); that must not fail warm-up and skip
    the preload calls after it, same as ocr_route.preload()/_asr_text.preload()."""
    try :
        _windows_by_video()
    except Exception as e :
        print(f"[text_lookup] windows cache not warmed ({type(e).__name__}: {e})")


def _frame_idx(name : str) -> int :
    return int(name.rsplit("-", 1)[1].split(".")[0])


def _nearest_keyframe(video_id : str, time_s : float) -> Optional[str] :
    """Same fps-based math as scripts/build_asr_text_index.py's
    frame_timestamp_seconds() (t = frame_idx / fps), inverted here to go from
    a window's time back to the nearest real keyframe of that video."""
    names = preprocess.frames_for_video(video_id)
    if not names :
        return None
    fps = preprocess.fps_for_video(video_id)
    target = time_s * fps
    return min(names, key=lambda name : abs(_frame_idx(name) - target))


# Replaced by the best-window lookup in _lookup_asr(). Kept for reference, not
# deleted: it returned the FIRST window in time order that shares ANY query token
# with the term, which is not the window that decided the video's BM25 rank (for
# "thì hiện tại" on L25_V075 it reported frame 3, 0.12 s in, while the best window
# is 810-870 s; it differed from the best window in 87% of 834 matched videos).
# It also re-tokenized that video's windows on every call.
#
# def _nearest_frame_for_term(video_id : str, term : str) -> Optional[str] :
#     windows = _windows_by_video().get(video_id)
#     if not windows :
#         return None
#     tokens = set(text_signal._bm25_tokenize(term))
#     match = next((w for w in windows if tokens & set(text_signal._bm25_tokenize(w.text))), None)
#     if match is None :
#         return None
#     return _nearest_keyframe(video_id, match.start_s)


def _lookup_asr(
        term : str,
        scope : str,
        video_id : Optional[str],
        only_videos : Optional[set[str]] = None,
) -> list[TextHit] :
    """One representative TextHit per matching video: the nearest keyframe to
    the start of the BM25 window that decided the video's score (ties go to the
    earliest window, see text_signal._best_windows_bm25()).

    Ranks are RAW and un-renumbered: they count every scored video, including
    the K01-K20 videos that were never keyframe-extracted (BM25 covers 1,478
    videos, the visual corpus 873), and total_matched is the number of scored
    videos. Dropping a video afterwards (no keyframes) leaves a gap in the ranks.

    only_videos (default None = every video, today's behaviour): rank
    enumeration still runs over ALL scored videos, so ranks and total_matched
    are identical, but the corpus-membership check, the frame resolution and the
    hit creation happen only for the videos in the set. The hits returned for
    those videos are the same ones a full run would return for them."""
    text_signal._load_bm25()
    if not text_signal._bm25_loaded :
        return []

    candidates = [video_id] if scope == "video" else sorted(set(text_signal._bm25_doc_video_ids))
    best_windows = text_signal._best_windows_bm25(candidates, term)
    scores = text_signal._normalize_bm25(best_windows, candidates)

    scored = sorted(
        ((vid, score) for vid, score in scores.items() if score > 0),
        key=lambda pair : (-pair[1], pair[0]))
    total_matched = len(scored)

    hits : list[TextHit] = []
    for rank, (vid, _score) in enumerate(scored, 1) :
        if (only_videos is not None) and (vid not in only_videos) :
            continue
        if scope == "corpus" and not preprocess.frames_for_video(vid) :
            continue  # outside the 873-video visual corpus
        doc_id = best_windows[vid][1]
        frame_name = _nearest_keyframe(vid, float(text_signal._bm25_doc_start_s[doc_id]))
        if frame_name is None :
            continue
        hits.append(TextHit(vid, frame_name, "exact", rank, total_matched, doc_id=doc_id))
    return hits
