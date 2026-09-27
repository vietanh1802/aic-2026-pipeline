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

import functools
import json
import logging
import math
import os
import re
import unicodedata
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Literal, Optional

import numpy as np

from app import asr_text
from app import ocr_search
from app import preprocess
from app.ocr_search import _strip_marks

logger = logging.getLogger(__name__)

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

# Longest text_filter main.py accepts (Field(max_length=...)). The substring
# prefilter below compiles one regex per distinct term at roughly 0.8 ms per
# character (measured: 5 ms for 7 characters, 155 ms for 200), so this also
# bounds the worst one-off compile cost instead of letting a pasted paragraph
# pin a request thread.
TEXT_FILTER_MAX_CHARS = 200

# Multi-term substring filters ("lửa, nước" = two terms, a frame matches when it
# holds at least one). Only the split ASR / OCR filters in substring mode use
# split_terms(); bm25, regex and the legacy text_filter never do.
#
#   * separators are "," and ";" plus the full-width "，" "；" "、";
#   * an ASCII comma with an ASCII digit on BOTH sides is a decimal comma and does
#     not split, so "1,5 kg" stays one term. The same rule keeps "2018,2019" and
#     "1,5,2" whole: write "2018, 2019" or "2018;2019" to get two terms;
#   * terms are trimmed (NBSP included) and empty ones dropped;
#   * duplicates are dropped case- and accent-insensitively and the FIRST typed
#     form wins, so "nuoc, nước" is the single term "nuoc" (and is matched with
#     that spelling's exact / normalized tiers);
#   * at most MAX_FILTER_TERMS terms are kept, the rest are dropped silently. The
#     200 character request cap already bounds the summed length of the terms,
#     hence the regex compile cost, exactly as for one long term today.
MAX_FILTER_TERMS = 5
_TERM_SEPARATOR_RE = re.compile(r"(?<![0-9]),|,(?![0-9])|[;，；、]")


def split_terms(text : str) -> list[str] :
    """Terms of a multi-term substring filter, see the block comment above. An
    empty list (blank text, ",,") means the source is inactive. A text without any
    separator gives [text.strip()], which is what today's single-term code gets."""
    seen : set[str] = set()
    terms : list[str] = []
    for part in _TERM_SEPARATOR_RE.split(text or "") :
        term = part.strip()
        if not term :
            continue
        key = _strip_marks(term).lower()
        if key in seen :
            continue
        seen.add(key)
        terms.append(term)
    return terms[ : MAX_FILTER_TERMS]


# Width of the snippet shown in the Text signal popover: the window holding the
# matched words is about this many characters, its edges move to the nearest
# whitespace within _SNIPPET_EDGE_SLACK. _MAX_HIGHLIGHT_SPANS bounds the work for
# a regex or a one-letter term that matches almost every character.
SNIPPET_MAX_CHARS = 90
_SNIPPET_EDGE_SLACK = 10
_MAX_HIGHLIGHT_SPANS = 200

_BM25_TOKEN_RE = re.compile(r"[^0-9a-zA-ZÀ-ỹ]+")
# The same character class, matching the tokens themselves instead of the gaps
# between them, so a token's position in the ORIGINAL text can be found. Keep it
# in step with _BM25_TOKEN_RE (test_token_spans_match_bm25_tokenize checks it).
_BM25_TOKEN_SPAN_RE = re.compile(r"[0-9a-zA-ZÀ-ỹ]+")


class TextMatchMode(str, Enum) :
    substring = "substring"
    regex = "regex"
    bm25 = "bm25"


class OcrFilterMode(str, Enum) :
    """Modes the OCR filter accepts. OCR has no BM25 index, so unlike
    TextMatchMode there is no bm25 here: a request asking for it is rejected
    (HTTP 422) by the request model instead of silently running something else."""
    substring = "substring"
    regex = "regex"


@dataclass
class MatchDetail :
    """HOW and WHERE one source matched a video, for the Text signal popover.
    All fields are plain JSON types (asdict() and json.dumps() just work).

    snippet        -- [[text, is_hit], ...] segments of the matched text; never
                      ** markers or offsets (see the block comment further down)
    matched_terms  -- bm25: distinct query tokens found in the chosen window, in
                      query order. Multi-term substring filter (ASR or OCR, two or
                      more terms typed): the terms found on the chosen frame, in
                      typed order. [] otherwise
    terms_total    -- bm25: distinct query tokens. Multi-term substring filter: the
                      number of terms (also when only some matched, "1 of 2").
                      0 otherwise, a single-term search included
    at_s           -- best-estimate moment, in seconds from the video start
    start_s, end_s -- bm25 only: the transcript window's range; None otherwise
    time_approx    -- True only for the bm25 estimate (position inside a 60 s
                      window; frame-based sources report the frame's own time)
    rank, total_matched -- CORPUS-ONLY video rank and matched-video count (bm25
                      and OCR substring, one term or several: the rank of the
                      video's best frame, videos matching more terms first); None
                      for the per-frame ASR substring and regex scans, which
                      rank nothing
    exact_phrase   -- OCR only: the frame holds the whole phrase, not its words
                      scattered (with several terms: True only if EVERY matched
                      term matched as a whole phrase); None otherwise"""
    snippet       : list[list]
    matched_terms : list[str]
    terms_total   : int
    at_s          : float
    start_s       : Optional[float]
    end_s         : Optional[float]
    time_approx   : bool
    rank          : Optional[int]
    total_matched : Optional[int]
    exact_phrase  : Optional[bool]


@dataclass
class SourceMatch :
    """One source's (asr or ocr) best result for a video: which frame it is
    on, whether that frame matched exactly or only after diacritic folding,
    and whether that frame is already in this query's visual result set."""
    match_frame : Optional[str]
    match_type  : Optional[Literal["exact", "normalized"]]
    location    : Literal["here", "elsewhere", "none"]
    # Added last with a default so existing SourceMatch(frame, type, location)
    # calls and the shared _NO_MATCH keep working; only matched sources get one.
    detail      : Optional[MatchDetail] = None


_NO_MATCH = SourceMatch(None, None, "none")


@dataclass
class VideoAnnotation :
    matched : bool
    score : float   # 1.0 if either source matched, else 0.0
    mode : str      # TextMatchMode value
    asr : SourceMatch
    ocr : SourceMatch


# ── combining TextHits into a SourceMatch ───────────────────────────────

# Previous _choose_hit(), kept for reference (replaced by the version below, which
# adds a leading "most terms matched" component that is 0 for every single-term hit):
#
# def _choose_hit(hits : list, here : list[str]) :
#     return min(hits, key=lambda h : (0 if h.match_type == "exact" else 1,
#                                       0 if h.frame_name in here else 1))

def _choose_hit(hits : list, here : list[str]) :
    """The TextHit that represents a source. Preference order: the frame that
    matched the MOST terms first (multi-term substring filters, TextHit.term_hits;
    a hit without term_hits counts 0, so single-term hits all tie here and their
    order is exactly what it always was); then an "exact" match_type beats
    "normalized" (for several terms the tier is the worst among the frame's terms);
    then a frame already in this query's result set ("here") beats one that is not.
    Remaining ties keep the order of `hits`: earliest frame for ASR, the OCR
    ranking for OCR."""
    return min(hits, key=lambda h : (-len(h.term_hits or ()),
                                      0 if h.match_type == "exact" else 1,
                                      0 if h.frame_name in here else 1))


