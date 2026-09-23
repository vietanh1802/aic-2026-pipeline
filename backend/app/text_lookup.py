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
from app.text_signal import TextMatchMode

OCR_LIMIT = 5000  # generous cap on returned rows; all_word_matches/rank are unaffected by it


@dataclass
class TextHit :
    video_id      : str
    frame_name    : str
    match_type    : Literal["exact", "normalized"]
    rank          : int
    total_matched : int


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

            hits.append(TextHit(hit_video, name, tag, row["rank"], total_matched))
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


def _nearest_frame_for_term(video_id : str, term : str) -> Optional[str] :
    windows = _windows_by_video().get(video_id)
    if not windows :
        return None
    tokens = set(text_signal._bm25_tokenize(term))
    match = next((w for w in windows if tokens & set(text_signal._bm25_tokenize(w.text))), None)
    if match is None :
        return None
    return _nearest_keyframe(video_id, match.start_s)


def _lookup_asr(term : str, scope : str, video_id : Optional[str]) -> list[TextHit] :
    text_signal._load_bm25()
    if not text_signal._bm25_loaded :
        return []

    candidates = [video_id] if scope == "video" else sorted(set(text_signal._bm25_doc_video_ids))
    annotations = text_signal._annotate_bm25(candidates, term, {}, TextMatchMode.bm25)

    scored = sorted(
        ((vid, ann.score) for vid, ann in annotations.items() if ann.score > 0),
        key=lambda pair : (-pair[1], pair[0]))
    total_matched = len(scored)

    hits : list[TextHit] = []
    for rank, (vid, _score) in enumerate(scored, 1) :
        if scope == "corpus" and not preprocess.frames_for_video(vid) :
            continue  # outside the 873-video visual corpus
        frame_name = _nearest_frame_for_term(vid, term)
        if frame_name is None :
            continue
        hits.append(TextHit(vid, frame_name, "exact", rank, total_matched))
    return hits
