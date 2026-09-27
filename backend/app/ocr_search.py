# backend/app/ocr_search.py
# -*- coding: utf-8 -*-
"""
ocr_search.py — find keyframes by the TEXT VISIBLE ON SCREEN
=============================================================

A standalone retrieval route with no FAISS/BEiT3/CLIP involvement. Give it a
phrase, get back the frames where Vintern OCR read exactly that phrase.

Why this is kept separate from the visual route
-----------------------------------------------
Measured over the 25 preliminary-round queries (notebook 78):

  * 13/25 answer frames carry NO text at all  -> this route cannot help there
  * 12/25 do carry text, and when the typed phrase narrows the corpus to <= 4
    images, the correct video comes back RANKED FIRST — 6 times out of 6

So it does not replace the visual route, but when the screen shows distinctive
text it leads straight to the video, faster than anything else. Blending its
scores into the visual route (RRF) would smear out exactly that advantage,
which is why the two are kept apart.

Why a linear scan instead of an inverted index
----------------------------------------------
Measured over 179,728 text rows:

  loading both JSON files    1.3 s   (once, at startup)
  scanning one phrase       15-38 ms (per query)

An inverted index would cost another ~23 MB of RAM and 14 s to build, to save a
few milliseconds. Not worth it. A linear scan is also closer to what was asked
for: "which frames CONTAIN THIS TEXT", not "which frames share the most words".

Two files, not one
------------------
`ocr_clean_nodau.json` is `ocr_clean.json` with the diacritics already removed.
Stripping diacritics from 179,728 rows takes 39 s — done at startup the server
stalls for 39 s, done per query every search waits 39 s. Notebook 79 generates
it once instead.

Stripping diacritics is what catches OCR errors: Vintern most often misreads the
diacritics themselves — `HỂ THAO` (THỂ THAO), `MỘT LÀNH ĐẠO` (LÃNH ĐẠO),
`Quan S / Chuyen` (all diacritics lost). Typing `the thao` in stripped mode
finds all three; keeping diacritics is more precise when OCR read them right.
The user picks with a checkbox in the UI.
"""

import json
import os
import re
import time
import unicodedata
from typing import Optional