def _best_match(hits : list, here : list[str]) -> SourceMatch :
    """SourceMatch of the hit _choose_hit() picks (no detail: that is attached
    by annotate_videos() only for matched sources)."""
    if not hits :
        return _NO_MATCH
    best = _choose_hit(hits, here)
    location = "here" if best.frame_name in here else "elsewhere"
    return SourceMatch(best.frame_name, best.match_type, location)


# ── substring / regex: per-frame checks over the video's FULL frame list ──
# (not routed through text_lookup.lookup_text() -- see module docstring)

# Accent-tolerant prefilter for substring mode
# ---------------------------------------------
# The previous _substring_hits() folded every frame's text with _strip_marks()
# (NFD + a per-character category test) on EVERY request, whenever the plain
# lower() check failed. Profiled on 100 real videos (36,550 frames, ~1.2 KB of
# ASR text each) that was 96% of the time of annotate_videos(substring): 4-8 s
# per search, growing with how few frames matched exactly. ocr_search.py already
# warns that _strip_marks is for typed text only and that folding the corpus
# costs seconds -- this loop did exactly that per request.
#
# Instead the TERM is folded once and compiled to a regex that matches the RAW
# text directly: each folded letter becomes a class of every character that
# folds to it (a, á, ả, Ă, Ấ ...), each followed by "any number of Mn marks"
# (the old fold deleted them). That is exactly "fold(text).lower() contains
# fold(term).lower()", so the hit set is identical, and it also yields match
# positions on the ORIGINAL text for free (nothing is shifted by folding).
#
# Why the result is identical, not just close (audited by scanning every code
# point, repeated in test_text_signal.py::test_fold_scope_is_complete):
#   * fold(c).lower() is one character for every non-Mn character in
#     _FOLD_SCOPE and empty only for Mn, so text folds character by character;
#   * fold(c.lower()) == fold(c).lower() for every code point, so the exact
#     check (term_lower in text.lower()) can never hit a frame the folded check
#     misses -- classification only needs to run on prefilter hits;
#   * no character outside the scope folds into it, except the 27 in
#     _FOLD_LEAK_TARGETS. A term with any character outside the classes falls
#     back to the old per-frame fold (see the elif branch below): exact by
#     definition, slow, and only for terms in other scripts or with those 27.
#
# The Mn class must cover every Mn character in the Basic Multilingual Plane
# (1,065), not only U+0300-036F: the old fold deletes every Mn, e.g. Thai tone
# marks, and a narrower class would stop matching "a" + <Thai mark> + "b".
#
# The 920 Mn characters ABOVE the BMP (variation selectors supplement, ancient
# scripts) are deliberately left out of the class. `re` compiles a class into a
# fast table only for the BMP and tests anything above it range by range after
# every failed lookup; including them made the pattern 4-8x slower (measured on
# 100 real videos: 1.0-1.7 s against 0.23-0.31 s). Instead a frame containing
# ANY character above U+FFFF (none of the 359,714 ASR texts; a handful of OCR
# texts at most) skips the prefilter and takes the exact per-frame fold. The
# test is a UTF-16 length comparison, ~2 us per frame.

# Unicode ranges scanned to learn which characters fold (NFD, drop Mn, lower)
# to which base character: Basic Latin through Latin Extended-B / IPA /
# modifier letters, Latin Extended Additional (every precomposed Vietnamese
# letter) and Letterlike Symbols (Kelvin and Angstrom signs fold to k and a).
_FOLD_SCOPE = ((0x0000, 0x02FF), (0x1E00, 0x1EFF), (0x2100, 0x214F))

# Characters OUTSIDE _FOLD_SCOPE that fold INTO it: Greek question mark -> ";",
# "≠" -> "=", Greek/Latin Extended-C/D capitals -> IPA letters, and so on.
_FOLD_LEAK_TARGETS = frozenset(";<=>`¨´·ʹȿɀɐɑɒɜɡɥɦɪɫɬɱɽʂʇʝʞ")


def _build_fold_classes() -> dict[str, str] :
    """Folded base character -> regex class of every in-scope character that
    folds to it. Non-Mn characters only: Mn folds to nothing and is covered by
    _MARK_CLASS instead."""
    sources : dict[str, list[str]] = {}
    for start, end in _FOLD_SCOPE :
        for code in range(start, end + 1) :
            char = chr(code)
            if unicodedata.category(char) != "Mn" :
                sources.setdefault(_strip_marks(char).lower(), []).append(char)
    return {base : "[" + "".join(re.escape(char) for char in chars) + "]"
            for base, chars in sources.items() if len(base) == 1}


def _build_mark_class() -> str :
    """Regex class of every Basic-Multilingual-Plane Mn (nonspacing mark) code
    point, as ranges. Non-BMP marks are handled per frame, see above."""
    ranges : list[list[int]] = []
    for code in range(0x10000) :
        if unicodedata.category(chr(code)) != "Mn" :
            continue
        if ranges and code == ranges[-1][1] + 1 :
            ranges[-1][1] = code
        else :
            ranges.append([code, code])
    return "[" + "".join(re.escape(chr(low)) + (("-" + re.escape(chr(high))) if high > low else "")
                         for low, high in ranges) + "]"


_FOLD_CLASSES = _build_fold_classes()
_MARK_CLASS   = _build_mark_class()


@functools.lru_cache(maxsize=256)
def _folded_pattern(term_folded : str) -> Optional[re.Pattern] :
    """Compiled prefilter for an already-folded term, or None when a character
    is outside the audited scope (the caller then folds frame by frame)."""
    if any((char not in _FOLD_CLASSES) or (char in _FOLD_LEAK_TARGETS) for char in term_folded) :
        return None
    return re.compile("".join(_FOLD_CLASSES[char] + _MARK_CLASS + "*" for char in term_folded))


# Previous implementation, kept for reference (replaced by the prefilter version
# below; its per-frame logic lives on, verbatim, as the fallback branch there):
#
# def _substring_hits(video_id : str, term : str, get_text) :
#     from app import text_lookup  # deferred: text_lookup imports this module
#
#     term_lower = term.lower()
#     term_folded = _strip_marks(term).lower()
#     exact, normalized = [], []
#     for name in preprocess.frames_for_video(video_id) :
#         text = get_text(name)
#         if not text :
#             continue
#         if term_lower in text.lower() :
#             exact.append(name)
#         elif term_folded in _strip_marks(text).lower() :
#             normalized.append(name)
#
#     total = len(exact) + len(normalized)
#     hits = [text_lookup.TextHit(video_id, name, "exact", rank, total)
#             for rank, name in enumerate(exact, 1)]
#     hits += [text_lookup.TextHit(video_id, name, "normalized", rank, total)
#              for rank, name in enumerate(normalized, len(exact) + 1)]
#     return hits


# Version with the prefilter but WITHOUT the per-video memo, kept for reference
# (replaced by the memo version below; the per-text logic now lives, unchanged,
# in _classify_text()). Same output; it re-ran the regex for every frame although
# adjacent keyframes share one transcript window:
#
#     for name in preprocess.frames_for_video(video_id) :
#         text = get_text(name)
#         if not text :
#             continue
#         # A UTF-16 encoding is longer than 2 bytes per character exactly when
#         # the text has a character above U+FFFF (which _MARK_CLASS ignores).
#         if (pattern is not None) and (len(text.encode("utf-16-le", "surrogatepass")) == 2 * len(text)) :
#             if pattern.search(text) :
#                 (exact if term_lower in text.lower() else normalized).append(name)
#         elif term_lower in text.lower() :
#             exact.append(name)  # fallback: term outside the audited scope, or a non-BMP frame
#         elif term_folded in _strip_marks(text).lower() :
#             normalized.append(name)


