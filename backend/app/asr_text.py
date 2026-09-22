# -*- coding: utf-8 -*-
"""
asr_text.py — frame filename -> nearby ASR transcript text
=============================================================

Companion to ocr_search.py, same shape: a flat dict loaded once at startup,
O(1) lookup by frame filename, a missing file degrades to "no ASR text"
rather than crashing the server. Built offline by
scripts/build_asr_text_index.py -- see that script's docstring for how the
frame -> nearby-transcript mapping is computed (timestamp math from FPS,
+-padding-second window overlap, dedup across overlapping ASR windows).

Ships as gzipped JSON (8.8 MB compressed, ~579 MB decompressed) alongside
the FAISS indexes and the OCR files, read straight out of gzip -- never
decompressed to a temp file.

Where the file lives
---------------------
Same convention as ocr_search.py: AIC_INDEX_DIR, falling back to the
indexes/ directory next to this file. Rides the same road to production as
the FAISS indexes and the OCR files -- no separate S3 prefix, no separate
deploy step.

get_text() does NOT lazily trigger a load (unlike ocr_search.get_text()).
It is a pure dict lookup that never raises, by design: it is called from
inside the ensemble-search request path (see main.py's text_filter), where
a load failure must never take the visual route down with it. Only
preload() -- called once at startup -- ever attempts to read the file.
"""

import gzip
import json
import os
import time

ASR_DIR = os.environ.get(
    "AIC_INDEX_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "indexes"))
ASR_TEXT_PATH = os.path.join(ASR_DIR, "asr_text_index.json.gz")

# frame filename -> concatenated ASR transcript text near that frame
_asr_text : dict[str, str] = {}
_loaded = False
_load_info : dict = {}


def _load() -> None :
    """Read the gzipped JSON into memory. Safe to call repeatedly; loads once."""
    global _loaded
    if _loaded :
        return
    started = time.time()
    if not os.path.exists(ASR_TEXT_PATH) :
        raise FileNotFoundError(
            f"Missing ASR text file: {ASR_TEXT_PATH} — run "
            f"scripts/build_asr_text_index.py to generate it, or point "
            f"AIC_INDEX_DIR at the directory containing it.")

    with gzip.open(ASR_TEXT_PATH, "rt", encoding="utf-8") as f :
        data = json.load(f)

    _asr_text.clear()
    _asr_text.update(data)
    _loaded = True
    load_seconds = round(time.time() - started, 2)
    gzipped_mb = os.path.getsize(ASR_TEXT_PATH) / 1_000_000
    _load_info.update({
        "entries_loaded" : len(_asr_text),
        "load_seconds" : load_seconds,
        "file_path" : ASR_TEXT_PATH,
    })
    print(f"[asr_text] {len(_asr_text):,} entries loaded · {gzipped_mb:.1f} MB gzipped · "
          f"{load_seconds}s")


def get_text(name : str) -> str :
    """ASR text near one frame — empty string when not found, or when the
    module has never been (successfully) loaded. Never raises."""
    return _asr_text.get(name, "")


def status() -> dict :
    """Tell /status whether this route is ready, without letting it fail."""
    present = os.path.exists(ASR_TEXT_PATH)
    out = {"ready" : bool(_loaded), "files_present" : present, "file_path" : ASR_TEXT_PATH,
           "entries_loaded" : 0, "load_seconds" : 0.0}
    out.update(_load_info)
    return out


def preload() -> None :
    """Load at startup so the first lookup does not pay the decompress cost.

    Swallowing the error is deliberate, same as ocr_search: a missing ASR
    index must not stop the visual route from working. get_text() simply
    returns "" for everything until the file exists and the server restarts.
    """
    try :
        _load()
    except Exception as e :
        print(f"[asr_text] not loaded ({e}) — get_text() will return empty strings")