# Where the two JSON files live: ALONGSIDE the FAISS indexes, not in app/data/.
#
# They ride the same road to production as the indexes — `aws s3 sync
# backend/app/indexes/ s3://aic2026-artifacts/indexes/`, then
# ssm-sync-indexes.sh pulls them onto /opt/aic/indexes. Keeping them in
# app/data/ would mean a second S3 prefix, a second volume and a second step in
# the runbook, all to carry 55 MB down a road that already exists.
#
# Falls back to AIC_INDEX_DIR, not to a path of its own. That is the whole
# point: deploy/p6/ssm-deploy-backend.sh runs `docker compose up` against the
# copy of docker-compose.yml ALREADY ON THE HOST. A deploy ships a new image and
# never the compose file, so adding a variable to the repo's compose does
# nothing in production — which is exactly how the first attempt failed: the
# container looked in /srv/aic/app/indexes (empty, since .gitignore keeps the
# files out of the image) while the files sat in /opt/aic/indexes.
#
# AIC_INDEX_DIR is already set on the host and already points at the mounted
# volume, so riding on it needs no deploy change at all. It is also simply
# true: these two files live beside the FAISS indexes and travel with them.
OCR_DIR = os.environ.get("AIC_OCR_DIR") or os.environ.get(
    "AIC_INDEX_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "indexes"))
WITH_MARKS_PATH = os.path.join(OCR_DIR, "ocr_clean.json")
NO_MARKS_PATH = os.path.join(OCR_DIR, "ocr_clean_nodau.json")

# name -> original text, kept verbatim for DISPLAY (case and diacritics intact)
_display: dict[str, str] = {}
# name -> lowercased text for COMPARISON, in both spellings
_haystack: dict[str, dict[str, str]] = {"with_marks": {}, "no_marks": {}}
_loaded = False
_load_info: dict = {}


def _strip_marks(text: str) -> str:
    """Remove Vietnamese diacritics. Used ONLY on what the user types — the
    corpus was stripped once by notebook 79 and must not be stripped twice."""
    text = unicodedata.normalize("NFD", text).replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def _load() -> None:
    """Read both JSON files into memory. Safe to call repeatedly; loads once.

    Keeps only frames that HAVE text: the other 180,803 are empty and would
    occupy memory without ever matching a query.
    """
    global _loaded
    if _loaded:
        return
    started = time.time()
    missing = [p for p in (WITH_MARKS_PATH, NO_MARKS_PATH) if not os.path.exists(p)]
    if missing:
        raise FileNotFoundError(
            "Thiếu file OCR: " + ", ".join(missing)
            + " — chạy notebooks/thanhbangcao/79_Vanh_tao_ocr_khong_dau.ipynb "
              "để sinh, hoặc đặt AIC_OCR_DIR trỏ tới thư mục chứa chúng.")

    with open(WITH_MARKS_PATH, encoding="utf-8") as f:
        with_marks = json.load(f)
    with open(NO_MARKS_PATH, encoding="utf-8") as f:
        no_marks = json.load(f)

    # The two files must cover the same frames. A mismatch means one is older
    # than the other, and results would then differ depending on whether the
    # user ticked "strip diacritics" — a failure mode that is very hard to trace
    # if allowed to pass silently.
    if set(with_marks) != set(no_marks):
        raise ValueError(
            f"ocr_clean.json ({len(with_marks):,} ảnh) và ocr_clean_nodau.json "
            f"({len(no_marks):,} ảnh) không cùng bộ tên ảnh — sinh lại bằng "
            f"notebook 79.")

    for name, text in with_marks.items():
        text = str(text)
        if not text.strip():
            continue
        _display[name] = text
        _haystack["with_marks"][name] = text.lower()
        # .lower() on the no_marks side is redundant — notebook 79 already
        # lowercases that file — and deliberately kept. During a deploy the
        # container starts against the PREVIOUS copy of the file, before
        # ssm-sync-indexes.sh has pulled the new one, and the previous copy may
        # still carry case. Without this, every search in that window silently
        # returns nothing. Measured cost of the insurance: 35 ms at startup.
        _haystack["no_marks"][name] = str(no_marks[name]).lower()

    _loaded = True
    _load_info.update({
        "total_frames": len(with_marks),
        "frames_with_text": len(_display),
        "load_seconds": round(time.time() - started, 2),
        "with_marks_path": WITH_MARKS_PATH,
        "no_marks_path": NO_MARKS_PATH,
    })
    print(f"[ocr_search] {len(_display):,}/{len(with_marks):,} keyframes carry "
          f"text · loaded in {_load_info['load_seconds']}s")


def _tokenize(text: str) -> list[str]:
    return [w for w in re.split(r"[^0-9a-zA-ZÀ-ỹ]+", text) if w]


# Whole-word matching was tried and REMOVED on request (see git history for the
# regex). It cut "quan an cho lon" from 3,570 hits to 180 by refusing to match
# 'lon' inside 'long an' — but it also refuses partial words the operator may
# well have meant, and OCR splits words wrongly often enough that the strictness
# cost more recall than it bought precision. Substring matching is back.


def search(query: str,
           limit: int = 100,
           strip_diacritics: bool = True,
           video: Optional[str] = None) -> dict:
    """Find frames containing EVERY word of `query`.

    A frame missing even one word is not returned, and nothing is returned when
    nothing qualifies — there is no widening fallback. Words match as
    substrings, so 'lon' does hit 'long an'; that is deliberate, see the note
    above _tokenize.

    Ranking depends ONLY on the text the user typed; no model takes part:

      1. Frames containing the WHOLE PHRASE come first, all of them
      2. The rest rank by how many query words they contain
      3. Ties break toward SHORTER text

    Rule 3 matters more than it looks: a sign reading exactly 'Quán ăn Chợ Lớn'
    is almost certainly what someone is after, whereas the same phrase buried in
    200 characters of scrolling slide text is usually a coincidence.

    Returns two counts:
      * `phrase_matches`   — hold the whole phrase  <- the count to trust
      * `all_word_matches` — hold every word, scattered; the size of the result

    There is deliberately no "holds at least one word" count. Under this rule
    such frames are not returned, so reporting them would advertise a looseness
    that no longer exists — and computing it is what forced the regex across
    all 179,728 rows on every query.

    Notebook 78 measured: `all_word_matches` <= 4 puts the right video first,
    6 times out of 6; >= 142 gets it right only 1 time in 6. Surfacing this
    number tells the operator immediately how far to trust the results, instead
    of paging through 500 images to find out.
    """
    _load()
    started = time.time()

    haystacks = _haystack["no_marks" if strip_diacritics else "with_marks"]
    needle = (_strip_marks(query) if strip_diacritics else query).lower().strip()
    if not needle:
        return {"results": [], "phrase_matches": 0, "all_word_matches": 0,
                "searched_frames": len(haystacks), "processing_time": 0.0}

    # A set, not a list: "chợ chợ" would otherwise want two distinct words and
    # match nothing, because one word can only be found once.
    words = set(_tokenize(needle))
    word_count = len(words)

    # Longest word first. `all()` stops at the first miss, and long words are
    # the rare ones, so the first probe is the one that does the rejecting.
    probes = sorted(words, key=len, reverse=True)

    # A frame only earns a row when it holds EVERY word. There is no
    # partial-match fallback: a query with no result is a true answer, and
    # quietly widening it hands back near-misses that look like hits. Type
    # fewer words to widen instead.
    scored, phrase_hits = [], 0
    for name, haystack in haystacks.items():
        if video and not name.startswith(video):
            continue
        if not all(probe in haystack for probe in probes):
            continue
        whole_phrase = needle in haystack
        if whole_phrase:
            phrase_hits += 1
        # The whole phrase always beats the same words scattered — add a step
        # taller than any achievable word count, so one comparison suffices.
        scored.append(((1000 if whole_phrase else 0) + word_count,
                       len(_display[name]), name))

    # Score descending, then shorter text, then name ascending. The last key
    # exists only so the same query always returns the same order — without it
    # two identical searches sort differently and the operator assumes the data
    # changed underneath them.
    scored.sort(key=lambda row: (-row[0], row[1], row[2]))
    rows = []
    for rank, (score, length, name) in enumerate(scored[:limit], 1):
        rows.append({
            "name": name,
            "score": float(score),
            "rank": rank,
            "exact_phrase": score >= 1000,
            "matched_words": int(score % 1000),
            "total_words": word_count,
            "ocr_text": _display[name],
            "text_length": length,
        })

    return {
        "results": rows,
        "phrase_matches": phrase_hits,
        "all_word_matches": len(scored),
        "searched_frames": len(haystacks),
        "processing_time": round(time.time() - started, 4),
    }


def search_terms(terms : list[str], strip_diacritics : bool = True) -> dict[str, tuple[int, list[tuple[int, bool]]]] :
    """Sibling of search() for a LIST of terms: one scan of the haystack tests
    every term, instead of one scan per term (search() is left untouched).

    Returns {frame name : (len(display text), [(term index, whole_phrase), ...])}
    for every frame that holds at least one term, the matches in term order. The
    display length is what search() breaks ranking ties on (shorter text first),
    so a caller can rank frames without a second lookup. No rows, no limit, no
    ranking here: that is the caller's job (text_lookup.lookup_text_batch_multi).

    Per term the rule is search()'s own: every WORD of the term must be a
    substring of the frame text, and whole_phrase says the typed phrase itself is
    (needle in haystack). A blank term matches nothing and is not counted below.
    With ONE term the result reproduces search() exactly, quirk included: a term
    without a single word character (for example "(" or an emoji) has nothing to
    require, so it matches every frame with text. With two or more terms that
    quirk would turn an OR list into "everything", so a term without word
    characters is matched as a literal phrase there.

    Speed: search() spends most of its time in the all(... generator ...) of its
    inner test (about 250 of 320 ms per pass, against 72 ms for a bare `in` loop).
    Here the longest word of each term (the rarest, so the one that rejects most
    frames) is tested first with a plain `in`, and only frames that pass it get the
    remaining words. Measured against N calls of search() with its row limit
    lifted, both diacritic modes, on the 179,728 real frames: 2.3 to 5.5 times
    faster (1 term 2.3 to 4.2x, 3 and 5 terms 3.9 to 5.5x), because the scan is
    shared and no row dicts are built."""
    _load()
    haystacks = _haystack["no_marks" if strip_diacritics else "with_marks"]
    needles = [(index, (_strip_marks(term) if strip_diacritics else term).lower().strip())
               for index, term in enumerate(terms)]
    needles = [(index, needle) for index, needle in needles if needle]
    plans = []  # (term index, needle, first probe, other probes)
    for index, needle in needles :
        probes = sorted(set(_tokenize(needle)), key=len, reverse=True)
        if probes :
            plans.append((index, needle, probes[0], probes[1 : ]))
        elif len(needles) > 1 :
            plans.append((index, needle, needle, []))  # literal phrase
        else :
            plans.append((index, needle, "", []))      # search()'s quirk: "" is in every text

    found : dict[str, tuple[int, list[tuple[int, bool]]]] = {}
    for name, haystack in haystacks.items() :
        for index, needle, first, rest in plans :
            if first not in haystack :
                continue
            for word in rest :
                if word not in haystack :
                    break
            else :
                entry = found.get(name)
                if entry is None :
                    entry = found[name] = (len(_display[name]), [])
                entry[1].append((index, needle in haystack))
    return found


def get_text(name: str) -> str:
    """OCR text for one frame — empty string when that frame carries none."""
    _load()
    return _display.get(name, "")


def status() -> dict:
    """Tell /status whether this route is ready, without letting it fail."""
    present = os.path.exists(WITH_MARKS_PATH) and os.path.exists(NO_MARKS_PATH)
    out = {"ready": bool(_loaded), "files_present": present,
           "with_marks_path": WITH_MARKS_PATH, "no_marks_path": NO_MARKS_PATH}
    out.update(_load_info)
    return out


def preload() -> None:
    """Load at startup so the first searcher does not pay the 1.3 s.

    Swallowing the error is deliberate: missing OCR files must not stop the
    visual route from working. A real failure surfaces at /ocr-search with a
    message spelling out how to generate them, rather than killing the whole
    server at boot.
    """
    try:
        _load()
    except Exception as e:
        print(f"[ocr_search] not loaded ({e}) — /ocr-search will report the error")