def _classify_text(text : str, term_lower : str, term_folded : str, pattern : Optional[re.Pattern]) -> Optional[str] :
    """"exact", "normalized" or None for ONE non-empty text and one term: the
    per-frame rule of _substring_hits(), lifted out so the per-video memo (and the
    multi-term scanner) run exactly the same logic once per distinct text."""
    # A UTF-16 encoding is longer than 2 bytes per character exactly when the
    # text has a character above U+FFFF (which _MARK_CLASS ignores).
    if (pattern is not None) and (len(text.encode("utf-16-le", "surrogatepass")) == 2 * len(text)) :
        if pattern.search(text) :
            return "exact" if term_lower in text.lower() else "normalized"
        return None
    if term_lower in text.lower() :
        return "exact"  # fallback: term outside the audited scope, or a non-BMP frame
    if term_folded in _strip_marks(text).lower() :
        return "normalized"
    return None


def _substring_hits(video_id : str, term : str, get_text) :
    """Diacritic-folded substring match, checked frame by frame instead of
    against one concatenated blob -- this is what fixes attribution and
    outside-the-result-set visibility for the sources lookup_text() does not
    cover (ASR here; both sources for regex mode, see _regex_hits below).

    Output is identical to folding every frame (see the block comment above):
    the compiled pattern only decides WHICH frames match, and exact versus
    normalized is still the original `term_lower in text.lower()` check.

    Per-video memo: only about 5 percent of ASR frame texts are distinct (one
    transcript window covers many adjacent keyframes), so each distinct text is
    classified once per call. The memo lives inside the call: nothing is shared
    between requests or threads, and it holds references to the existing strings."""
    from app import text_lookup  # deferred: text_lookup imports this module

    term_lower = term.lower()
    term_folded = _strip_marks(term).lower()
    pattern = _folded_pattern(term_folded)
    exact, normalized = [], []
    kinds : dict[str, Optional[str]] = {}
    for name in preprocess.frames_for_video(video_id) :
        text = get_text(name)
        if not text :
            continue
        if text not in kinds :
            kinds[text] = _classify_text(text, term_lower, term_folded, pattern)
        kind = kinds[text]
        if kind == "exact" :
            exact.append(name)
        elif kind == "normalized" :
            normalized.append(name)

    total = len(exact) + len(normalized)
    hits = [text_lookup.TextHit(video_id, name, "exact", rank, total)
            for rank, name in enumerate(exact, 1)]
    hits += [text_lookup.TextHit(video_id, name, "normalized", rank, total)
             for rank, name in enumerate(normalized, len(exact) + 1)]
    return hits


def _substring_matches_multi(video_id : str, terms : list[str], get_text) -> list[tuple[str, tuple[Optional[str], ...]]] :
    """Multi-term ASR substring scan of ONE video: [(frame name, kinds), ...] for
    every frame that holds at least one term, in frame order (earliest first).
    kinds[i] is "exact", "normalized" or None for terms[i] on that frame, decided
    by exactly the per-text rule of _substring_hits() (_classify_text(): the same
    accent-tolerant prefilter and the same fallback for terms outside the audited
    scope or texts above the BMP), so kinds[i] is what a separate
    _substring_hits(video_id, terms[i], ...) would say for that frame.

    One walk over the frames and one per-video memo of text -> kinds, so N terms
    cost N classifications per DISTINCT text (about 5 percent of the frames), not N
    passes over every frame. A combined alternation regex is deliberately NOT used:
    measured slower than N passes (the regex engine tries every alternative at
    every position) and it cannot separate overlapping terms such as "nước" and
    "nước sôi", because finditer consumes the text a match covers."""
    plans = []
    for term in terms :
        term_folded = _strip_marks(term).lower()
        plans.append((term.lower(), term_folded, _folded_pattern(term_folded)))

    matches : list[tuple[str, tuple[Optional[str], ...]]] = []
    memo : dict[str, tuple[Optional[str], ...]] = {}
    for name in preprocess.frames_for_video(video_id) :
        text = get_text(name)
        if not text :
            continue
        kinds = memo.get(text)
        if kinds is None :
            kinds = memo[text] = tuple(_classify_text(text, lower, folded, pattern) for lower, folded, pattern in plans)
        if any(kinds) :
            matches.append((name, kinds))
    return matches


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
# Start / end of each document's window in seconds, aligned with doc ids (one
# float32 each, ~0.2 MB for 26,117 documents). Lets the scorer tell which
# window decided a video's rank and break ties by time without re-reading
# windows.jsonl.
_bm25_doc_start_s : Optional[np.ndarray] = None
_bm25_doc_end_s : Optional[np.ndarray] = None


def _bm25_tokenize(text : str) -> list[str] :
    """Lowercase + split on non-alphanumeric. Diacritics are deliberately
    KEPT -- see the module docstring for why folding them would break BM25
    term lookups against the real vocabulary.json."""
    return [t for t in _BM25_TOKEN_RE.split(text.lower()) if t]


def _load_bm25() -> None :
    global _bm25_loaded, _bm25_unavailable_reason, _bm25_token_to_id
    global _bm25_posting_offsets, _bm25_posting_doc_ids, _bm25_posting_term_freqs
    global _bm25_document_lengths, _bm25_avgdl, _bm25_doc_video_ids, _bm25_doc_texts
    global _bm25_doc_start_s, _bm25_doc_end_s

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
        #
        # Verified on the real release (aic2026-full-20260817-r01): the file is
        # grouped by video (none re-opens later), windows inside a video are in
        # strictly increasing start time, posting lists are sorted by doc id,
        # and for 300 random docs the video id, eligible_to_physical.npy,
        # document_lengths, token counts and posting term frequencies all agree
        # with the row at that position. So a smaller doc id within a video IS
        # an earlier window, and doc_id indexes the start/end arrays below.
        doc_video_ids : list[str] = []
        doc_texts : list[str] = []
        doc_start_s : list[float] = []
        doc_end_s : list[float] = []
        with open(windows_path, encoding="utf-8") as f :
            for line in f :
                row = json.loads(line)
                if not row.get("eligible") :
                    continue
                doc_video_ids.append(row["video_id"])
                doc_texts.append(row.get("retrieval_text") or "")
                doc_start_s.append(row["sample_start"] / row["sample_rate"])
                doc_end_s.append(row["sample_end"] / row["sample_rate"])

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
        _bm25_doc_start_s = np.asarray(doc_start_s, dtype=np.float32)
        _bm25_doc_end_s = np.asarray(doc_end_s, dtype=np.float32)
        _bm25_loaded = True
        print(f"[text_signal] BM25 index loaded: {len(tokens):,} terms · "
              f"{len(document_lengths):,} documents")
    except Exception as e :
        _bm25_unavailable_reason = f"{type(e).__name__}: {e}"
        print(f"[text_signal] BM25 unavailable ({_bm25_unavailable_reason})")


