# backend/app/text_signal.py
# -*- coding: utf-8 -*-
"""
text_signal.py — per-video text-match annotation engine (ASR + OCR)
=====================================================================

Sits between the raw text data (asr_text.py + ocr_search.py, via
text_lookup.py's per-video lookup) and the ensemble endpoint. Given the
video_ids in a result set and a filter query, returns a per-video
VideoAnnotation identifying, for each source separately, WHICH FRAME matched
and whether that frame is one already on screen or elsewhere in the video.
This is PURELY ADDITIVE metadata -- it never removes a frame or changes a
rank; see main.py's ensemble endpoint for how the response is annotated.

Stage C rewrite -- the bug this replaces
-----------------------------------------
The previous version joined every retrieved frame's OCR/ASR text into one
string per video (_video_texts()/_concat_dedup_adjacent()) and matched
against that blob. Two confirmed failures followed directly from that:

  1. A match on frame A got reported as if it belonged to frame B of the same
     video, because both frames' text had been concatenated before matching
     -- there was no way to say which frame the hit actually came from.
  2. A match on a frame outside the currently-retrieved set was invisible
     entirely -- the blob only ever contained the handful of frames already
     in the visual result set, not the video's real frame list.

This version calls text_lookup.lookup_text(term, source, scope="video",
video_id) per candidate video instead. lookup_text() searches the video's
FULL frame list (via preprocess.frames_for_video(), Stage B), not just the
retrieved subset, which is what catches (2); each TextHit names its own
frame_name, which is what fixes (1). "here" vs "elsewhere" is then just
membership in this query's own frame_names dict -- unchanged from before.

Three modes, `TextMatchMode`:

  bm25      -- ASR only (unchanged from before: OCR was never part of bm25
               mode). Routes through lookup_text(source="asr").
  substring -- OCR routes through lookup_text(source="ocr") (word-scatter +
               phrase matching, exact vs. diacritic-folded "normalized" --
               see text_lookup.py / ocr_search.py). ASR does NOT route
               through lookup_text(source="asr"): that path is unconditional
               BM25 relevance scoring, a different (and looser) guarantee
               than substring mode's deterministic "is this text present"
               contract, so substring mode keeps its own per-frame,
               diacritic-aware substring check -- fixed the same way (full
               frame list via preprocess.frames_for_video(), not a blob).
  regex     -- Does NOT map onto lookup_text() at all: neither ocr_search's
               word/phrase engine nor BM25's tokenized relevance scoring can
               express an arbitrary regex. Keeps its own per-frame,
               non-folded re.search() check for both sources, over the full
               frame list.

BM25 token format -- confirmed, not assumed
--------------------------------------------
Inspecting vocabulary.json directly (41,236 tokens) shows the index was
built WITHOUT diacritic stripping: "ngò" and "ngo" are both present as
distinct, separate vocabulary entries, and "nước" is present while "nuoc"
is not. Folding diacritics on the query before tokenizing for BM25 would
therefore look up the WRONG term id silently. So `_bm25_tokenize` only
lowercases and splits -- it deliberately does NOT call `_strip_marks`,
unlike substring mode.

BM25 document indexing -- confirmed, not assumed
---------------------------------------------------
document_lengths.npy has 26,117 rows -- the count of ELIGIBLE windows, not
the raw 26,163 physical windows (46 are ineligible/textless). Verified by
filtering windows.jsonl to eligible==True in file order and comparing
against eligible_to_physical.npy: identical. So doc_id 0..26116 is built
here the same way -- by filtering windows.jsonl to eligible rows in file
order -- rather than trusting an assumed physical_index numbering.
"""

import json
import math
import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Literal, Optional

import numpy as np

from app import asr_text
from app import ocr_search
from app import preprocess
from app.ocr_search import _strip_marks

