# backend/app/text_signal.py
# -*- coding: utf-8 -*-
"""
text_signal.py — per-video text-match annotation engine (ASR + OCR)
=====================================================================

Sits between the raw text data (asr_text.py + ocr_search.py) and the
ensemble endpoint. Given the video_ids in a result set and a filter query,
returns a per-video VideoAnnotation: whether/how well the video's text
matches, which source(s) matched, and a short highlighted snippet. This is
PURELY ADDITIVE metadata -- it never removes a frame or changes a rank; see
main.py's ensemble endpoint for how the response is annotated.

Three modes, `TextMatchMode`:

  substring -- diacritic-folded, case-insensitive substring match. Cheap,
               forgiving of accent typos.
  regex     -- `re.search(query, text, re.IGNORECASE)`. Diacritics are NOT
               folded (the pattern is matched against the text as-is) --
               folding would make capture groups and quantifiers behave
               unpredictably against a string that no longer resembles what
               the user typed.
  bm25      -- ranked relevance against the prebuilt ASR BM25 index
               (<AIC_INDEX_DIR>/asr/bm25/). Falls back to substring, with a
               note in the snippet, if that index isn't present.

BM25 token format -- confirmed, not assumed
--------------------------------------------
Inspecting vocabulary.json directly (41,236 tokens) shows the index was
built WITHOUT diacritic stripping: "ngò" and "ngo" are both present as
distinct, separate vocabulary entries, and "nước" is present while "nuoc"
is not. Folding diacritics on the query before tokenizing for BM25 would
therefore look up the WRONG term id silently. So `_bm25_tokenize` only
lowercases and splits -- it deliberately does NOT call `_strip_marks`,
unlike the substring mode above it.

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
from typing import Optional

import numpy as np

from app import asr_text
from app import ocr_search
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
BM25_MATCH_THRESHOLD = 0.05
SNIPPET_WINDOW = 40  # chars before/after the match

_BM25_TOKEN_RE = re.compile(r"[^0-9a-zA-ZÀ-ỹ]+")
# Matches the frame filename convention confirmed against main.py's own
# _frame_idx_from_name(): the last "-"-separated numeric component, before
# the extension, is the frame index -- used only to sort frames of one video
# into chronological order before dedup, never to identify the video itself.
_FRAME_IDX_RE = re.compile(r"-(\d+)\.\w+$")


class TextMatchMode(str, Enum) :
    substring = "substring"
    regex = "regex"
    bm25 = "bm25"


@dataclass
class VideoAnnotation :
    matched : bool
    score : float          # 0.0-1.0, normalized within the result set
    sources : list[str]    # ["asr"], ["ocr"], ["asr", "ocr"], or []
    snippets : list[str]   # up to 2 excerpts, matched span wrapped in **..**
    mode : str              # TextMatchMode value


# ── shared helpers ──────────────────────────────────────────────────────

def _frame_sort_key(name : str) :
    m = _FRAME_IDX_RE.search(name)
    return int(m.group(1)) if m else float("inf")


def _sorted_frames(frames : list[str]) -> list[str] :
    return sorted(frames, key=_frame_sort_key)


def _concat_dedup_adjacent(texts : list[str]) -> str :
    """Join per-frame text in chronological order, dropping empty values and
    a fragment that is identical to the one right before it. Adjacent frames
    within the same ASR window (or the same OCR-visible text) repeat heavily
    -- this keeps concatenated video-level text and its snippets readable."""
    parts : list[str] = []
    prev = None
    for text in texts :
        if not text :
            continue
        if text == prev :
            continue
        parts.append(text)
        prev = text
    return " ".join(parts)


def _make_snippet(text : str, start : int, end : int, window : int = SNIPPET_WINDOW) -> str :
    prefix = text[max(0, start - window):start]
    match_text = text[start:end]
    suffix = text[end:end + window]
    if start - window > 0 :
        prefix = "..." + prefix
    if end + window < len(text) :
        suffix = suffix + "..."
    return f"{prefix}**{match_text}**{suffix}"


def _video_texts(video_id : str, frame_names : dict[str, list[str]]) -> tuple[str, str] :
    """(ocr_text, asr_text) concatenated across this video's frames in the
    current result set, chronologically ordered and adjacent-deduped."""
    frames = _sorted_frames(frame_names.get(video_id, []))
    ocr_text = _concat_dedup_adjacent([ocr_search.get_text(f) for f in frames])
    asr_text_value = _concat_dedup_adjacent([asr_text.get_text(f) for f in frames])
    return ocr_text, asr_text_value


# ── substring mode ──────────────────────────────────────────────────────

def _annotate_substring(video_ids : list[str], query : str,
                         frame_names : dict[str, list[str]], mode : TextMatchMode) -> dict[str, VideoAnnotation] :
    query_stripped = _strip_marks(query).lower()
    out : dict[str, VideoAnnotation] = {}
    for video_id in video_ids :
        try :
            ocr_text, asr_text_value = _video_texts(video_id, frame_names)
            sources, snippets = [], []

            # _strip_marks is a 1:1 char replacement (đ/Đ) plus removal of
            # combining marks after NFD decomposition -- both preserve string
            # length, so an index found in the stripped text is the SAME
            # index in the original, letting the snippet keep real diacritics.
            if asr_text_value :
                idx = _strip_marks(asr_text_value).lower().find(query_stripped)
                if idx != -1 :
                    sources.append("asr")
                    snippets.append(_make_snippet(asr_text_value, idx, idx + len(query_stripped)))
            if ocr_text :
                idx = _strip_marks(ocr_text).lower().find(query_stripped)
                if idx != -1 :
                    sources.append("ocr")
                    snippets.append(_make_snippet(ocr_text, idx, idx + len(query_stripped)))

            matched = bool(sources)
            out[video_id] = VideoAnnotation(matched, 1.0 if matched else 0.0, sources, snippets, mode.value)
        except Exception as e :
            out[video_id] = VideoAnnotation(False, 0.0, [], [f"Error: {e}"], mode.value)
    return out


# ── regex mode ───────────────────────────────────────────────────────────

def _annotate_regex(video_ids : list[str], query : str,
                     frame_names : dict[str, list[str]], mode : TextMatchMode) -> dict[str, VideoAnnotation] :
    try :
        pattern = re.compile(query, re.IGNORECASE)
    except re.error as e :
        error_annotation = VideoAnnotation(False, 0.0, [], [f"Invalid regex — {e}"], mode.value)
        return {video_id : error_annotation for video_id in video_ids}

    out : dict[str, VideoAnnotation] = {}
    for video_id in video_ids :
        try :
            ocr_text, asr_text_value = _video_texts(video_id, frame_names)
            sources, snippets = [], []

            asr_match = pattern.search(asr_text_value) if asr_text_value else None
            if asr_match :
                sources.append("asr")
                snippets.append(_make_snippet(asr_text_value, asr_match.start(), asr_match.end()))
            ocr_match = pattern.search(ocr_text) if ocr_text else None
            if ocr_match :
                sources.append("ocr")
                snippets.append(_make_snippet(ocr_text, ocr_match.start(), ocr_match.end()))

            matched = bool(sources)
            out[video_id] = VideoAnnotation(matched, 1.0 if matched else 0.0, sources, snippets, mode.value)
        except Exception as e :
            out[video_id] = VideoAnnotation(False, 0.0, [], [f"Error: {e}"], mode.value)
    return out


# ── bm25 mode ────────────────────────────────────────────────────────────

_bm25_loaded = False
_bm25_unavailable_reason : Optional[str] = None
_bm25_token_to_id : dict[str, int] = {}
_bm25_posting_offsets : Optional[np.ndarray] = None
_bm25_posting_doc_ids : Optional[np.ndarray] = None
_bm25_posting_term_freqs : Optional[np.ndarray] = None
_bm25_document_lengths : Optional[np.ndarray] = None
_bm25_avgdl = 0.0
_bm25_doc_video_ids : list[str] = []
_bm25_doc_texts : list[str] = []


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
        print(f"[text_signal] BM25 unavailable ({_bm25_unavailable_reason}) — "
              f"falling back to substring mode")


def _annotate_bm25(video_ids : list[str], query : str,
                    frame_names : dict[str, list[str]], mode : TextMatchMode) -> dict[str, VideoAnnotation] :
    _load_bm25()
    if not _bm25_loaded :
        fallback = _annotate_substring(video_ids, query, frame_names, mode)
        for annotation in fallback.values() :
            annotation.snippets.append("(BM25 unavailable, using substring)")
        return fallback

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
    video_best : dict[str, tuple[float, int]] = {}
    for doc_id, score in doc_scores.items() :
        video_id = _bm25_doc_video_ids[doc_id]
        if video_id not in wanted :
            continue
        if (video_id not in video_best) or (score > video_best[video_id][0]) :
            video_best[video_id] = (score, doc_id)

    max_score = max((s for s, _ in video_best.values()), default=0.0)

    out : dict[str, VideoAnnotation] = {}
    for video_id in video_ids :
        try :
            if (video_id in video_best) and (max_score > 0) :
                raw_score, doc_id = video_best[video_id]
                normalized = raw_score / max_score
                matched = normalized >= BM25_MATCH_THRESHOLD
                snippet = _bm25_doc_texts[doc_id][:100]
                out[video_id] = VideoAnnotation(
                    matched=matched, score=round(normalized, 4),
                    sources=["asr"] if matched else [],
                    snippets=[snippet] if matched else [],
                    mode=mode.value)
            else :
                out[video_id] = VideoAnnotation(False, 0.0, [], [], mode.value)
        except Exception as e :
            out[video_id] = VideoAnnotation(False, 0.0, [], [f"Error: {e}"], mode.value)
    return out


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
    filtering feature must not be able to take the visual route down."""
    query = (filter_query or "").strip()
    if not query :
        return {video_id : VideoAnnotation(False, 0.0, [], [], mode.value) for video_id in video_ids}

    try :
        if mode == TextMatchMode.substring :
            return _annotate_substring(video_ids, query, frame_names, mode)
        if mode == TextMatchMode.regex :
            return _annotate_regex(video_ids, query, frame_names, mode)
        if mode == TextMatchMode.bm25 :
            return _annotate_bm25(video_ids, query, frame_names, mode)
        raise ValueError(f"unknown TextMatchMode: {mode}")
    except Exception as e :
        return {video_id : VideoAnnotation(False, 0.0, [], [f"Error: {e}"], mode.value)
                for video_id in video_ids}


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