def _bm25_doc_scores(query : str) -> dict[int, float] :
    """Raw BM25 score of every document that shares at least one token with
    the query (doc id -> score). This is the scoring loop that used to live
    inside _annotate_bm25(), moved unchanged so the video-level scorer and the
    best-window scorer below cannot drift apart.

    Iteration order of the returned dict is NOT meaningful (it follows the
    sorted query tokens, then posting order): callers that need a tie-break
    must impose one, see _best_windows_bm25()."""
    query_tokens = sorted(set(_bm25_tokenize(query)))
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
    return doc_scores


def _best_windows_bm25(video_ids : list[str], query : str) -> dict[str, tuple[float, int]] :
    """video id -> (raw BM25 score, doc id) of the window that DECIDED that
    video's score, for the requested videos that match at all. A video is
    scored by the MAX across its windows (a single strong hit matters more
    than many weak ones), and this keeps which window that was, so the frame
    reported for the video can be the one the rank came from instead of
    whichever window happens to share a word with the query.

    Ties (equal score) go to the EARLIEST window, then the lowest doc id. The
    old `score > best` comparison let whichever document the scoring loop met
    first win, and that order follows the sorted query tokens, not time.

    Scores are raw, not normalized: normalization depends on the set of
    requested videos, see _normalize_bm25(). Returns {} when BM25 is not
    loaded."""
    _load_bm25()
    if not _bm25_loaded :
        return {}

    wanted = set(video_ids)
    best : dict[str, tuple[float, float, int]] = {}  # video -> (score, start_s, doc_id)
    for doc_id, score in _bm25_doc_scores(query).items() :
        video_id = _bm25_doc_video_ids[doc_id]
        if video_id not in wanted :
            continue
        start_s = float(_bm25_doc_start_s[doc_id])
        current = best.get(video_id)
        if (current is None) or (score > current[0]) or (
                score == current[0] and (start_s, doc_id) < (current[1], current[2])) :
            best[video_id] = (score, start_s, doc_id)
    return {video_id : (score, doc_id) for video_id, (score, _start_s, doc_id) in best.items()}


def _normalize_bm25(best : dict[str, tuple[float, int]], video_ids : list[str]) -> dict[str, float] :
    """Normalized (0..1, rounded to 4 places) score per requested video, 0.0
    for a video with no match -- the normalization _annotate_bm25() has always
    applied, kept in one place so text_lookup ranks videos with exactly the
    same numbers (rounding creates ties that are broken by video id)."""
    max_score = max((score for score, _doc_id in best.values()), default=0.0)
    if max_score <= 0 :
        return {video_id : 0.0 for video_id in video_ids}
    return {video_id : round(best[video_id][0] / max_score if video_id in best else 0.0, 4)
            for video_id in video_ids}


def _annotate_bm25(video_ids : list[str], query : str) -> dict[str, float] :
    """Normalized (0..1) BM25 relevance per requested video_id, 0.0 for a
    video with no match. Pure scorer -- attribution to a specific frame is
    text_lookup.py's job (it calls _best_windows_bm25() for that), not this
    function's. Return type and values are unchanged; it is now a thin wrapper
    over _best_windows_bm25()."""
    _load_bm25()
    if not _bm25_loaded :
        return {video_id : 0.0 for video_id in video_ids}
    return _normalize_bm25(_best_windows_bm25(video_ids, query), video_ids)


# ── popover detail: HOW and WHERE a text match happened ─────────────────
#
# Each matched source of a video carries a MatchDetail (SourceMatch.detail): a
# short snippet with the matched words marked, the moment in the video, which
# query words matched (bm25), and the corpus-only rank. Everything below is pure
# text/time arithmetic on data the lookup already produced -- no I/O -- so it
# can be unit tested without an index.
#
# Highlight positions are computed on the ORIGINAL text and shipped as
# [text, is_hit] segments, never as offsets: a Python code-point offset and a
# JavaScript UTF-16 index disagree for characters above U+FFFF (an emoji in OCR
# text), and folding (diacritics, decomposed text, "đ") would shift offsets
# computed on folded text. The substring prefilter regex already matches the
# raw text, so its spans need no mapping back.

def _has_astral(text : str) -> bool :
    """True when the text has a character above U+FFFF (a UTF-16 encoding is
    then longer than 2 bytes per character) -- the same guard _substring_hits
    uses before trusting the BMP-only mark class of _folded_pattern()."""
    return len(text.encode("utf-16-le", "surrogatepass")) != 2 * len(text)


def _token_spans(text : str) -> list[tuple[int, int]] :
    """(start, end) of every BM25 token of the ORIGINAL text. Same character
    class as _bm25_tokenize() (see _BM25_TOKEN_SPAN_RE); a token's text is
    text[start:end].lower(), exactly what _bm25_tokenize() yields."""
    return [match.span() for match in _BM25_TOKEN_SPAN_RE.finditer(text)]


def _moment_in_window(start_s : float, end_s : float, text_length : int, char_position : float) -> float :
    """Linear estimate of when a character position was spoken inside a
    transcript window, assuming an even speaking rate over the window. It is an
    ESTIMATE (the release has no word timestamps) and is clamped to the window;
    an empty text gives the window's middle."""
    low, high = min(start_s, end_s), max(start_s, end_s)
    if text_length <= 0 :
        return (low + high) / 2
    fraction = min(max(char_position / text_length, 0.0), 1.0)
    return min(max(low + fraction * (high - low), low), high)


def _clean_spans(text_length : int, spans) -> list[tuple[int, int]] :
    """Spans sorted by start, clamped to the text, empty/inverted ones dropped."""
    clean = []
    for span in spans :
        start, end = max(0, int(span[0])), min(text_length, int(span[1]))
        if start < end :
            clean.append((start, end))
    return sorted(clean)