def _resolve_asr_release_dir() -> str :
    """<AIC_INDEX_DIR>/asr -- same fallback pattern as asr_text.py's ASR_DIR
    and ocr_search.py's OCR_DIR, so the BM25 release rides the exact road
    that already gets ASR/OCR data onto the box (AIC_INDEX_DIR is bind-mounted
    from /opt/aic/indexes -- see docker-compose.yml -- and synced from
    s3://aic2026-artifacts/indexes/ -- see deploy/p6/ssm-sync-indexes.sh).

    The OLD default computed this from the module's own __file__ location
    (three dirname() calls up to what it assumed was the repo root, then
    artifacts/asr/releases/...), which resolves to /srv/artifacts/... inside
    the deployed container -- a path nothing in the Dockerfile or
    docker-compose.yml ever creates, mounts, or copies into. BM25 was
    therefore unreachable in production regardless of what the EC2 host
    held. Same class of bug ocr_search.py's own comments describe already
    having been hit and fixed once for OCR (see OCR_DIR below).

    AIC_ASR_RELEASE_DIR still overrides the whole result, same as
    AIC_OCR_DIR overrides ocr_search.py's OCR_DIR."""
    index_dir = os.environ.get(
        "AIC_INDEX_DIR",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "indexes"))
    default = os.path.join(index_dir, "asr")
    return os.environ.get("AIC_ASR_RELEASE_DIR", default)


ASR_RELEASE_DIR = _resolve_asr_release_dir()

BM25_K1 = 1.5
BM25_B = 0.75

_BM25_TOKEN_RE = re.compile(r"[^0-9a-zA-ZÀ-ỹ]+")


class TextMatchMode(str, Enum) :
    substring = "substring"
    regex = "regex"
    bm25 = "bm25"


@dataclass
class SourceMatch :
    """One source's (asr or ocr) best result for a video: which frame it is
    on, whether that frame matched exactly or only after diacritic folding,
    and whether that frame is already in this query's visual result set."""
    match_frame : Optional[str]
    match_type  : Optional[Literal["exact", "normalized"]]
    location    : Literal["here", "elsewhere", "none"]


_NO_MATCH = SourceMatch(None, None, "none")


@dataclass
class VideoAnnotation :
    matched : bool
    score : float   # 1.0 if either source matched, else 0.0
    mode : str      # TextMatchMode value
    asr : SourceMatch
    ocr : SourceMatch


# ── combining TextHits into a SourceMatch ───────────────────────────────

def _best_match(hits : list, here : list[str]) -> SourceMatch :
    """Pick one TextHit to represent a source. Preference order: an "exact"
    match_type beats "normalized" first; within the same match_type, a frame
    already in this query's result set ("here") beats one that is not."""
    if not hits :
        return _NO_MATCH
    best = min(hits, key=lambda h : (0 if h.match_type == "exact" else 1,
                                      0 if h.frame_name in here else 1))
    location = "here" if best.frame_name in here else "elsewhere"
    return SourceMatch(best.frame_name, best.match_type, location)


# ── substring / regex: per-frame checks over the video's FULL frame list ──
# (not routed through text_lookup.lookup_text() -- see module docstring)

def _substring_hits(video_id : str, term : str, get_text) :
    """Diacritic-folded substring match, checked frame by frame instead of
    against one concatenated blob -- this is what fixes attribution and
    outside-the-result-set visibility for the sources lookup_text() does not
    cover (ASR here; both sources for regex mode, see _regex_hits below)."""
    from app import text_lookup  # deferred: text_lookup imports this module

    term_lower = term.lower()
    term_folded = _strip_marks(term).lower()
    exact, normalized = [], []
    for name in preprocess.frames_for_video(video_id) :
        text = get_text(name)
        if not text :
            continue
        if term_lower in text.lower() :
            exact.append(name)
        elif term_folded in _strip_marks(text).lower() :
            normalized.append(name)

    total = len(exact) + len(normalized)
    hits = [text_lookup.TextHit(video_id, name, "exact", rank, total)
            for rank, name in enumerate(exact, 1)]
    hits += [text_lookup.TextHit(video_id, name, "normalized", rank, total)
             for rank, name in enumerate(normalized, len(exact) + 1)]
    return hits


def _regex_hits(video_id : str, pattern : re.Pattern, get_text) :
    """Not diacritic-folded -- folding would make capture groups and
    quantifiers behave unpredictably against text that no longer resembles
    what the user typed. Every hit is "exact": there is no folded tier."""
    from app import text_lookup  # deferred: text_lookup imports this module

    matches = [name for name in preprocess.frames_for_video(video_id)
               if (text := get_text(name)) and pattern.search(text)]
    total = len(matches)
    return [text_lookup.TextHit(video_id, name, "exact", rank, total)
            for rank, name in enumerate(matches, 1)]


# ── bm25 scoring (used by text_lookup.py's ASR path) ────────────────────

_bm25_loaded = False
_bm25_unavailable_reason : Optional[str] = None
_bm25_token_to_id : dict[str, int] = {}
_bm25_posting_offsets : Optional[np.ndarray] = None
_bm25_posting_doc_ids : Optional[np.ndarray] = None
_bm25_posting_term_freqs : Optional[np.ndarray] = None
_bm25_document_lengths : Optional[np.ndarray] = None
_bm25_avgdl = 0.0
_bm25_doc_video_ids : list[str] = []
_bm25_doc_texts : list[str] = []   # unused since the Stage C rewrite dropped
                                    # snippet-building; left loaded rather than
                                    # touching _load_bm25()/its test fixtures
                                    # without a stronger reason -- see report.


def _bm25_tokenize(text : str) -> list[str] :
    """Lowercase + split on non-alphanumeric. Diacritics are deliberately
    KEPT -- see the module docstring for why folding them would break BM25
    term lookups against the real vocabulary.json."""
    return [t for t in _BM25_TOKEN_RE.split(text.lower()) if t]


def _load_bm25() -> None :
    global _bm25_loaded, _bm25_unavailable_reason, _bm25_token_to_id
    global _bm25_posting_offsets, _bm25_posting_doc_ids, _bm25_posting_term_freqs
    global _bm25_document_lengths, _bm25_avgdl, _bm25_doc_video_ids, _bm25_doc_texts

    if _bm25_loaded or (_bm25_unavailable_reason is not None) :
        return

    try :
        bm25_dir = os.path.join(ASR_RELEASE_DIR, "bm25")
        vocab_path = os.path.join(bm25_dir, "vocabulary.json")
        windows_path = os.path.join(ASR_RELEASE_DIR, "windows.jsonl")
        required = [
            vocab_path, windows_path,
            os.path.join(bm25_dir, "posting_offsets.npy"),
            os.path.join(bm25_dir, "posting_doc_ids.npy"),
            os.path.join(bm25_dir, "posting_term_frequencies.npy"),
            os.path.join(bm25_dir, "document_lengths.npy"),
        ]
        missing = [p for p in required if not os.path.exists(p)]
        if missing :
            raise FileNotFoundError(f"missing BM25 artifact(s): {missing}")

        with open(vocab_path, encoding="utf-8") as f :
            vocab = json.load(f)
        tokens = vocab["tokens"]
        token_to_id = {tok : i for i, tok in enumerate(tokens)}

        posting_offsets = np.load(os.path.join(bm25_dir, "posting_offsets.npy"))
        posting_doc_ids = np.load(os.path.join(bm25_dir, "posting_doc_ids.npy"))
        posting_term_freqs = np.load(os.path.join(bm25_dir, "posting_term_frequencies.npy"))
        document_lengths = np.load(os.path.join(bm25_dir, "document_lengths.npy"))

        # doc_id == position among ELIGIBLE windows.jsonl rows, in file order
        # (see module docstring). Read once here so scoring never re-parses
        # the 74 MB windows.jsonl per request.
        doc_video_ids : list[str] = []
        doc_texts : list[str] = []
        with open(windows_path, encoding="utf-8") as f :
            for line in f :
                row = json.loads(line)
                if not row.get("eligible") :
                    continue
                doc_video_ids.append(row["video_id"])
                doc_texts.append(row.get("retrieval_text") or "")

        if len(doc_video_ids) != len(document_lengths) :
            raise ValueError(
                f"BM25 doc count mismatch: {len(doc_video_ids)} eligible windows.jsonl "
                f"rows vs {len(document_lengths)} document_lengths.npy entries")

        avgdl = float(document_lengths.mean()) if len(document_lengths) else 0.0
        if avgdl <= 0 :
            raise ValueError("BM25 avgdl is zero -- document_lengths look empty/corrupt")

        _bm25_token_to_id = token_to_id
        _bm25_posting_offsets = posting_offsets
        _bm25_posting_doc_ids = posting_doc_ids
        _bm25_posting_term_freqs = posting_term_freqs
        _bm25_document_lengths = document_lengths
        _bm25_avgdl = avgdl
        _bm25_doc_video_ids = doc_video_ids
        _bm25_doc_texts = doc_texts
        _bm25_loaded = True
        print(f"[text_signal] BM25 index loaded: {len(tokens):,} terms · "
              f"{len(document_lengths):,} documents")
    except Exception as e :
        _bm25_unavailable_reason = f"{type(e).__name__}: {e}"
        print(f"[text_signal] BM25 unavailable ({_bm25_unavailable_reason})")