def _snippet_bounds(text : str, spans, max_chars : int = SNIPPET_MAX_CHARS) -> tuple[int, int] :
    """[lo, hi) of the slice shown as the snippet. The window of about
    max_chars that holds the most DISTINCT matched strings wins (ties: more
    spans, then the earliest), is centred on its spans, and its edges move to
    the nearest whitespace within _SNIPPET_EDGE_SLACK characters so words are
    not cut. With no spans it is simply the first max_chars characters."""
    length = len(text)
    clean = _clean_spans(length, spans)
    if not clean :
        return 0, min(length, max_chars)

    best_key, best_first, best_last, last = None, 0, 1, 0
    for first in range(len(clean)) :
        limit = clean[first][0] + max_chars
        last = max(last, first + 1)  # a span longer than the window still counts on its own
        while last < len(clean) and clean[last][1] <= limit :
            last += 1
        inside = clean[first : last]
        key = (len({text[start : end].lower() for start, end in inside}), len(inside), -clean[first][0])
        if (best_key is None) or (key > best_key) :
            best_key, best_first, best_last = key, first, last

    first_start = clean[best_first][0]
    last_end = max(end for _start, end in clean[best_first : best_last])
    extent = min(last_end - first_start, max_chars)
    lo = max(0, first_start - (max_chars - extent) // 2)
    hi = min(length, lo + max_chars)
    lo = max(0, hi - max_chars)
    for position in range(lo, max(lo - _SNIPPET_EDGE_SLACK, 0) - 1, -1) :
        if position == 0 or text[position - 1].isspace() :
            lo = position
            break
    for position in range(hi, min(hi + _SNIPPET_EDGE_SLACK, length) + 1) :
        if position == length or text[position].isspace() :
            hi = position
            break
    return lo, hi


def _snippet_segments(text : str, spans, max_chars : int = SNIPPET_MAX_CHARS) -> list[list] :
    """The snippet as [[text, is_hit], ...]. Truncation ellipses ("…") are
    part of the text of the first / last non-hit segment (a separate non-hit
    segment when the snippet starts or ends on a hit). Whitespace runs,
    newlines included, collapse to one space AFTER slicing, so a hit that
    spans a newline keeps its boundaries. Empty text gives []."""
    if not text :
        return []
    length = len(text)
    clean = _clean_spans(length, spans)
    lo, hi = _snippet_bounds(text, clean, max_chars)

    pieces : list[list] = []
    cursor = lo
    merged : list[list[int]] = []
    for start, end in clean :
        if merged and start <= merged[-1][1] :
            merged[-1][1] = max(merged[-1][1], end)
        else :
            merged.append([start, end])
    for start, end in merged :
        start, end = max(start, lo), min(end, hi)
        if start >= end :
            continue
        if start > cursor :
            pieces.append([text[cursor : start], False])
        pieces.append([text[start : end], True])
        cursor = end
    if cursor < hi :
        pieces.append([text[cursor : hi], False])

    pieces = [[re.sub(r"\s+", " ", piece), is_hit] for piece, is_hit in pieces]
    if pieces and not pieces[0][1] :
        pieces[0][0] = pieces[0][0].lstrip()
    if pieces and not pieces[-1][1] :
        pieces[-1][0] = pieces[-1][0].rstrip()
    for previous, current in zip(pieces, pieces[1:]) :
        if previous[0].endswith(" ") and current[0].startswith(" ") :
            current[0] = current[0][1:]
    pieces = [piece for piece in pieces if piece[0]]
    if not any(piece[0].strip() for piece in pieces) :
        return []  # nothing but whitespace (a "hit" on blanks is not worth showing)

    if lo > 0 :
        if pieces[0][1] :
            pieces.insert(0, ["…", False])
        else :
            pieces[0][0] = "…" + pieces[0][0]
    if hi < length :
        if pieces[-1][1] :
            pieces.append(["…", False])
        else :
            pieces[-1][0] = pieces[-1][0] + "…"
    return pieces


def _find_spans(text : str, chunk : str, folded : bool) -> list[tuple[int, int]] :
    """Spans of `chunk` in the original text. Exact: a case-insensitive literal
    search. Folded (an accent-insensitive match): the accent-tolerant pattern of
    _substring_hits(), which matches the raw text, so nothing needs mapping
    back; no spans for a term outside its audited scope or a text with a
    character above U+FFFF (the caller then shows a snippet without highlight)."""
    if not chunk :
        return []
    if not folded :
        return [match.span() for match in re.finditer(re.escape(chunk), text, re.IGNORECASE)]
    if _has_astral(text) :
        return []
    pattern = _folded_pattern(chunk)
    return [] if pattern is None else [match.span() for match in pattern.finditer(text)]


def _substring_spans(text : str, term : str, match_type : str, scatter : bool) -> list[tuple[int, int]] :
    """Highlight spans for a substring-mode hit. scatter (OCR): when the whole
    phrase is not in the text, ocr_search matched it because every WORD is, so
    each word is highlighted on its own."""
    folded = match_type != "exact"
    phrase = _strip_marks(term).lower() if folded else term.strip()
    spans = _find_spans(text, phrase, folded)
    if (not spans) and scatter :
        for word in dict.fromkeys(ocr_search._tokenize(phrase.lower())) :
            spans += _find_spans(text, word, folded)
    return spans[:_MAX_HIGHLIGHT_SPANS]


def _regex_spans(pattern : Optional[re.Pattern], text : str) -> list[tuple[int, int]] :
    spans : list[tuple[int, int]] = []
    if pattern is None :
        return spans
    for match in pattern.finditer(text) :
        if match.end() > match.start() :
            spans.append(match.span())
        if len(spans) >= _MAX_HIGHLIGHT_SPANS :
            break
    return spans


def _describe_bm25(hit, term : str) -> MatchDetail :
    """The best window's own text, its query tokens highlighted, and the moment
    of the densest cluster estimated inside the 60 s window."""
    text = _bm25_doc_texts[hit.doc_id]
    query_tokens = list(dict.fromkeys(_bm25_tokenize(term)))
    wanted = set(query_tokens)
    spans, found = [], set()
    for start, end in _token_spans(text) :
        token = text[start : end].lower()
        if token in wanted :
            spans.append((start, end))
            found.add(token)
    lo, hi = _snippet_bounds(text, spans)
    start_s, end_s = float(_bm25_doc_start_s[hit.doc_id]), float(_bm25_doc_end_s[hit.doc_id])
    at_s = _moment_in_window(start_s, end_s, len(text), (lo + hi) / 2)
    return MatchDetail(
        snippet=_snippet_segments(text, spans), matched_terms=[t for t in query_tokens if t in found],
        terms_total=len(query_tokens), at_s=round(at_s, 3), start_s=round(start_s, 3), end_s=round(end_s, 3),
        time_approx=True, rank=hit.corpus_video_rank, total_matched=hit.corpus_videos_matched,
        exact_phrase=None)


def _describe_multi(hit, source : str, terms : list[str]) -> MatchDetail :
    """Detail of a multi-term substring match: the chosen frame's text with EVERY
    term it holds highlighted. Spans are built per term with the existing
    machinery and that term's OWN tier (an accent-folded span pattern is a superset
    of the literal one, so a term matched only after folding needs the folded
    pattern while an exact one on the same frame must stay literal), then
    concatenated: _snippet_segments() already merges overlapping and adjacent spans
    ("nước" inside "nước sôi") and _snippet_bounds() already picks the window with
    the most DISTINCT matched strings, so the window holding both terms wins over
    one holding a single term three times. matched_terms follow the typed order
    (hit.term_hits is in term order), terms_total counts every typed term.
    rank / total_matched / exact_phrase are the hit's own (see
    text_lookup.lookup_text_batch_multi); ASR carries none."""
    from app import text_lookup  # deferred: text_lookup imports this module

    text = (asr_text.get_text if source == "asr" else ocr_search.get_text)(hit.frame_name)
    spans : list[tuple[int, int]] = []
    for index, tier, _whole_phrase in hit.term_hits :
        spans += _substring_spans(text, terms[index], tier, scatter=(source == "ocr"))
    at_s = text_lookup._frame_idx(hit.frame_name) / preprocess.fps_for_video(hit.video_id)
    return MatchDetail(
        snippet=_snippet_segments(text, spans), matched_terms=[terms[index] for index, _tier, _phrase in hit.term_hits],
        terms_total=len(terms), at_s=round(at_s, 3), start_s=None, end_s=None, time_approx=False,
        rank=hit.corpus_video_rank, total_matched=hit.corpus_videos_matched, exact_phrase=hit.exact_phrase)


def describe_match(hit, source : str, mode : TextMatchMode, term : str,
                   pattern : Optional[re.Pattern] = None, terms : Optional[list[str]] = None) -> MatchDetail :
    """MatchDetail for the TextHit chosen to represent `source` ("asr" or
    "ocr") of one video. Frame-based sources (substring, regex, OCR) report the
    frame's own time; bm25 reports the estimate described in _describe_bm25().
    rank / total_matched are the corpus-only video rank the hit carries (bm25
    and OCR substring), None for the per-frame substring/regex ASR scans, which
    rank nothing. May raise on inconsistent input: annotate_videos() isolates
    that per source.

    terms: the typed terms of a multi-term substring filter. A substring hit that
    carries term_hits AND comes with its terms is described by _describe_multi();
    every other call is exactly what it always was."""
    from app import text_lookup  # deferred: text_lookup imports this module

    if mode == TextMatchMode.bm25 :
        return _describe_bm25(hit, term)
    if (mode == TextMatchMode.substring) and (terms is not None) and (hit.term_hits is not None) :
        return _describe_multi(hit, source, terms)

    text = (asr_text.get_text if source == "asr" else ocr_search.get_text)(hit.frame_name)
    if mode == TextMatchMode.regex :
        spans = _regex_spans(pattern, text)
    else :
        spans = _substring_spans(text, term, hit.match_type, scatter=(source == "ocr"))
    at_s = text_lookup._frame_idx(hit.frame_name) / preprocess.fps_for_video(hit.video_id)
    return MatchDetail(
        snippet=_snippet_segments(text, spans), matched_terms=[], terms_total=0, at_s=round(at_s, 3),
        start_s=None, end_s=None, time_approx=False, rank=hit.corpus_video_rank,
        total_matched=hit.corpus_videos_matched, exact_phrase=hit.exact_phrase)


# ── entry points: independent ASR / OCR filters, and the legacy single filter ──
#
# One text_filter + one text_filter_mode used to drive BOTH sources. The split
# entry point below runs each source with its OWN query and mode; the legacy
# annotate_videos() is now a thin mapping onto it, so there is one engine and
# the old behaviour cannot drift (test_text_signal.py keeps a verbatim copy of
# the previous implementation and asserts identical output, detail included).

def _mode_label(asr_mode : Optional[Enum], ocr_mode : Optional[Enum]) -> str :
    """VideoAnnotation.mode / text_filter_mode of the split path: the active
    source's own mode value when only one source is active, "mixed" when both
    are (their modes are then in asr_filter_mode / ocr_filter_mode), "" when
    neither is. A mode of None means that source is inactive."""
    if (asr_mode is not None) and (ocr_mode is not None) :
        return "mixed"
    active = asr_mode if asr_mode is not None else ocr_mode
    return active.value if active is not None else ""


def _asr_multi_hits(video_id : str, terms : list[str], get_text) -> list :
    """TextHits of one video for the multi-term ASR substring filter: one hit per
    frame that holds at least one term, in frame order, so _choose_hit()'s
    remaining ties go to the EARLIEST frame. match_type is the worst tier among the
    frame's terms and term_hits lists (term index, tier, None) for each term found
    (ASR has no whole-phrase flag). rank / total_matched are the position among and
    the number of the video's matching frames; nothing ranks ASR substring videos,
    so the corpus ranks stay None."""
    from app import text_lookup  # deferred: text_lookup imports this module

    matches = _substring_matches_multi(video_id, terms, get_text)
    hits = []
    for rank, (name, kinds) in enumerate(matches, 1) :
        term_hits = tuple((index, kind, None) for index, kind in enumerate(kinds) if kind)
        tier = "normalized" if any(kind == "normalized" for _index, kind, _phrase in term_hits) else "exact"
        hits.append(text_lookup.TextHit(video_id, name, tier, rank, len(matches), term_hits=term_hits))
    return hits


def _asr_hits(video_id : str, query : str, mode : TextMatchMode, pattern : Optional[re.Pattern],
              batch : dict[str, list], terms : Optional[list[str]] = None) -> list :
    """TextHits of one video for the ASR source. bm25 comes from the
    corpus-wide batch (one postings walk for all candidates), substring and
    regex scan the video's own frames. terms (substring only): the two or more
    terms of a multi-term filter, scanned by _asr_multi_hits(); None is today's
    single-phrase scan of `query`."""
    if mode == TextMatchMode.bm25 :
        return batch.get(video_id, [])
    if mode == TextMatchMode.substring :
        if terms is not None :
            return _asr_multi_hits(video_id, terms, asr_text.get_text)
        return _substring_hits(video_id, query, asr_text.get_text)
    if mode == TextMatchMode.regex :
        return _regex_hits(video_id, pattern, asr_text.get_text)
    raise ValueError(f"unknown ASR mode: {mode}")


def _ocr_hits(video_id : str, query : str, mode : TextMatchMode, pattern : Optional[re.Pattern],
              batch : dict[str, list]) -> list :
    """TextHits of one video for the OCR source: substring comes from the
    corpus-wide batch (ocr_search scans every frame once), regex scans the
    video's own frames. There is no bm25 for OCR."""
    if mode == TextMatchMode.substring :
        return batch.get(video_id, [])
    if mode == TextMatchMode.regex :
        return _regex_hits(video_id, pattern, ocr_search.get_text)
    raise ValueError(f"unknown OCR mode: {mode}")


# ── multi-term substring filters: where each rule lives ─────────────────────
#
# "lửa, nước" in the split ASR / OCR filters, substring mode only (multi_term=True):
#
#   terms          split_terms()       separators, decimal comma, duplicates, cap of five
#   plan / source  _plan_terms()       no terms = inactive, one = today's single-term code, two or more = below
#   ASR scan       _asr_multi_hits()   one hit per frame, from _substring_matches_multi() (per-text memo,
#                                      the per-text rule of _substring_hits(), see _classify_text())
#   OCR scan       text_lookup.lookup_text_batch_multi()   on ocr_search.search_terms(), no OCR_LIMIT row cap
#   best frame     _choose_hit()       most terms, then exact, then "here", then list order (ASR: earliest
#                                      frame; OCR: whole-phrase terms, then shorter text)
#   detail         describe_match(terms=) -> _describe_multi()   matched_terms in typed order, terms_total
#
# bm25, regex and the legacy text_filter never split; one term after splitting is today's code, byte for byte.

def _plan_terms(query : str) -> tuple[Optional[str], Optional[list[str]]] :
    """How ONE substring source is searched when multi_term is on, from its
    stripped, non-empty query: (query, terms).

      no terms at all (",,")   -> (None, None): the source is inactive
      exactly one term         -> (that term, None): today's single-term code runs
                                  with it. A query without a separator gives the
                                  very same string back; "lửa," gives "lửa"
      two or more terms        -> (query, terms): the multi-term scanners run"""
    terms = split_terms(query)
    if not terms :
        return None, None
    if len(terms) == 1 :
        return terms[0], None
    return query, terms


def annotate_videos_split(
        video_ids : list[str],
        frame_names : dict[str, list[str]],
        asr_query : Optional[str],
        asr_mode : Optional[Enum],
        ocr_query : Optional[str],
        ocr_mode : Optional[Enum],
        mode_label : Optional[str] = None,
        multi_term : bool = False,
) -> dict[str, VideoAnnotation] :
    """Annotate videos with an ASR filter and an OCR filter that are
    independent: each has its own query and mode (asr: substring | regex |
    bm25, ocr: substring | regex -- TextMatchMode or OcrFilterMode members, only
    their .value is read).

    A source is INACTIVE, and yields _NO_MATCH for every video, when its query
    is empty after strip, its mode is None or one OCR cannot do (bm25), or its
    regex does not compile (only that source turns off; the other still runs).
    mode_label becomes VideoAnnotation.mode (default: _mode_label() of the
    requested sources). Each source builds its match detail with ITS OWN mode,
    term and pattern.

    multi_term (default False, which is exactly the behaviour before it existed;
    the legacy annotate_videos() always passes False): a source in SUBSTRING mode
    reads its query as a list of terms, see split_terms() and _plan_terms(). A
    frame matches when it holds at least one term, the video's frame is the one
    with the most terms, and the detail lists which terms it found (MatchDetail).
    bm25 and regex sources ignore the flag. A query that splits into no terms
    (",,") makes that source inactive, like an invalid regex: the label still
    comes from the requested modes.

    Never raises, and each video is handled in its own try/except: one video's
    failure must not blank out every other video's real annotation. A detail
    failure leaves that source's match intact without detail, logged once per
    call."""
    from app import text_lookup  # deferred: text_lookup imports this module

    asr_query = (asr_query or "").strip()
    ocr_query = (ocr_query or "").strip()
    asr_active = TextMatchMode(asr_mode.value) if (asr_mode is not None and asr_query) else None
    ocr_active = None
    if (ocr_mode is not None) and ocr_query and ocr_mode.value in (OcrFilterMode.substring.value, OcrFilterMode.regex.value) :
        ocr_active = TextMatchMode(ocr_mode.value)
    label = mode_label if mode_label is not None else _mode_label(asr_active, ocr_active)

    # A regex that does not compile turns THAT source off, not the whole call:
    # the label above was taken from the requested modes, so the response still
    # says the filter was active (an empty result), like an invalid legacy regex.
    asr_pattern = ocr_pattern = None
    if asr_active == TextMatchMode.regex :
        try :
            asr_pattern = re.compile(asr_query, re.IGNORECASE)
        except re.error :
            asr_active = None
    if ocr_active == TextMatchMode.regex :
        try :
            ocr_pattern = re.compile(ocr_query, re.IGNORECASE)
        except re.error :
            ocr_active = None

    # Multi-term substring: only when the caller asked (annotate_request's split
    # branch), only for a source in substring mode. asr_terms / ocr_terms stay None
    # for a single term, which then runs today's code below with that one term.
    asr_terms : Optional[list[str]] = None
    ocr_terms : Optional[list[str]] = None
    if multi_term and (asr_active == TextMatchMode.substring) :
        asr_query, asr_terms = _plan_terms(asr_query)
        if asr_query is None :
            asr_active = None
    if multi_term and (ocr_active == TextMatchMode.substring) :
        ocr_query, ocr_terms = _plan_terms(ocr_query)
        if ocr_query is None :
            ocr_active = None

    if (asr_active is None) and (ocr_active is None) :
        return {video_id : VideoAnnotation(False, 0.0, label, _NO_MATCH, _NO_MATCH) for video_id in video_ids}

    # One scan/postings-walk for the whole candidate set, not one per video --
    # lookup_text(scope="video") called in a loop re-pays a full OCR haystack
    # scan (ocr_search has no per-video index) or BM25 postings walk per video;
    # measured at 3.0-3.2s / 100 candidates for OCR, up to ~470ms for a common
    # BM25 term. lookup_text_batch() does the corpus-wide work exactly once and
    # partitions it, matching the earlier corpus-scope exclusion filtering.
    asr_batch : dict[str, list] = {}
    ocr_batch : dict[str, list] = {}
    if asr_active == TextMatchMode.bm25 :
        asr_batch = text_lookup.lookup_text_batch(asr_query, source="asr", video_ids=video_ids)
    if (ocr_active == TextMatchMode.substring) and (ocr_terms is None) :
        ocr_batch = text_lookup.lookup_text_batch(ocr_query, source="ocr", video_ids=video_ids)
    elif ocr_active == TextMatchMode.substring :
        # Multi-term OCR. lookup_text_batch_multi() already logs and returns "no
        # hits" when its own scan fails; this second guard is for anything else it
        # could raise, so a broken OCR side yields "no OCR match" for every video
        # (logged once for the request) instead of failing the whole annotation.
        try :
            ocr_batch = text_lookup.lookup_text_batch_multi(ocr_terms, source="ocr", video_ids=video_ids)
        except Exception :
            logger.exception("[text_signal] multi-term OCR lookup failed (OCR reported as no match)")
            ocr_batch = {}

    out : dict[str, VideoAnnotation] = {}
    detail_failure_logged = False
    video_failure_logged = False
    for video_id in video_ids :
        here = frame_names.get(video_id, [])
        try :
            # Previous: asr_hits = _asr_hits(video_id, asr_query, asr_active, asr_pattern, asr_batch) if ... (same call, no terms)
            asr_hits = _asr_hits(video_id, asr_query, asr_active, asr_pattern, asr_batch, asr_terms) if asr_active is not None else []
            ocr_hits = _ocr_hits(video_id, ocr_query, ocr_active, ocr_pattern, ocr_batch) if ocr_active is not None else []
            asr_match = _best_match(asr_hits, here)
            ocr_match = _best_match(ocr_hits, here)

            # The detail is decoration on an annotation that is already right:
            # each source has its own try/except, so a failure (an odd text, a
            # pattern) leaves that source without detail instead of blanking the
            # video. Built only for matched sources and only for the ONE chosen
            # hit, so it adds nothing for non-matching videos or extra frames.
            # Each source describes its match with its own mode, term, pattern.
            for source, match, hits, source_mode, source_query, source_pattern, source_terms in (
                    ("asr", asr_match, asr_hits, asr_active, asr_query, asr_pattern, asr_terms),
                    ("ocr", ocr_match, ocr_hits, ocr_active, ocr_query, ocr_pattern, ocr_terms)) :
                if match.location == "none" :
                    continue
                try :
                    chosen = _choose_hit(hits, here)
                    if source_terms is None :
                        match.detail = describe_match(chosen, source, source_mode, source_query, source_pattern)
                    else :
                        match.detail = describe_match(chosen, source, source_mode, source_query, source_pattern, terms=source_terms)
                except Exception :
                    if not detail_failure_logged :  # once per call, not once per video
                        logger.exception("[text_signal] match detail failed (annotation kept without it)")
                        detail_failure_logged = True

            matched = (asr_match.location != "none") or (ocr_match.location != "none")
            out[video_id] = VideoAnnotation(matched, 1.0 if matched else 0.0, label, asr_match, ocr_match)
        except Exception :
            # One video's failure blanks that video only. Logged once per call
            # (it used to be silent): with the multi-term scanners a bug here would
            # otherwise turn every ASR match into "no match" without a trace.
            if not video_failure_logged :
                logger.exception("[text_signal] video annotation failed (reported as no match)")
                video_failure_logged = True
            out[video_id] = VideoAnnotation(False, 0.0, label, _NO_MATCH, _NO_MATCH)
    return out


def annotate_videos(
        video_ids : list[str],
        filter_query : str,
        mode : TextMatchMode,
        frame_names : dict[str, list[str]],
) -> dict[str, VideoAnnotation] :
    """The legacy single-filter entry point, unchanged in signature and output
    (SourceMatch.detail included): one query and one mode drive both sources.

      bm25      -> ASR only (OCR was never part of bm25 mode)
      substring -> ASR substring scan + OCR substring lookup
      regex     -> ASR and OCR with the same pattern; an invalid pattern turns
                   both sources off, i.e. every video comes back not matched
      empty query -> every video not matched

    Never raises; see annotate_videos_split() for the per-video isolation."""
    if mode == TextMatchMode.bm25 :
        asr_mode, ocr_mode = TextMatchMode.bm25, None
    else :
        asr_mode, ocr_mode = mode, mode
    return annotate_videos_split(video_ids, frame_names, filter_query, asr_mode, filter_query, ocr_mode,
                                 mode_label=mode.value, multi_term=False)  # the legacy path never splits on commas


# Previous body of annotate_videos(), kept for reference (replaced by the mapping
# above onto annotate_videos_split(), which runs the same per-source logic for
# any combination of ASR and OCR modes; test_text_signal.py holds a live copy as
# the equivalence oracle):
#
# def annotate_videos(video_ids, filter_query, mode, frame_names) :
#     from app import text_lookup  # deferred: text_lookup imports this module
#
#     query = (filter_query or "").strip()
#     if not query :
#         return {video_id : VideoAnnotation(False, 0.0, mode.value, _NO_MATCH, _NO_MATCH)
#                 for video_id in video_ids}
#
#     regex_pattern = None
#     if mode == TextMatchMode.regex :
#         try :
#             regex_pattern = re.compile(query, re.IGNORECASE)
#         except re.error :
#             return {video_id : VideoAnnotation(False, 0.0, mode.value, _NO_MATCH, _NO_MATCH)
#                     for video_id in video_ids}
#
#     ocr_hits_by_video : dict[str, list] = {}
#     asr_hits_by_video : dict[str, list] = {}
#     if mode == TextMatchMode.bm25 :
#         asr_hits_by_video = text_lookup.lookup_text_batch(query, source="asr", video_ids=video_ids)
#     elif mode == TextMatchMode.substring :
#         ocr_hits_by_video = text_lookup.lookup_text_batch(query, source="ocr", video_ids=video_ids)
#
#     out : dict[str, VideoAnnotation] = {}
#     detail_failure_logged = False
#     for video_id in video_ids :
#         here = frame_names.get(video_id, [])
#         try :
#             ocr_hits : list = []
#             if mode == TextMatchMode.bm25 :
#                 asr_hits = asr_hits_by_video.get(video_id, [])
#                 ocr_match = _NO_MATCH
#             elif mode == TextMatchMode.substring :
#                 asr_hits = _substring_hits(video_id, query, asr_text.get_text)
#                 ocr_hits = ocr_hits_by_video.get(video_id, [])
#                 ocr_match = _best_match(ocr_hits, here)
#             elif mode == TextMatchMode.regex :
#                 asr_hits = _regex_hits(video_id, regex_pattern, asr_text.get_text)
#                 ocr_hits = _regex_hits(video_id, regex_pattern, ocr_search.get_text)
#                 ocr_match = _best_match(ocr_hits, here)
#             else :
#                 raise ValueError(f"unknown TextMatchMode: {mode}")
#
#             asr_match = _best_match(asr_hits, here)
#             for source, match, hits in (("asr", asr_match, asr_hits), ("ocr", ocr_match, ocr_hits)) :
#                 if match.location == "none" :
#                     continue
#                 try :
#                     match.detail = describe_match(_choose_hit(hits, here), source, mode, query, regex_pattern)
#                 except Exception :
#                     if not detail_failure_logged :
#                         logger.exception("[text_signal] match detail failed (annotation kept without it)")
#                         detail_failure_logged = True
#
#             matched = (asr_match.location != "none") or (ocr_match.location != "none")
#             out[video_id] = VideoAnnotation(matched, 1.0 if matched else 0.0, mode.value, asr_match, ocr_match)
#         except Exception :
#             out[video_id] = VideoAnnotation(False, 0.0, mode.value, _NO_MATCH, _NO_MATCH)
#     return out


@dataclass
class RequestAnnotation :
    """What the /ensemble-search endpoint copies into its response: the
    annotations (video id -> asdict(VideoAnnotation), or None when no filter is
    active) plus the flags and labels. text_filter_active is True when ANY
    source is active, split or legacy."""
    video_annotations : Optional[dict]
    text_filter_active : bool
    text_filter_mode : Optional[str]
    asr_filter_active : bool
    ocr_filter_active : bool
    asr_filter_mode : Optional[str]
    ocr_filter_mode : Optional[str]


def annotate_request(
        asr_filter : str,
        asr_filter_mode : TextMatchMode,
        ocr_filter : str,
        ocr_filter_mode : OcrFilterMode,
        legacy_filter : str,
        legacy_mode : TextMatchMode,
        results : list[dict],
) -> RequestAnnotation :
    """Routing of the request's text filters, on primitives so it can be tested
    without importing main.py (which loads torch and FAISS).

    If asr_filter or ocr_filter is non-empty after strip, the split path runs
    and the legacy fields are ignored. Otherwise the legacy text_filter runs
    EXACTLY as before (this protects old callers, and the deploy window in which
    an old frontend talks to the new backend). `results` are the visual result
    rows ("video" and "name" keys); nothing is removed or reordered.

    Only the split path reads a substring filter as a list of terms ("lửa, nước",
    see split_terms()); bm25, regex and the legacy text_filter never do. The flags
    of the response follow the request as typed: a filter that splits into no terms
    (",,") is still reported active with its mode, but nothing is searched for that
    source (every video comes back with no match for it), exactly like an invalid
    regex."""
    asr_active = bool((asr_filter or "").strip())
    ocr_active = bool((ocr_filter or "").strip())
    legacy_active = bool((legacy_filter or "").strip())
    if not (asr_active or ocr_active or legacy_active) :
        return RequestAnnotation(None, False, None, False, False, None, None)

    frame_names : dict[str, list[str]] = {}
    for frame in results :
        frame_names.setdefault(frame["video"], []).append(frame["name"])
    video_ids = list(frame_names.keys())

    if asr_active or ocr_active :
        asr_requested = asr_filter_mode if asr_active else None
        ocr_requested = ocr_filter_mode if ocr_active else None
        label = _mode_label(asr_requested, ocr_requested)
        # Previous: annotate_videos_split(video_ids, frame_names, asr_filter, asr_requested,
        #                                 ocr_filter, ocr_requested, mode_label=label)
        # multi_term=True is what turns "lửa, nước" into two terms in substring mode.
        annotations = annotate_videos_split(video_ids, frame_names, asr_filter, asr_requested,
                                            ocr_filter, ocr_requested, mode_label=label, multi_term=True)
        return RequestAnnotation(
            video_annotations={vid : asdict(annotation) for vid, annotation in annotations.items()},
            text_filter_active=True, text_filter_mode=label, asr_filter_active=asr_active,
            ocr_filter_active=ocr_active, asr_filter_mode=asr_filter_mode.value if asr_active else None,
            ocr_filter_mode=ocr_filter_mode.value if ocr_active else None)

    annotations = annotate_videos(video_ids, legacy_filter, legacy_mode, frame_names)
    return RequestAnnotation(
        video_annotations={vid : asdict(annotation) for vid, annotation in annotations.items()},
        text_filter_active=True, text_filter_mode=legacy_mode.value, asr_filter_active=False,
        ocr_filter_active=False, asr_filter_mode=None, ocr_filter_mode=None)


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