def _annotate_bm25(video_ids : list[str], query : str) -> dict[str, float] :
    """Normalized (0..1) BM25 relevance per requested video_id, 0.0 for a
    video with no match. Pure scorer -- attribution to a specific frame is
    text_lookup.py's job (it calls this), not this function's."""
    _load_bm25()
    if not _bm25_loaded :
        return {video_id : 0.0 for video_id in video_ids}

    query_tokens = sorted(set(_bm25_tokenize(query)))
    wanted = set(video_ids)
    n_docs = len(_bm25_document_lengths)
    doc_scores : dict[int, float] = {}

    for token in query_tokens :
        term_id = _bm25_token_to_id.get(token)
        if term_id is None :
            continue
        start = int(_bm25_posting_offsets[term_id])
        end = int(_bm25_posting_offsets[term_id + 1])
        doc_freq = end - start
        if doc_freq == 0 :
            continue
        idf = math.log(1.0 + (n_docs - doc_freq + 0.5) / (doc_freq + 0.5))
        doc_ids = _bm25_posting_doc_ids[start:end]
        term_freqs = _bm25_posting_term_freqs[start:end]
        for doc_id, tf in zip(doc_ids.tolist(), term_freqs.tolist()) :
            doc_len = float(_bm25_document_lengths[doc_id])
            denom = tf + BM25_K1 * (1 - BM25_B + BM25_B * doc_len / _bm25_avgdl)
            doc_scores[doc_id] = doc_scores.get(doc_id, 0.0) + idf * (tf * (BM25_K1 + 1)) / denom

    # Score each video by the MAX across its windows (a single strong hit
    # matters more than many weak ones) -- one pass over the sparse matched
    # docs, not over every window of every video.
    video_best : dict[str, float] = {}
    for doc_id, score in doc_scores.items() :
        video_id = _bm25_doc_video_ids[doc_id]
        if video_id not in wanted :
            continue
        if (video_id not in video_best) or (score > video_best[video_id]) :
            video_best[video_id] = score

    max_score = max(video_best.values(), default=0.0)
    if max_score <= 0 :
        return {video_id : 0.0 for video_id in video_ids}
    return {video_id : round(video_best.get(video_id, 0.0) / max_score, 4)
            for video_id in video_ids}


# ── entry point ──────────────────────────────────────────────────────────

def annotate_videos(
        video_ids : list[str],
        filter_query : str,
        mode : TextMatchMode,
        frame_names : dict[str, list[str]],
) -> dict[str, VideoAnnotation] :
    """Never raises. An empty query, an unmatched query, and an internal
    error all resolve to a valid (not-matched) annotation per video rather
    than propagating an exception -- the caller is a search endpoint, and a
    filtering feature must not be able to take the visual route down.

    Each video is handled in its own try/except (unchanged from before): one
    video's failure must not blank out every other video's real annotation."""
    from app import text_lookup  # deferred: text_lookup imports this module

    query = (filter_query or "").strip()
    if not query :
        return {video_id : VideoAnnotation(False, 0.0, mode.value, _NO_MATCH, _NO_MATCH)
                for video_id in video_ids}

    regex_pattern = None
    if mode == TextMatchMode.regex :
        try :
            regex_pattern = re.compile(query, re.IGNORECASE)
        except re.error :
            return {video_id : VideoAnnotation(False, 0.0, mode.value, _NO_MATCH, _NO_MATCH)
                    for video_id in video_ids}

    # One scan/postings-walk for the whole candidate set, not one per video --
    # lookup_text(scope="video") called in a loop re-pays a full OCR haystack
    # scan (ocr_search has no per-video index) or BM25 postings walk per video;
    # measured at 3.0-3.2s / 100 candidates for OCR, up to ~470ms for a common
    # BM25 term. lookup_text_batch() does the corpus-wide work exactly once and
    # partitions it, matching the earlier corpus-scope exclusion filtering.
    ocr_hits_by_video : dict[str, list] = {}
    asr_hits_by_video : dict[str, list] = {}
    if mode == TextMatchMode.bm25 :
        asr_hits_by_video = text_lookup.lookup_text_batch(query, source="asr", video_ids=video_ids)
    elif mode == TextMatchMode.substring :
        ocr_hits_by_video = text_lookup.lookup_text_batch(query, source="ocr", video_ids=video_ids)

    out : dict[str, VideoAnnotation] = {}
    for video_id in video_ids :
        here = frame_names.get(video_id, [])
        try :
            if mode == TextMatchMode.bm25 :
                asr_hits = asr_hits_by_video.get(video_id, [])
                ocr_match = _NO_MATCH
            elif mode == TextMatchMode.substring :
                asr_hits = _substring_hits(video_id, query, asr_text.get_text)
                ocr_hits = ocr_hits_by_video.get(video_id, [])
                ocr_match = _best_match(ocr_hits, here)
            elif mode == TextMatchMode.regex :
                asr_hits = _regex_hits(video_id, regex_pattern, asr_text.get_text)
                ocr_hits = _regex_hits(video_id, regex_pattern, ocr_search.get_text)
                ocr_match = _best_match(ocr_hits, here)
            else :
                raise ValueError(f"unknown TextMatchMode: {mode}")

            asr_match = _best_match(asr_hits, here)
            matched = (asr_match.location != "none") or (ocr_match.location != "none")
            out[video_id] = VideoAnnotation(matched, 1.0 if matched else 0.0, mode.value, asr_match, ocr_match)
        except Exception :
            out[video_id] = VideoAnnotation(False, 0.0, mode.value, _NO_MATCH, _NO_MATCH)
    return out


def preload() -> None :
    """Load the BM25 index at startup, same reasoning as asr_text.preload()
    and ocr_search.preload(): a broken path (or a genuinely missing index)
    should show up in /status right after warm-up, not silently on a team
    member's first live BM25 query during competition. Previously BM25 only
    loaded lazily on the first bm25-mode request, which is why a broken path
    could sit unnoticed with bm25_unavailable_reason still null -- nothing
    had triggered _load_bm25() yet.

    _load_bm25() already swallows its own failure into
    _bm25_unavailable_reason (see below) and never raises, so this needs no
    try/except of its own -- unlike ocr_route.preload()/_asr_text.preload()
    in main.py, which wrap a _load() that DOES raise on failure."""
    _load_bm25()


def status() -> dict :
    """Tell /status whether the BM25 engine is ready, without letting it fail."""
    return {
        "bm25_ready" : bool(_bm25_loaded),
        "bm25_unavailable_reason" : _bm25_unavailable_reason,
        "bm25_release_dir" : ASR_RELEASE_DIR,
        "bm25_documents" : len(_bm25_doc_video_ids) if _bm25_loaded else 0,
    }
